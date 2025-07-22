# apps/trading_analytics/tests/test_portfolio_analytics.py
"""
Test suite for portfolio analytics service and calculations
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading_analytics.portfolio_analytics import (
    PortfolioAnalyticsService, PortfolioMetrics, PositionAnalytics, SectorAllocation
)
from apps.trading_simulation.models import (
    UserSimulationProfile, SimulatedPosition, SimulatedInstrument
)
from apps.market_data.models import Ticker, Exchange, Sector

User = get_user_model()


class TestPortfolioMetrics(TestCase):
    """Test PortfolioMetrics data structure"""
    
    def test_portfolio_metrics_creation(self):
        """Test creating PortfolioMetrics"""
        metrics = PortfolioMetrics(
            total_value=100000.0,
            cash_balance=10000.0,
            invested_value=90000.0,
            total_return_pct=15.5,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            intraday_pnl=500.0,
            daily_pnl=1000.0,
            weekly_pnl=3000.0,
            monthly_pnl=8000.0,
            ytd_pnl=15000.0,
            portfolio_var_1day=-2000.0,
            portfolio_volatility=0.18,
            portfolio_beta=1.05,
            max_drawdown=-0.08,
            sharpe_ratio=1.45,
            alpha=0.03,
            tracking_error=0.05,
            information_ratio=0.6,
            position_count=12,
            largest_position_pct=8.5,
            top5_concentration=35.2,
            sector_count=6,
            last_updated=timezone.now(),
            calculation_time_ms=150.5
        )
        
        self.assertEqual(metrics.total_value, 100000.0)
        self.assertEqual(metrics.position_count, 12)
        self.assertEqual(metrics.sharpe_ratio, 1.45)
        
        # Test serialization
        data = metrics.to_dict()
        self.assertIn('total_value', data)
        self.assertIn('sharpe_ratio', data)
        self.assertIn('last_updated', data)


class TestPositionAnalytics(TestCase):
    """Test PositionAnalytics data structure"""
    
    def test_position_analytics_creation(self):
        """Test creating PositionAnalytics"""
        analytics = PositionAnalytics(
            symbol='AAPL',
            quantity=100.0,
            market_value=15000.0,
            weight_pct=7.5,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=3.45,
            daily_pnl=75.0,
            daily_pnl_pct=0.5,
            position_var=-300.0,
            volatility=0.25,
            beta=1.15,
            correlation_to_portfolio=0.75,
            return_1d=0.5,
            return_7d=2.1,
            return_30d=8.3,
            return_ytd=15.7,
            sector='Technology',
            market_cap_category='Large Cap',
            last_price=150.0,
            avg_cost=145.0
        )
        
        self.assertEqual(analytics.symbol, 'AAPL')
        self.assertEqual(analytics.market_value, 15000.0)
        self.assertEqual(analytics.sector, 'Technology')
        
        # Test serialization
        data = analytics.to_dict()
        self.assertIn('symbol', data)
        self.assertIn('unrealized_pnl_pct', data)


class TestSectorAllocation(TestCase):
    """Test SectorAllocation data structure"""
    
    def test_sector_allocation_creation(self):
        """Test creating SectorAllocation"""
        allocation = SectorAllocation(
            sector='Technology',
            market_value=45000.0,
            weight_pct=45.0,
            position_count=5,
            pnl_contribution=2250.0,
            avg_return=12.5,
            volatility=0.22
        )
        
        self.assertEqual(allocation.sector, 'Technology')
        self.assertEqual(allocation.weight_pct, 45.0)
        self.assertEqual(allocation.position_count, 5)
        
        # Test serialization
        data = allocation.to_dict()
        self.assertIn('sector', data)
        self.assertIn('pnl_contribution', data)


class TestPortfolioAnalyticsService(TestCase):
    """Test PortfolioAnalyticsService functionality"""
    
    def setUp(self):
        self.service = PortfolioAnalyticsService()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create user profile
        self.profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00'),
            virtual_cash_balance=Decimal('15000.00')
        )
        
        # Create test data
        self.exchange = Exchange.objects.create(
            name='NASDAQ',
            code='NASDAQ',
            country='US',
            timezone='America/New_York'
        )
        
        self.sector = Sector.objects.create(
            name='Technology',
            description='Technology companies'
        )
        
        self.ticker = Ticker.objects.create(
            symbol='AAPL',
            name='Apple Inc.',
            exchange=self.exchange,
            sector=self.sector,
            is_active=True
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            simulated_exchange_id=1,  # Assuming this exists
            is_active=True
        )
    
    @patch('apps.trading_analytics.portfolio_analytics.database_sync_to_async')
    async def test_get_portfolio_data(self, mock_db_sync):
        """Test getting portfolio data"""
        # Mock the database call
        mock_db_sync.return_value = Mock(return_value={
            'total_value': 115000.0,
            'cash_balance': 15000.0,
            'total_return_pct': 15.0,
            'positions': []
        })
        
        result = await self.service._get_portfolio_data(self.user.id)
        
        self.assertIsNotNone(result)
        mock_db_sync.assert_called_once()
    
    @patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service._get_portfolio_data')
    @patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service._calculate_all_metrics')
    @patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service._cache_analytics')
    async def test_calculate_comprehensive_analytics(self, mock_cache, mock_calculate, mock_get_data):
        """Test comprehensive analytics calculation"""
        # Mock portfolio data
        mock_get_data.return_value = {
            'total_value': 115000.0,
            'cash_balance': 15000.0,
            'total_return_pct': 15.0,
            'positions': []
        }
        
        # Mock calculated metrics
        mock_metrics = PortfolioMetrics(
            total_value=115000.0,
            cash_balance=15000.0,
            invested_value=100000.0,
            total_return_pct=15.0,
            unrealized_pnl=5000.0,
            realized_pnl=10000.0,
            intraday_pnl=200.0,
            daily_pnl=500.0,
            weekly_pnl=2000.0,
            monthly_pnl=5000.0,
            ytd_pnl=15000.0,
            portfolio_var_1day=-2300.0,
            portfolio_volatility=0.16,
            portfolio_beta=1.02,
            max_drawdown=-0.05,
            sharpe_ratio=1.25,
            alpha=0.02,
            tracking_error=0.04,
            information_ratio=0.5,
            position_count=8,
            largest_position_pct=12.5,
            top5_concentration=45.0,
            sector_count=4,
            last_updated=timezone.now(),
            calculation_time_ms=0.0
        )
        
        mock_calculate.return_value = mock_metrics
        mock_cache.return_value = None
        
        result = await self.service.calculate_comprehensive_analytics(self.user.id)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.total_value, 115000.0)
        self.assertEqual(result.position_count, 8)
        
        mock_get_data.assert_called_once_with(self.user.id)
        mock_calculate.assert_called_once()
        mock_cache.assert_called_once()
    
    def test_service_initialization(self):
        """Test service initialization"""
        service = PortfolioAnalyticsService()
        
        self.assertEqual(service.cache_ttl, 300)
        self.assertEqual(service.risk_free_rate, 0.02)
        self.assertEqual(service.benchmark_symbol, '^GSPC')
        self.assertIsInstance(service.calculation_cache, dict)
        self.assertIsInstance(service.last_calculation_time, dict)
    
    async def test_get_position_analytics_empty(self):
        """Test getting position analytics with no positions"""
        with patch('apps.trading_analytics.portfolio_analytics.database_sync_to_async') as mock_db:
            mock_db.return_value = Mock(return_value=[])
            
            result = await self.service.get_position_analytics(self.user.id)
            
            self.assertEqual(len(result), 0)
    
    async def test_get_sector_allocation_empty(self):
        """Test getting sector allocation with no positions"""
        with patch('apps.trading_analytics.portfolio_analytics.database_sync_to_async') as mock_db:
            mock_db.return_value = Mock(return_value=[])
            
            result = await self.service.get_sector_allocation(self.user.id)
            
            self.assertEqual(len(result), 0)


@pytest.mark.asyncio
class TestPortfolioAnalyticsAsync:
    """Async tests for portfolio analytics"""
    
    async def test_analytics_performance(self):
        """Test analytics calculation performance"""
        service = PortfolioAnalyticsService()
        
        # Test with mocked data
        with patch.object(service, '_get_portfolio_data') as mock_data:
            mock_data.return_value = {
                'total_value': 100000.0,
                'cash_balance': 10000.0,
                'positions': []
            }
            
            start_time = timezone.now()
            
            # This would normally calculate real metrics
            # For testing, we'll just verify the method can be called
            with patch.object(service, '_calculate_all_metrics') as mock_calc:
                mock_calc.return_value = Mock()
                
                result = await service.calculate_comprehensive_analytics(1)
                
                # Verify it completed in reasonable time
                execution_time = (timezone.now() - start_time).total_seconds()
                assert execution_time < 5.0  # Should complete in under 5 seconds
    
    async def test_concurrent_analytics_calculations(self):
        """Test multiple analytics calculations running concurrently"""
        service = PortfolioAnalyticsService()
        
        # Mock the data fetching
        with patch.object(service, '_get_portfolio_data') as mock_data:
            mock_data.return_value = {
                'total_value': 100000.0,
                'cash_balance': 10000.0,
                'positions': []
            }
            
            with patch.object(service, '_calculate_all_metrics') as mock_calc:
                mock_calc.return_value = Mock()
                
                # Run multiple calculations concurrently
                import asyncio
                tasks = [
                    service.calculate_comprehensive_analytics(i)
                    for i in range(1, 6)
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # All should complete without exceptions
                for result in results:
                    assert not isinstance(result, Exception)
