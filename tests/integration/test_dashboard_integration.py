# tests/integration/test_dashboard_integration.py
"""
Refactored Integration Tests for Dashboard System
=================================================
This version uses best practices for Django testing, ensuring a clean,
reliable, and efficient test setup.
"""

import asyncio
from decimal import Decimal
from unittest.mock import patch

# Use Django's standard TestCase for automatic transaction rollback and better isolation.
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

# Import all necessary models
from apps.trading_simulation.models import (
    UserSimulationProfile, SimulatedPosition, SimulatedInstrument,
    SimulatedExchange
)
from apps.market_data.models import Ticker, Exchange, Sector, DataSource
from apps.order_management.models import SimulatedOrder

User = get_user_model()


class TestDashboardIntegration(TestCase):
    """
    Integration tests for the core dashboard functionality.
    Uses setUpTestData for efficient, one-time setup of shared resources.
    """

    @classmethod
    def setUpTestData(cls):
        """
        Set up non-modified objects used by all test methods.
        This runs once for the entire test class, making tests faster.
        """
        print("🔧 Setting up integration test data (once per class)...")

        # 1. Create User
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )

        # 2. Create Core Market Data Dependencies
        cls.data_source = DataSource.objects.create(name='Test Source', code='TESTSRC', is_active=True)
        cls.sector = Sector.objects.create(name='Technology', code='TECH')
        cls.real_exchange = Exchange.objects.create(name='NASDAQ', code='NASDAQ', country='US')

        # 3. Create a Ticker
        cls.ticker = Ticker.objects.create(
            symbol='AAPL',
            name='Apple Inc.',
            exchange=cls.real_exchange,
            sector=cls.sector,
            data_source=cls.data_source,
            is_active=True
        )

        # 4. Create Simulation-Layer Objects
        # 🔥 FIX: Create SimulatedExchange WITH the required real_exchange
        cls.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NASDAQ',
            code='SIM_NASDAQ',
            real_exchange=cls.real_exchange
        )

        cls.sim_instrument = SimulatedInstrument.objects.create(
            real_ticker=cls.ticker,
            exchange=cls.sim_exchange,
            is_tradable=True
        )

        # 5. Create User-Specific Simulation Data
        # 🔥 FIX: Create the UserSimulationProfile that the API views require
        cls.profile = UserSimulationProfile.objects.create(
            user=cls.user,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00'),
            virtual_cash_balance=Decimal('15000.00')
        )

        cls.position = SimulatedPosition.objects.create(
            user=cls.user,
            instrument=cls.sim_instrument,
            quantity=Decimal('100'),
            average_cost=Decimal('1000.00'),
            total_cost=Decimal('100000.00'),
            market_value=Decimal('115000.00')
        )
        print("✅ Test data setup complete.")

    def setUp(self):
        """
        Set up for each test method. Runs after setUpTestData.
        This is the place for objects that might be modified by tests.
        """
        # Create an API client and authenticate the user for API tests
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_core_model_creation(self):
        """Test that core models were created successfully in setup."""
        print("🧪 Testing Core Model Creation...")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SimulatedExchange.objects.count(), 1)
        self.assertEqual(UserSimulationProfile.objects.count(), 1)
        self.assertEqual(SimulatedPosition.objects.count(), 1)
        # Check the relationship that was failing before
        sim_exchange = SimulatedExchange.objects.first()
        self.assertIsNotNone(sim_exchange.real_exchange)
        self.assertEqual(sim_exchange.real_exchange.code, 'NASDAQ')
        print("✅ Core model creation test passed")

    def test_dashboard_summary_api_endpoint(self):
        """Test the dashboard summary REST API endpoint."""
        print("🌐 Testing Dashboard Summary API Endpoint...")
        url = '/api/analytics/dashboard/summary/'

        # Mock the service layer calls to isolate the view logic
        with patch('apps.trading_analytics.views.dashboard_service') as mock_service:
            # Configure the mock to return a dictionary when its methods are called
            mock_service.get_portfolio_analytics.return_value = asyncio.Future()
            mock_service.get_portfolio_analytics.return_value.set_result({
                'summary': {'total_value': 115000.0, 'daily_pnl': 500.0},
                'position_metrics': {'position_count': 1}
            })
            mock_service.get_risk_analytics.return_value = asyncio.Future()
            mock_service.get_risk_analytics.return_value.set_result({
                'risk_score': 'LOW', 'alerts': {'active_count': 0}, 'portfolio_var_1d': 1200.0
            })
            mock_service.get_performance_analytics.return_value = asyncio.Future()
            mock_service.get_performance_analytics.return_value.set_result({
                'current_performance': {'total_return_pct': 15.0, 'win_rate': 60.0}
            })

            response = self.client.get(url)

            # Assertions
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['summary']['portfolio']['total_value'], 115000.0)
            self.assertEqual(data['summary']['risk']['risk_score'], 'LOW')
            self.assertEqual(data['summary']['performance']['total_return_pct'], 15.0)

        print("✅ Dashboard summary API endpoint test passed")

    def test_dashboard_data_api_endpoint(self):
        """Test the dashboard data REST API endpoint."""
        print("📊 Testing Dashboard Data API Endpoint...")
        url = '/api/analytics/dashboard/data/'

        with patch('apps.trading_analytics.views.dashboard_service') as mock_service:
            # Configure the mock to return a comprehensive data structure
            mock_service.get_unified_dashboard_data.return_value = asyncio.Future()
            mock_service.get_unified_dashboard_data.return_value.set_result({
                'portfolio': {'total_value': 115000.0},
                'market': {'quotes': {'AAPL': {'price': 155.0}}}
            })

            response = self.client.get(url, {'symbols': ['AAPL']})

            # Assertions
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['status'], 'success')
            self.assertIn('data', data)
            self.assertEqual(data['data']['portfolio']['total_value'], 115000.0)

        print("✅ Dashboard data API endpoint test passed")

    def test_database_operations(self):
        """Test that basic database operations are working as expected."""
        print("🗄️  Testing Database Operations...")
        user = User.objects.get(username='testuser')
        profile = UserSimulationProfile.objects.get(user=user)
        self.assertEqual(profile.user.username, 'testuser')
        self.assertEqual(profile.initial_virtual_balance, Decimal('100000.00'))
        # Test a profile method
        self.assertAlmostEqual(profile.calculate_total_return_percentage(), 15.0)
        print("✅ Database operations test passed")

    def test_cache_operations(self):
        """Test that the cache is configured and working."""
        print("💾 Testing Cache Operations...")
        from django.core.cache import cache
        cache.set('test_key', 'test_value', 30)
        retrieved_value = cache.get('test_key')
        self.assertEqual(retrieved_value, 'test_value')
        print("✅ Cache operations test passed")


