# apps/trading_analytics/tests/test_dashboard_api.py
"""
Test suite for dashboard API endpoints
"""

import json
from unittest.mock import Mock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.trading_simulation.models import UserSimulationProfile

User = get_user_model()


class TestDashboardAPIEndpoints(TestCase):
    """Test dashboard REST API endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create user profile
        self.profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=115000.00,
            virtual_cash_balance=15000.00
        )
        
        # Get JWT token for authentication
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        
        # Set authentication header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
    
    def test_dashboard_data_api_authentication_required(self):
        """Test that dashboard data API requires authentication"""
        # Remove authentication
        self.client.credentials()
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    @patch('apps.trading_analytics.views.async_to_sync')
    @patch('django.core.cache.cache.get')
    def test_dashboard_data_api_success(self, mock_cache_get, mock_async_sync):
        """Test successful dashboard data API call"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock dashboard service
        mock_async_sync.return_value = {
            'dashboard_data': {
                'portfolio': {'total_value': 115000.0},
                'market': {'quotes': {}},
                'risk': {'risk_score': 'LOW'}
            },
            'timestamp': timezone.now().isoformat(),
            'user_id': self.user.id
        }
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url, {'symbols': ['AAPL', 'MSFT']})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertFalse(data['cached'])
    
    @patch('django.core.cache.cache.get')
    def test_dashboard_data_api_cached_response(self, mock_cache_get):
        """Test dashboard data API with cached response"""
        # Mock cache hit
        cached_data = {
            'dashboard_data': {'portfolio': {'total_value': 115000.0}},
            'timestamp': timezone.now().isoformat()
        }
        mock_cache_get.return_value = cached_data
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['cached'])
    
    @patch('apps.trading_analytics.views.async_to_sync')
    def test_dashboard_data_api_error_handling(self, mock_async_sync):
        """Test dashboard data API error handling"""
        # Mock service error
        mock_async_sync.return_value = None
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        data = response.json()
        self.assertEqual(data['status'], 'error')
    
    @patch('apps.trading_analytics.views.async_to_sync')
    def test_dashboard_summary_api(self, mock_async_sync):
        """Test dashboard summary API endpoint"""
        # Mock service responses
        mock_async_sync.side_effect = [
            {'summary': {'total_value': 115000.0}},  # portfolio
            {'risk_score': 'LOW', 'alerts': {'active_count': 0}},  # risk
            {'current_performance': {'total_return_pct': 15.0}}  # performance
        ]
        
        url = reverse('trading_analytics:dashboard_summary')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('summary', data)
        self.assertIn('portfolio', data['summary'])
        self.assertIn('risk', data['summary'])
        self.assertIn('performance', data['summary'])
    
    @patch('apps.core.websockets.connection_manager.connection_manager.get_metrics')
    @patch('django.core.cache.cache.get')
    def test_dashboard_health_api(self, mock_cache_get, mock_get_metrics):
        """Test dashboard health API endpoint"""
        # Mock cached health data
        mock_cache_get.return_value = {
            'active_connections': 10,
            'last_cleanup': timezone.now().isoformat()
        }
        
        # Mock connection metrics
        mock_get_metrics.return_value = {
            'connections': {'active': 10},
            'messages': {'total_sent': 1000, 'error_rate': 0.01}
        }
        
        url = reverse('trading_analytics:dashboard_health')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('health', data)
        self.assertIn('dashboard_health', data['health'])
        self.assertIn('websocket_metrics', data['health'])
    
    @patch('django.core.cache.cache.set')
    def test_dashboard_configure_api_success(self, mock_cache_set):
        """Test dashboard configuration API success"""
        url = reverse('trading_analytics:dashboard_configure')
        
        config_data = {
            'config': {
                'layout': 'standard',
                'watchlist': ['AAPL', 'MSFT'],
                'show_portfolio': True,
                'theme': 'dark'
            }
        }
        
        response = self.client.post(
            url, 
            data=json.dumps(config_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('config', data)
        
        # Verify cache was set
        mock_cache_set.assert_called_once()
    
    def test_dashboard_configure_api_invalid_layout(self):
        """Test dashboard configuration API with invalid layout"""
        url = reverse('trading_analytics:dashboard_configure')
        
        config_data = {
            'config': {
                'layout': 'invalid_layout',  # Invalid option
                'watchlist': ['AAPL']
            }
        }
        
        response = self.client.post(
            url,
            data=json.dumps(config_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Invalid layout option', data['message'])
    
    @patch('apps.trading_analytics.views.async_to_sync')
    def test_real_time_portfolio_api(self, mock_async_sync):
        """Test real-time portfolio API endpoint"""
        # Mock dashboard service
        mock_async_sync.return_value = {
            'summary': {'total_value': 115000.0},
            'risk_metrics': {'portfolio_var': -2000.0}
        }
        
        url = reverse('trading_analytics:real_time_portfolio')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertIn('portfolio_summary', data['data'])
        self.assertIn('positions', data['data'])
        self.assertIn('real_time_analytics', data['data'])


class TestDashboardAPIQueryParameters(TestCase):
    """Test dashboard API query parameter handling"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get JWT token
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
    
    @patch('apps.trading_analytics.views.async_to_sync')
    @patch('django.core.cache.cache.get')
    def test_dashboard_data_with_symbols_parameter(self, mock_cache_get, mock_async_sync):
        """Test dashboard data API with symbols parameter"""
        mock_cache_get.return_value = None
        mock_async_sync.return_value = {
            'dashboard_data': {'market': {'symbols_count': 2}},
            'timestamp': timezone.now().isoformat()
        }
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url, {
            'symbols': ['AAPL', 'MSFT', 'GOOGL']
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify service was called with correct symbols
        mock_async_sync.assert_called_with(self.user.id, ['AAPL', 'MSFT', 'GOOGL'])
    
    @patch('apps.trading_analytics.views.async_to_sync')
    @patch('django.core.cache.cache.get')
    def test_dashboard_data_without_symbols_parameter(self, mock_cache_get, mock_async_sync):
        """Test dashboard data API without symbols parameter"""
        mock_cache_get.return_value = None
        mock_async_sync.return_value = {
            'dashboard_data': {'market': {'symbols_count': 0}},
            'timestamp': timezone.now().isoformat()
        }
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify service was called with empty symbols list
        mock_async_sync.assert_called_with(self.user.id, [])


class TestDashboardAPIErrorHandling(TestCase):
    """Test dashboard API error handling"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get JWT token
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
    
    @patch('apps.trading_analytics.views.async_to_sync')
    def test_dashboard_api_service_exception(self, mock_async_sync):
        """Test API handling of service exceptions"""
        # Mock service exception
        mock_async_sync.side_effect = Exception("Service unavailable")
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('message', data)
    
    def test_dashboard_configure_invalid_json(self):
        """Test dashboard configure API with invalid JSON"""
        url = reverse('trading_analytics:dashboard_configure')
        
        response = self.client.post(
            url,
            data="invalid json",
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_dashboard_configure_missing_config(self):
        """Test dashboard configure API with missing config"""
        url = reverse('trading_analytics:dashboard_configure')
        
        response = self.client.post(
            url,
            data=json.dumps({}),  # No config field
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestDashboardAPICaching(TestCase):
    """Test dashboard API caching behavior"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get JWT token
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
    
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    @patch('apps.trading_analytics.views.async_to_sync')
    def test_dashboard_data_cache_behavior(self, mock_async_sync, mock_cache_set, mock_cache_get):
        """Test dashboard data caching behavior"""
        # First request - cache miss
        mock_cache_get.return_value = None
        mock_async_sync.return_value = {
            'dashboard_data': {'test': 'data'},
            'timestamp': timezone.now().isoformat()
        }
        
        url = reverse('trading_analytics:dashboard_data')
        response = self.client.get(url)
        
        # Should have called service and set cache
        mock_async_sync.assert_called_once()
        mock_cache_set.assert_called_once()
        
        data = response.json()
        self.assertFalse(data['cached'])
        
        # Second request - cache hit
        mock_cache_get.return_value = {'cached': 'data'}
        mock_async_sync.reset_mock()
        
        response = self.client.get(url)
        
        # Should not have called service again
        mock_async_sync.assert_not_called()
        
        data = response.json()
        self.assertTrue(data['cached'])
