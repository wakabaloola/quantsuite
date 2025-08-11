# apps/trading_analytics/tests/test_dashboard_api.py
"""
Complete and corrected test suite for dashboard API endpoints.
"""

from unittest.mock import patch, AsyncMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.trading_simulation.models import UserSimulationProfile

User = get_user_model()


class TestDashboardAPIs(TestCase):
    """
    Comprehensive test suite for all dashboard REST API endpoints.
    """

    @classmethod
    def setUpTestData(cls):
        """Set up data once for all tests in this class."""
        cls.user = User.objects.create_user(username='testuser', password='testpassword')
        UserSimulationProfile.objects.create(user=cls.user)

    def setUp(self):
        """Set up the API client and authenticate for each test."""
        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    @patch('apps.trading_analytics.views.dashboard_service.get_unified_dashboard_data', new_callable=AsyncMock)
    def test_dashboard_data_api_success(self, mock_get_data):
        """Test successful GET to /dashboard/data/."""
        mock_get_data.return_value = {'dashboard_data': {}}
        response = self.client.get(reverse('trading_analytics:dashboard_data'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.trading_analytics.views.dashboard_service.get_portfolio_analytics', new_callable=AsyncMock)
    @patch('apps.trading_analytics.views.dashboard_service.get_risk_analytics', new_callable=AsyncMock)
    @patch('apps.trading_analytics.views.dashboard_service.get_performance_analytics', new_callable=AsyncMock)
    def test_dashboard_summary_api_success(self, mock_perf, mock_risk, mock_portfolio):
        """Test successful GET to /dashboard/summary/."""
        mock_portfolio.return_value = {'summary': {}}
        mock_risk.return_value = {'risk_score': 'LOW'}
        mock_perf.return_value = {'current_performance': {}}
        response = self.client.get(reverse('trading_analytics:dashboard_summary'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

