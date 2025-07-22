# apps/trading_analytics/tests/test_dashboard_service.py
"""
Test suite for dashboard service functionality
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading_analytics.dashboard_service import DashboardService

User = get_user_model()


class TestDashboardService(TestCase):
    """Test DashboardService functionality"""
    
    def setUp(self):
        self.service = DashboardService()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_service_initialization(self):
        """Test service initialization"""
        self.assertIsInstance(self.service.cache_ttl, dict)
        self.assertIn('market_overview', self.service.cache_ttl)
        self.assertIn('portfolio_summary', self.service.cache_ttl)
        self.assertEqual(self.service.cache_ttl['market_overview'], 60)
    
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_portfolio_analytics')
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_market_analytics')
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_risk_analytics')
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_performance_analytics')
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_active_alerts')
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_execution_summary')
    async def test_get_unified_dashboard_data(self, mock_execution, mock_alerts, 
                                            mock_performance, mock_risk, 
                                            mock_market, mock_portfolio):
        """Test getting unified dashboard data"""
        # Mock all the service methods
        mock_portfolio.return_value = {'total_value': 100000}
        mock_market.return_value = {'quotes': {'AAPL': {'price': 150.0}}}
        mock_risk.return_value = {'risk_score': 'LOW'}
        mock_performance.return_value = {'total_return_pct': 15.0}
        mock_alerts.return_value = []
        mock_execution.return_value = {'active_orders': 0}
        
        result = await self.service.get_unified_dashboard_data(
            self.user.id, 
            ['AAPL', 'MSFT']
        )
        
        self.assertIn('dashboard_data', result)
        self.assertIn('timestamp', result)
        self.assertIn('user_id', result)
        self.assertEqual(result['user_id'], self.user.id)
        
        # Verify all components were called
        mock_portfolio.assert_called_once_with(self.user.id)
        mock_market.assert_called_once_with(['AAPL', 'MSFT'])
        mock_risk.assert_called_once_with(self.user.id)
    
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    @patch('apps.trading_analytics.dashboard_service.portfolio_analytics_service.calculate_comprehensive_analytics')
    async def test_get_portfolio_analytics_with_cache(self, mock_analytics, mock_cache_set, mock_cache_get):
        """Test portfolio analytics with caching"""
        # Test cache miss
        mock_cache_get.return_value = None
        mock_analytics.return_value = Mock(
            total_value=100000.0,
            cash_balance=10000.0,
            daily_pnl=500.0
        )
        
        result = await self.service.get_portfolio_analytics(self.user.id)
        
        self.assertIn('summary', result)
        self.assertIn('risk_metrics', result)
        mock_cache_set.assert_called_once()
        
        # Test cache hit
        mock_cache_get.return_value = {'cached': True}
        
        result = await self.service.get_portfolio_analytics(self.user.id)
        self.assertEqual(result, {'cached': True})
    
    @patch('apps.trading_analytics.dashboard_service.streaming_engine.get_current_quote')
    @patch('apps.trading_analytics.dashboard_service.enhanced_ta_service.get_cached_signal')
    async def test_get_market_analytics(self, mock_signal, mock_quote):
        """Test market analytics gathering"""
        # Mock quote
        mock_quote.return_value = Mock(
            price=150.0,
            volume=1000000,
            change_24h=2.5,
            change_pct_24h=1.67,
            bid=149.95,
            ask=150.05,
            timestamp=timezone.now()
        )
        
        # Mock signal
        mock_signal.return_value = Mock(
            signal_type=Mock(value='BUY'),
            strength=0.75,
            confidence=Mock(value='HIGH'),
            trend_direction=Mock(value='UP')
        )
        
        result = await self.service.get_market_analytics(['AAPL'])
        
        self.assertIn('quotes', result)
        self.assertIn('technical_signals', result)
        self.assertIn('overview', result)
        self.assertEqual(result['symbols_count'], 1)
        
        # Check quote data
        self.assertIn('AAPL', result['quotes'])
        self.assertEqual(result['quotes']['AAPL']['price'], 150.0)
    
    async def test_get_risk_analytics(self):
        """Test risk analytics calculation"""
        with patch.object(self.service, '_get_portfolio_value', return_value=100000.0):
            with patch.object(self.service, '_get_positions_count', return_value=10):
                with patch.object(self.service, '_get_active_risk_alerts', return_value=[]):
                    
                    result = await self.service.get_risk_analytics(self.user.id)
                    
                    self.assertIn('portfolio_var_1d', result)
                    self.assertIn('positions_count', result)
                    self.assertIn('risk_score', result)
                    self.assertEqual(result['positions_count'], 10)
    
    async def test_analyze_correlations_insufficient_symbols(self):
        """Test correlation analysis with insufficient symbols"""
        result = await self.service.analyze_correlations(self.user.id, ['AAPL'])
        
        self.assertEqual(result, {})
    
    @patch('django.core.cache.cache.get')
    async def test_analyze_correlations_with_data(self, mock_cache_get):
        """Test correlation analysis with sufficient data"""
        # Mock correlation matrix
        mock_cache_get.return_value = {
            'AAPL': {'AAPL': 1.0, 'MSFT': 0.75},
            'MSFT': {'AAPL': 0.75, 'MSFT': 1.0}
        }
        
        result = await self.service.analyze_correlations(self.user.id, ['AAPL', 'MSFT'])
        
        self.assertIn('correlation_matrix', result)
        self.assertIn('average_correlation', result)
        self.assertIn('diversification_ratio', result)
        self.assertEqual(result['average_correlation'], 0.75)
    
    async def test_get_market_context(self):
        """Test market context calculation"""
        with patch('apps.trading_analytics.dashboard_service.streaming_engine.get_current_quote') as mock_quote:
            mock_quote.return_value = Mock(
                price=450.0,
                change_pct_24h=1.5
            )
            
            result = await self.service.get_market_context()
            
            self.assertIn('indices', result)
            self.assertIn('market_sentiment', result)
            self.assertIn('session_info', result)
    
    def test_determine_market_sentiment_bullish(self):
        """Test bullish market sentiment determination"""
        indices_data = {
            'SPY': {'change_pct': 2.0, 'price': 450},
            'VIX': {'price': 15.0}
        }
        
        result = self.service._determine_market_sentiment(indices_data)
        
        self.assertEqual(result['overall_sentiment'], 'BULLISH')
        self.assertEqual(result['volatility_level'], 'LOW')
    
    def test_determine_market_sentiment_bearish(self):
        """Test bearish market sentiment determination"""
        indices_data = {
            'SPY': {'change_pct': -2.5, 'price': 420},
            'VIX': {'price': 35.0}
        }
        
        result = self.service._determine_market_sentiment(indices_data)
        
        self.assertEqual(result['overall_sentiment'], 'BEARISH')
        self.assertEqual(result['volatility_level'], 'HIGH')
    
    async def test_calculate_data_quality(self):
        """Test data quality calculation"""
        dashboard_data = {
            'portfolio': {'total_value': 100000},
            'market': {'data_completeness': 0.95, 'quotes': {'AAPL': {}}},
            'risk': {'risk_score': 'LOW'},
            'performance': {'total_return_pct': 15.0}
        }
        
        result = await self.service.calculate_data_quality(dashboard_data)
        
        self.assertIn('overall_score', result)
        self.assertIn('component_scores', result)
        self.assertGreater(result['overall_score'], 0)
        self.assertEqual(result['component_scores']['market'], 95.0)


@pytest.mark.asyncio
class TestDashboardServiceAsync:
    """Async-specific tests for dashboard service"""
    
    async def test_concurrent_data_gathering(self):
        """Test concurrent data gathering performance"""
        service = DashboardService()
        
        with patch.object(service, 'get_portfolio_analytics', new_callable=AsyncMock) as mock_portfolio:
            with patch.object(service, 'get_market_analytics', new_callable=AsyncMock) as mock_market:
                with patch.object(service, 'get_risk_analytics', new_callable=AsyncMock) as mock_risk:
                    
                    mock_portfolio.return_value = {}
                    mock_market.return_value = {}
                    mock_risk.return_value = {}
                    
                    start_time = timezone.now()
                    
                    result = await service.get_unified_dashboard_data(1, [])
                    
                    execution_time = (timezone.now() - start_time).total_seconds()
                    
                    # Should complete quickly due to concurrent execution
                    assert execution_time < 2.0
                    assert 'dashboard_data' in result
    
    async def test_error_handling_in_unified_data(self):
        """Test error handling in unified data gathering"""
        service = DashboardService()
        
        with patch.object(service, 'get_portfolio_analytics', new_callable=AsyncMock) as mock_portfolio:
            with patch.object(service, 'get_market_analytics', new_callable=AsyncMock) as mock_market:
                
                # Make one service fail
                mock_portfolio.side_effect = Exception("Portfolio service error")
                mock_market.return_value = {'quotes': {}}
                
                result = await service.get_unified_dashboard_data(1, [])
                
                # Should still return data, with empty portfolio data
                assert 'dashboard_data' in result
                assert result['dashboard_data']['portfolio'] == {}
                assert 'market' in result['dashboard_data']
