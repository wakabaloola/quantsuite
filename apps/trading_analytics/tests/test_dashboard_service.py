# apps/trading_analytics/tests/test_dashboard_service.py
"""
Complete and corrected test suite for the Dashboard Service.
"""

import asyncio
from decimal import Decimal
from unittest.mock import patch, AsyncMock, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading_analytics.dashboard_service import DashboardService
from apps.trading_simulation.models import UserSimulationProfile, SimulatedExchange, SimulatedInstrument
from apps.market_data.models import Ticker, Exchange, Sector, DataSource

User = get_user_model()


class TestDashboardService(TestCase):
    """
    Comprehensive test suite for the DashboardService, ensuring all
    core functionalities are tested with a correct and efficient setup.
    """

    @classmethod
    def setUpTestData(cls):
        """Set up all necessary database objects once for the entire test class."""
        cls.user = User.objects.create_user(username='testuser', password='testpassword')
        UserSimulationProfile.objects.create(
            user=cls.user,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00')
        )

    def setUp(self):
        """Set up for each test method."""
        self.service = DashboardService()

    def test_service_initialization(self):
        """Test that the service initializes correctly."""
        self.assertIn('market_overview', self.service.cache_ttl)
        self.assertEqual(self.service.cache_ttl['portfolio_summary'], 300)

    @patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service.calculate_comprehensive_analytics', new_callable=AsyncMock)
    def test_get_portfolio_analytics(self, mock_calculate_analytics):
        """Test the get_portfolio_analytics method."""
        # Configure the mock to return a mock object with attributes
        mock_analytics_result = Mock()
        mock_analytics_result.total_value = 115000.0
        mock_analytics_result.portfolio_beta = 1.02
        mock_analytics_result.position_count = 5
        mock_analytics_result.sharpe_ratio = 1.5
        mock_analytics_result.max_drawdown = -0.05
        mock_calculate_analytics.return_value = mock_analytics_result

        result = asyncio.run(self.service.get_portfolio_analytics(self.user.id))

        self.assertIn('summary', result)
        self.assertIn('risk_metrics', result)
        self.assertEqual(result['summary']['total_value'], 115000.0)
        self.assertEqual(result['risk_metrics']['portfolio_beta'], 1.02)
        mock_calculate_analytics.assert_called_once_with(self.user.id)

    @patch('apps.market_data.streaming.streaming_engine.get_current_quote', new_callable=AsyncMock)
    @patch('apps.market_data.analysis.enhanced_ta_service.get_cached_signal')
    def test_get_market_analytics(self, mock_get_signal, mock_get_quote):
        """Test the get_market_analytics method."""
        # Mock responses from dependencies
        mock_get_quote.return_value = Mock(price=Decimal('150.00'), volume=1000000)
        mock_get_signal.return_value = Mock(to_dict=lambda: {'signal_type': 'BUY', 'strength': 0.8})

        symbols = ['AAPL', 'MSFT']
        result = asyncio.run(self.service.get_market_analytics(symbols))

        self.assertIn('quotes', result)
        self.assertIn('technical_signals', result)
        self.assertIn('AAPL', result['quotes'])
        self.assertEqual(result['quotes']['AAPL']['price'], 150.0)
        self.assertEqual(result['technical_signals']['AAPL']['signal_type'], 'BUY')

    @patch.object(DashboardService, '_get_portfolio_value', new_callable=AsyncMock)
    @patch.object(DashboardService, '_get_positions_count', new_callable=AsyncMock)
    @patch.object(DashboardService, '_get_active_risk_alerts', new_callable=AsyncMock)
    def test_get_risk_analytics(self, mock_alerts, mock_positions, mock_value):
        """Test the get_risk_analytics method."""
        mock_value.return_value = 115000.0
        mock_positions.return_value = 5
        mock_alerts.return_value = []

        result = asyncio.run(self.service.get_risk_analytics(self.user.id))

        self.assertIn('risk_score', result)
        self.assertEqual(result['risk_score'], 'LOW')
        self.assertEqual(result['positions_count'], 5)

    def test_error_handling_invalid_user(self):
        """Test that methods handle invalid user IDs gracefully."""
        result = asyncio.run(self.service.get_portfolio_analytics(99999))
        self.assertEqual(result, {})

    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_portfolio_analytics', new_callable=AsyncMock)
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_market_analytics', new_callable=AsyncMock)
    def test_get_unified_dashboard_data(self, mock_market, mock_portfolio):
        """Test the unified dashboard data aggregation."""
        mock_portfolio.return_value = {'summary': {'total_value': 115000.0}}
        mock_market.return_value = {'quotes': {'AAPL': {'price': 150.0}}}

        result = asyncio.run(self.service.get_unified_dashboard_data(self.user.id, ['AAPL']))

        self.assertIn('dashboard_data', result)
        self.assertIn('portfolio', result['dashboard_data'])
        self.assertIn('market', result['dashboard_data'])
        self.assertEqual(result['dashboard_data']['market']['quotes']['AAPL']['price'], 150.0)

