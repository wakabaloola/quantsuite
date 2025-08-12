# apps/trading_analytics/tests/test_dashboard_service.py
"""
Complete and corrected test suite for the Dashboard Service.

This version uses modern async test patterns (`async def`) and the correct
mocking library (`AsyncMock`). It provides correctly structured, pickleable
mock data to match what the service code expects.
"""

from decimal import Decimal
from unittest.mock import patch, AsyncMock, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading_analytics.dashboard_service import DashboardService

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

    def setUp(self):
        """Set up for each test method."""
        self.service = DashboardService()

    def test_service_initialization(self):
        """Test that the service initializes correctly."""
        self.assertIn('market_overview', self.service.cache_ttl)
        self.assertEqual(self.service.cache_ttl['portfolio_summary'], 30)

    @patch('apps.trading_analytics.dashboard_service.portfolio_analytics_service.calculate_comprehensive_analytics', new_callable=AsyncMock)
    async def test_get_portfolio_analytics(self, mock_calculate_analytics):
        """Test the get_portfolio_analytics method with a correctly structured mock object."""
        mock_result = Mock()
        mock_result.total_value = 115000.0
        mock_result.cash_balance = 15000.0
        mock_result.invested_value = 100000.0
        mock_result.total_return_pct = 15.0
        mock_result.daily_pnl = 500.0
        mock_result.unrealized_pnl = 15000.0
        mock_result.portfolio_var_1day = 2000.0
        mock_result.portfolio_volatility = 0.18
        mock_result.portfolio_beta = 1.02
        mock_result.max_drawdown = -0.05
        mock_result.sharpe_ratio = 1.2
        mock_result.alpha = 0.03
        mock_result.tracking_error = 0.02
        mock_result.position_count = 5
        mock_result.largest_position_pct = 20.0
        mock_result.top5_concentration = 75.0
        mock_result.sector_count = 3
        mock_calculate_analytics.return_value = mock_result

        result = await self.service.get_portfolio_analytics(self.user.id)

        self.assertIn('summary', result)
        self.assertEqual(result['summary']['total_value'], 115000.0)
        mock_calculate_analytics.assert_awaited_once_with(self.user.id)

    @patch('apps.market_data.streaming.streaming_engine.get_current_quote', new_callable=AsyncMock)
    @patch('apps.market_data.analysis.enhanced_ta_service.get_cached_signal')
    async def test_get_market_analytics(self, mock_get_signal, mock_get_quote):
        """Test the get_market_analytics method with detailed, realistic mock objects."""
        def quote_side_effect(symbol):
            if symbol == 'AAPL':
                mock_quote = Mock()
                mock_quote.price = 150.0
                mock_quote.volume = 5000000
                mock_quote.change_24h = 2.5
                mock_quote.change_pct_24h = 1.67
                mock_quote.bid = 149.95
                mock_quote.ask = 150.05
                mock_quote.timestamp = timezone.now()
                return mock_quote
            return None

        mock_get_quote.side_effect = quote_side_effect
        mock_get_signal.return_value = None  # No signal for simplicity

        result = await self.service.get_market_analytics(['AAPL'])

        self.assertIn('quotes', result)
        self.assertIn('AAPL', result['quotes'])
        self.assertEqual(result['quotes']['AAPL']['price'], 150.0)

    # FIX: The patch target now points to the absolute path of the function.
    @patch('apps.trading_analytics.dashboard_service.DashboardService._calculate_risk_score', new_callable=AsyncMock)
    async def test_get_risk_analytics(self, mock_calculate_risk_score):
        """Test the get_risk_analytics method with the correct patch target."""
        mock_calculate_risk_score.return_value = 'LOW'

        result = await self.service.get_risk_analytics(self.user.id)

        self.assertEqual(result['risk_score'], 'LOW')
        mock_calculate_risk_score.assert_awaited_once_with(self.user.id)

    async def test_error_handling_invalid_user(self):
        """Test that methods handle invalid user IDs gracefully."""
        with patch('apps.trading_analytics.dashboard_service.portfolio_analytics_service.calculate_comprehensive_analytics', new_callable=AsyncMock) as mock_calc:
            mock_calc.side_effect = User.DoesNotExist
            result = await self.service.get_portfolio_analytics(99999)
            self.assertEqual(result, {})

    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_portfolio_analytics', new_callable=AsyncMock)
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_market_analytics', new_callable=AsyncMock)
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_risk_analytics', new_callable=AsyncMock)
    async def test_get_unified_dashboard_data(self, mock_risk, mock_market, mock_portfolio):
        """Test the unified dashboard data aggregation with correct async mocking."""
        mock_portfolio.return_value = {'summary': {'total_value': 115000.0}}
        mock_market.return_value = {'quotes': {'AAPL': {'price': 150.0}}}
        mock_risk.return_value = {'risk_score': 'LOW'}

        result = await self.service.get_unified_dashboard_data(self.user.id, ['AAPL'])

        self.assertIn('dashboard_data', result)
        self.assertEqual(result['dashboard_data']['market']['quotes']['AAPL']['price'], 150.0)
        self.assertEqual(result['dashboard_data']['portfolio']['summary']['total_value'], 115000.0)
        self.assertEqual(result['dashboard_data']['risk']['risk_score'], 'LOW')

