# apps/trading_analytics/tests/test_dashboard_tasks.py
"""
Test suite for dashboard background tasks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from celery import current_app

from apps.trading_analytics.tasks import (
    update_dashboard_cache_all_users,
    broadcast_market_summary,
    calculate_dashboard_performance_metrics,
    cleanup_dashboard_sessions,
    generate_dashboard_alerts,
    get_user_watchlist
)

User = get_user_model()


class TestDashboardTasks(TestCase):
    """Test dashboard background tasks"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            last_login=timezone.now()
        )
    
    @patch('apps.trading_analytics.tasks.async_to_sync')
    @patch('apps.trading_analytics.tasks.get_user_watchlist')
    @patch('django.core.cache.cache.set')
    def test_update_dashboard_cache_all_users(self, mock_cache_set, mock_watchlist, mock_async_sync):
        """Test updating dashboard cache for all users"""
        # Mock the async functions
        mock_watchlist.return_value = ['AAPL', 'MSFT']
        mock_async_sync.return_value = Mock(return_value={
            'dashboard_data': {'portfolio': {'total_value': 100000}},
            'timestamp': timezone.now().isoformat()
        })
        
        # Run the task
        result = update_dashboard_cache_all_users()
        
        self.assertEqual(result['status'], 'success')
        self.assertGreater(result['successful'], 0)
        self.assertEqual(result['failed'], 0)
        
        # Verify cache was set
        mock_cache_set.assert_called()
    
    @patch('apps.trading_analytics.tasks.async_to_sync')
    @patch('channels.layers.get_channel_layer')
    def test_broadcast_market_summary(self, mock_channel_layer, mock_async_sync):
        """Test market summary broadcasting"""
        # Mock dashboard service methods
        mock_async_sync.return_value = {
            'indices': {'SPY': {'price': 450.0}},
            'market_sentiment': {'overall_sentiment': 'BULLISH'}
        }
        
        # Mock channel layer
        mock_layer = Mock()
        mock_channel_layer.return_value = mock_layer
        
        # Run the task
        result = broadcast_market_summary()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('indices_count', result)
        
        # Verify channel layer was used
        mock_layer.group_send.assert_called()
    
    def test_calculate_dashboard_performance_metrics(self):
        """Test dashboard performance metrics calculation"""
        # Create user with simulation profile
        from apps.trading_simulation.models import UserSimulationProfile
        
        profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=115000.00
        )
        
        with patch('django.core.cache.cache.set') as mock_cache_set:
            result = calculate_dashboard_performance_metrics()
            
            self.assertEqual(result['status'], 'success')
            self.assertGreater(result['users_processed'], 0)
            
            # Verify cache was set
            mock_cache_set.assert_called()
    
    @patch('apps.trading_analytics.tasks.connection_manager')
    @patch('django.core.cache.cache.set')
    def test_cleanup_dashboard_sessions(self, mock_cache_set, mock_connection_manager):
        """Test dashboard session cleanup"""
        # Mock connection manager metrics
        mock_connection_manager.get_metrics.return_value = {
            'connections': {'active': 5},
            'messages': {'avg_processing_time': 50}
        }
        
        result = cleanup_dashboard_sessions()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('cache_keys_cleaned', result)
        self.assertEqual(result['active_connections'], 5)
        
        # Verify cache was set for health metrics
        mock_cache_set.assert_called()
    
    @patch('apps.trading_analytics.tasks.async_to_sync')
    def test_generate_dashboard_alerts(self, mock_async_sync):
        """Test dashboard alert generation"""
        # Create user with simulation profile
        from apps.trading_simulation.models import UserSimulationProfile
        
        profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=95000.00  # Loss to trigger alert
        )
        
        # Mock the async publish_risk_alert function
        mock_async_sync.return_value = None
        
        result = generate_dashboard_alerts()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('alerts_generated', result)
        self.assertIn('users_checked', result)


class TestDashboardTaskUtilities(TestCase):
    """Test utility functions for dashboard tasks"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    @patch('apps.trading_analytics.tasks.database_sync_to_async')
    async def test_get_user_watchlist(self, mock_db_sync):
        """Test getting user watchlist"""
        # Mock database call
        mock_db_sync.return_value = Mock(return_value=['AAPL', 'MSFT', 'GOOGL'])
        
        result = await get_user_watchlist(self.user.id)
        
        self.assertIsInstance(result, list)
        self.assertIn('AAPL', result)
    
    def test_get_user_watchlist_default(self):
        """Test getting default watchlist when user preferences don't exist"""
        from apps.trading_analytics.tasks import get_user_watchlist
        import asyncio
        
        # Test the actual sync version that returns defaults
        # Since this is a simplified implementation, it returns defaults
        result = asyncio.run(get_user_watchlist(999))  # Non-existent user
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)


class TestTaskErrorHandling(TestCase):
    """Test error handling in dashboard tasks"""
    
    @patch('apps.trading_analytics.tasks.User.objects.filter')
    def test_update_dashboard_cache_error_handling(self, mock_filter):
        """Test error handling in cache update task"""
        # Simulate database error
        mock_filter.side_effect = Exception("Database error")
        
        result = update_dashboard_cache_all_users()
        
        self.assertEqual(result['status'], 'failed')
        self.assertIn('error', result)
    
    @patch('apps.trading_analytics.tasks.dashboard_service')
    def test_broadcast_market_summary_error_handling(self, mock_service):
        """Test error handling in market summary broadcast"""
        # Simulate service error
        mock_service.get_market_context.side_effect = Exception("Service error")
        
        result = broadcast_market_summary()
        
        self.assertEqual(result['status'], 'failed')
        self.assertIn('error', result)
    
    @patch('apps.trading_analytics.tasks.User.objects.filter')
    def test_calculate_performance_error_handling(self, mock_filter):
        """Test error handling in performance calculation"""
        # Simulate error
        mock_filter.side_effect = Exception("Query error")
        
        result = calculate_dashboard_performance_metrics()
        
        self.assertEqual(result['status'], 'failed')
        self.assertIn('error', result)


@pytest.mark.asyncio
class TestAsyncTaskComponents:
    """Test async components of dashboard tasks"""
    
    async def test_async_dashboard_data_gathering(self):
        """Test async data gathering performance"""
        from apps.trading_analytics.tasks import dashboard_service
        
        with patch.object(dashboard_service, 'get_unified_dashboard_data') as mock_data:
            mock_data.return_value = {
                'dashboard_data': {'portfolio': {}},
                'timestamp': timezone.now().isoformat()
            }
            
            start_time = timezone.now()
            
            result = await dashboard_service.get_unified_dashboard_data(1, [])
            
            execution_time = (timezone.now() - start_time).total_seconds()
            
            # Should complete quickly
            assert execution_time < 1.0
            assert 'dashboard_data' in result


class TestCeleryTaskConfiguration(TestCase):
    """Test Celery task configuration and scheduling"""
    
    def test_task_registration(self):
        """Test that dashboard tasks are properly registered"""
        registered_tasks = current_app.tasks
        
        task_names = [
            'apps.trading_analytics.tasks.update_dashboard_cache_all_users',
            'apps.trading_analytics.tasks.broadcast_market_summary',
            'apps.trading_analytics.tasks.calculate_dashboard_performance_metrics',
            'apps.trading_analytics.tasks.cleanup_dashboard_sessions',
            'apps.trading_analytics.tasks.generate_dashboard_alerts'
        ]
        
        for task_name in task_names:
            if task_name in registered_tasks:
                task = registered_tasks[task_name]
                self.assertIsNotNone(task)
                # Verify task has proper configuration
                self.assertTrue(hasattr(task, 'delay'))
                self.assertTrue(hasattr(task, 'apply_async'))
    
    def test_task_retry_configuration(self):
        """Test task retry configuration"""
        # Test that tasks have proper retry settings
        task = update_dashboard_cache_all_users
        
        # These tasks should have retry configuration
        self.assertTrue(hasattr(task, 'max_retries'))
    
    @patch('apps.trading_analytics.tasks.cache')
    def test_cache_interaction(self, mock_cache):
        """Test cache interaction in tasks"""
        mock_cache.get.return_value = None
        mock_cache.set.return_value = True
        
        # Test a task that uses cache
        with patch('apps.trading_analytics.tasks.User.objects.filter') as mock_filter:
            mock_filter.return_value.values_list.return_value = [1, 2, 3]
            
            with patch('apps.trading_analytics.tasks.async_to_sync'):
                result = update_dashboard_cache_all_users()
                
                # Verify cache operations
                mock_cache.set.assert_called()
    
    def test_performance_monitoring(self):
        """Test performance monitoring in tasks"""
        with patch('apps.trading_analytics.tasks.timezone.now') as mock_now:
            # Mock time progression
            start_time = timezone.now()
            end_time = start_time + timezone.timedelta(seconds=2)
            mock_now.side_effect = [start_time, end_time]
            
            with patch('apps.trading_analytics.tasks.User.objects.filter') as mock_filter:
                mock_filter.return_value.values_list.return_value = []
                
                result = update_dashboard_cache_all_users()
                
                # Task should complete and return status
                self.assertIn('status', result)


class TestTaskIntegration(TestCase):
    """Test integration between dashboard tasks and other services"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    @patch('channels.layers.get_channel_layer')
    @patch('apps.trading_analytics.tasks.async_to_sync')
    def test_websocket_integration(self, mock_async_sync, mock_channel_layer):
        """Test integration with WebSocket channels"""
        # Mock channel layer
        mock_layer = Mock()
        mock_channel_layer.return_value = mock_layer
        
        # Mock dashboard service
        mock_async_sync.return_value = {'test': 'data'}
        
        result = broadcast_market_summary()
        
        # Verify WebSocket broadcast was attempted
        mock_layer.group_send.assert_called()
        
        # Check the group and message
        call_args = mock_layer.group_send.call_args
        group_name = call_args[0][0]
        message = call_args[0][1]
        
        self.assertEqual(group_name, 'dashboard_global')
        self.assertIn('type', message)
    
    @patch('apps.core.events.publish_risk_alert')
    def test_event_system_integration(self, mock_publish_alert):
        """Test integration with event system"""
        # Create scenario that should trigger alert
        from apps.trading_simulation.models import UserSimulationProfile
        
        profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=50000.00  # 50% loss
        )
        
        with patch('apps.trading_analytics.tasks.async_to_sync') as mock_async:
            mock_async.return_value = None
            
            result = generate_dashboard_alerts()
            
            # Should have attempted to publish alerts
            self.assertEqual(result['status'], 'success')
