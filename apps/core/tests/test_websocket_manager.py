# apps/core/tests/test_websocket_manager.py
"""
UPDATED Test suite for WebSocket connection management.
This version is compatible with all Django versions and tests async functionality.
"""

import asyncio
from unittest.mock import Mock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.core.websockets.connection_manager import connection_manager, ConnectionInfo

User = get_user_model()


class TestConnectionManager(TestCase):
    """Test WebSocket connection management with async methods."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        # Reset the global connection_manager state before each test
        connection_manager.connections.clear()
        connection_manager.user_connections.clear()
        connection_manager.metrics.active_connections = 0
        connection_manager.metrics.total_connections = 0
        connection_manager.metrics.authenticated_connections = 0

    def run_async(self, coro):
        """Helper function to run async code in a sync test."""
        # 🔥 FIX: Get a new event loop for each async test run
        return asyncio.run(coro)

    def test_register_connection(self):
        """Test registering a new connection."""
        channel_name = "test_channel_1"
        
        success = self.run_async(connection_manager.register_connection(
            channel_name=channel_name,
            user_id=self.user.id,
            consumer_type='dashboard'
        ))
        
        self.assertTrue(success)
        self.assertIn(channel_name, connection_manager.connections)
        self.assertIn(channel_name, connection_manager.user_connections[self.user.id])
        
        conn_info = connection_manager.connections[channel_name]
        self.assertEqual(conn_info.user_id, self.user.id)
        self.assertEqual(conn_info.consumer_type, 'dashboard')
        self.assertEqual(connection_manager.metrics.active_connections, 1)

    def test_unregister_connection(self):
        """Test unregistering a connection."""
        channel_name = "test_channel_2"
        self.run_async(connection_manager.register_connection(
            channel_name=channel_name,
            user_id=self.user.id,
            consumer_type='dashboard'
        ))
        
        self.assertIn(channel_name, connection_manager.connections)
        
        self.run_async(connection_manager.unregister_connection(channel_name))
        
        self.assertNotIn(channel_name, connection_manager.connections)
        self.assertNotIn(self.user.id, connection_manager.user_connections)
        self.assertEqual(connection_manager.metrics.active_connections, 0)

    def test_get_user_connections_info(self):
        """Test getting connection info for a specific user."""
        self.run_async(connection_manager.register_connection("ch_1", self.user.id, "dashboard"))
        self.run_async(connection_manager.register_connection("ch_2", self.user.id, "portfolio"))
        
        user_conns = connection_manager.get_user_connections(self.user.id)
        
        self.assertEqual(len(user_conns), 2)
        types = {conn['consumer_type'] for conn in user_conns}
        self.assertEqual(types, {'dashboard', 'portfolio'})

    def test_cleanup_stale_connections(self):
        """Test that stale connections are cleaned up correctly."""
        channel_name = "stale_channel"
        self.run_async(connection_manager.register_connection(channel_name, self.user.id))
        
        # Manually make the connection stale
        conn_info = connection_manager.connections[channel_name]
        conn_info.last_activity = timezone.now() - timedelta(seconds=connection_manager.heartbeat_timeout + 1)
        
        self.run_async(connection_manager.cleanup_stale_connections())
        
        self.assertNotIn(channel_name, connection_manager.connections)
        self.assertEqual(connection_manager.metrics.active_connections, 0)

