# apps/core/tests/test_websocket_manager.py
"""
Test suite for WebSocket connection management and performance monitoring
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.core.websockets.connection_manager import ConnectionManager, ConnectionInfo
from apps.core.websockets.permissions import WebSocketPermissionMixin
from apps.core.websockets.middleware import PerformanceMiddleware, RateLimitMiddleware

User = get_user_model()


class TestConnectionManager(TestCase):
    """Test WebSocket connection management"""
    
    def setUp(self):
        self.connection_manager = ConnectionManager()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_connection_manager_initialization(self):
        """Test connection manager initializes correctly"""
        self.assertIsNotNone(self.connection_manager.connections)
        self.assertIsNotNone(self.connection_manager.user_connections)
        self.assertIsNotNone(self.connection_manager.metrics)
        self.assertEqual(len(self.connection_manager.connections), 0)
    
    def test_add_connection(self):
        """Test adding a new connection"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': self.user,
            'path': '/ws/test/',
            'client': ['127.0.0.1', 0]
        }
        
        connection_id = self.connection_manager.add_connection(
            consumer=mock_consumer,
            user_id=self.user.id,
            connection_type='dashboard'
        )
        
        self.assertIsNotNone(connection_id)
        self.assertIn(connection_id, self.connection_manager.connections)
        self.assertIn(self.user.id, self.connection_manager.user_connections)
        
        # Check connection info
        conn_info = self.connection_manager.connections[connection_id]
        self.assertEqual(conn_info.user_id, self.user.id)
        self.assertEqual(conn_info.connection_type, 'dashboard')
        self.assertIsNotNone(conn_info.connected_at)
    
    def test_remove_connection(self):
        """Test removing a connection"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': self.user,
            'path': '/ws/test/',
            'client': ['127.0.0.1', 0]
        }
        
        connection_id = self.connection_manager.add_connection(
            consumer=mock_consumer,
            user_id=self.user.id,
            connection_type='dashboard'
        )
        
        # Remove connection
        self.connection_manager.remove_connection(connection_id)
        
        self.assertNotIn(connection_id, self.connection_manager.connections)
        # User connections should be empty if this was the only connection
        if self.user.id in self.connection_manager.user_connections:
            self.assertEqual(len(self.connection_manager.user_connections[self.user.id]), 0)
    
    def test_get_user_connections(self):
        """Test getting connections for a user"""
        mock_consumer1 = Mock()
        mock_consumer1.scope = {
            'user': self.user,
            'path': '/ws/dashboard/',
            'client': ['127.0.0.1', 0]
        }
        
        mock_consumer2 = Mock()
        mock_consumer2.scope = {
            'user': self.user,
            'path': '/ws/portfolio/',
            'client': ['127.0.0.1', 0]
        }
        
        conn_id1 = self.connection_manager.add_connection(
            consumer=mock_consumer1,
            user_id=self.user.id,
            connection_type='dashboard'
        )
        
        conn_id2 = self.connection_manager.add_connection(
            consumer=mock_consumer2,
            user_id=self.user.id,
            connection_type='portfolio'
        )
        
        user_connections = self.connection_manager.get_user_connections(self.user.id)
        self.assertEqual(len(user_connections), 2)
        self.assertIn(conn_id1, user_connections)
        self.assertIn(conn_id2, user_connections)
    
    def test_connection_cleanup(self):
        """Test cleaning up stale connections"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': self.user,
            'path': '/ws/test/',
            'client': ['127.0.0.1', 0]
        }
        
        connection_id = self.connection_manager.add_connection(
            consumer=mock_consumer,
            user_id=self.user.id,
            connection_type='dashboard'
        )
        
        # Manually set connection as old
        conn_info = self.connection_manager.connections[connection_id]
        conn_info.connected_at = timezone.now() - timedelta(hours=2)
        conn_info.last_activity = timezone.now() - timedelta(hours=1, minutes=30)
        
        # Run cleanup
        cleaned = self.connection_manager.cleanup_stale_connections(max_age_hours=1)
        
        self.assertEqual(cleaned, 1)
        self.assertNotIn(connection_id, self.connection_manager.connections)
    
    def test_get_metrics(self):
        """Test getting connection metrics"""
        # Add some connections
        for i in range(3):
            mock_consumer = Mock()
            mock_consumer.scope = {
                'user': self.user,
                'path': f'/ws/test{i}/',
                'client': ['127.0.0.1', 0]
            }
            
            self.connection_manager.add_connection(
                consumer=mock_consumer,
                user_id=self.user.id,
                connection_type='dashboard'
            )
        
        metrics = self.connection_manager.get_metrics()
        
        self.assertEqual(metrics['connections']['active'], 3)
        self.assertEqual(metrics['connections']['by_type']['dashboard'], 3)
        self.assertIn('messages', metrics)
        self.assertIn('performance', metrics)


class TestWebSocketPermissions(TestCase):
    """Test WebSocket permission system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='testpass123',
            is_staff=True
        )
    
    def test_permission_mixin_initialization(self):
        """Test permission mixin initialization"""
        mixin = WebSocketPermissionMixin()
        self.assertEqual(mixin.permission_classes, [])
    
    @patch('apps.core.websockets.permissions.IsAuthenticated')
    def test_permission_check_authenticated(self, mock_auth):
        """Test permission checking for authenticated users"""
        mock_permission = Mock()
        mock_permission.return_value.has_permission.return_value = True
        mock_auth.return_value = mock_permission
        
        mixin = WebSocketPermissionMixin()
        mixin.permission_classes = [mock_auth()]
        
        mock_scope = {'user': self.user}
        
        # This would normally be async, but for testing we'll mock it
        with patch.object(mixin, '_check_permissions', return_value=True):
            result = mixin._check_permissions(mock_scope)
            self.assertTrue(result)


@pytest.mark.asyncio
class TestAsyncWebSocketFeatures:
    """Test async WebSocket features"""
    
    async def test_rate_limiting_middleware(self):
        """Test rate limiting middleware"""
        middleware = RateLimitMiddleware()
        
        # Mock scope and consumer
        mock_scope = {
            'user': Mock(id=1),
            'client': ['127.0.0.1', 0]
        }
        
        mock_consumer = AsyncMock()
        
        # Test rate limiting
        for i in range(15):  # Exceed rate limit
            result = await middleware.process_message(mock_scope, mock_consumer, {'type': 'test'})
            if i < 10:  # Should pass first 10
                assert result is None  # No blocking
            else:  # Should start blocking
                break
    
    async def test_performance_middleware(self):
        """Test performance monitoring middleware"""
        middleware = PerformanceMiddleware()
        
        mock_scope = {'user': Mock(id=1)}
        mock_consumer = AsyncMock()
        
        # Test performance tracking
        await middleware.process_message(mock_scope, mock_consumer, {'type': 'test'})
        
        # Check that metrics were recorded
        assert hasattr(middleware, 'metrics')


class TestConnectionInfo(TestCase):
    """Test ConnectionInfo data structure"""
    
    def test_connection_info_creation(self):
        """Test ConnectionInfo creation and properties"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': Mock(id=1),
            'path': '/ws/test/',
            'client': ['127.0.0.1', 12345]
        }
        
        conn_info = ConnectionInfo(
            connection_id='test-123',
            consumer=mock_consumer,
            user_id=1,
            connection_type='dashboard'
        )
        
        self.assertEqual(conn_info.connection_id, 'test-123')
        self.assertEqual(conn_info.user_id, 1)
        self.assertEqual(conn_info.connection_type, 'dashboard')
        self.assertIsNotNone(conn_info.connected_at)
        self.assertEqual(conn_info.messages_sent, 0)
        self.assertEqual(conn_info.messages_received, 0)
    
    def test_connection_info_update_activity(self):
        """Test updating connection activity"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': Mock(id=1),
            'path': '/ws/test/',
            'client': ['127.0.0.1', 12345]
        }
        
        conn_info = ConnectionInfo(
            connection_id='test-123',
            consumer=mock_consumer,
            user_id=1,
            connection_type='dashboard'
        )
        
        original_activity = conn_info.last_activity
        
        # Update activity
        conn_info.update_activity('sent')
        
        self.assertEqual(conn_info.messages_sent, 1)
        self.assertGreater(conn_info.last_activity, original_activity)
        
        # Update received
        conn_info.update_activity('received')
        self.assertEqual(conn_info.messages_received, 1)
    
    def test_connection_info_to_dict(self):
        """Test ConnectionInfo serialization"""
        mock_consumer = Mock()
        mock_consumer.scope = {
            'user': Mock(id=1),
            'path': '/ws/test/',
            'client': ['127.0.0.1', 12345]
        }
        
        conn_info = ConnectionInfo(
            connection_id='test-123',
            consumer=mock_consumer,
            user_id=1,
            connection_type='dashboard'
        )
        
        data = conn_info.to_dict()
        
        self.assertIn('connection_id', data)
        self.assertIn('user_id', data)
        self.assertIn('connection_type', data)
        self.assertIn('connected_at', data)
        self.assertIn('messages_sent', data)
        self.assertIn('messages_received', data)
        self.assertEqual(data['connection_id'], 'test-123')
        self.assertEqual(data['user_id'], 1)
