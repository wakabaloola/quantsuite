# apps/trading_simulation/tests/test_websocket_auth.py
import pytest
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from apps.trading_simulation.consumers import OrderUpdatesConsumer
from apps.trading_simulation.middleware import JWTAuthMiddlewareStack

User = get_user_model()

class WebSocketAuthenticationTests(TransactionTestCase):
    """Test WebSocket JWT authentication middleware"""
    
    def setUp(self):
        """Set up test user and tokens"""
        self.user = User.objects.create_user(
            username='authuser',
            email='auth@test.com',
            password='authpass123'
        )
        
        self.refresh = RefreshToken.for_user(self.user)
        self.access_token = str(self.refresh.access_token)
        
        # Create authenticated application
        self.application = JWTAuthMiddlewareStack(
            URLRouter([
                re_path(r'ws/trading/orders/(?P<user_id>\w+)/$', 
                       OrderUpdatesConsumer.as_asgi()),
            ])
        )

    async def test_websocket_jwt_authentication_success(self):
        """Test successful JWT authentication"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.user.id}/?token={self.access_token}'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        await communicator.disconnect()

    async def test_websocket_jwt_authentication_failure(self):
        """Test JWT authentication failure with invalid token"""
        invalid_token = 'invalid.jwt.token'
        
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.user.id}/?token={invalid_token}'
        )
        
        # Should still connect but with AnonymousUser
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        await communicator.disconnect()

    async def test_websocket_no_token(self):
        """Test WebSocket connection without token"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.user.id}/'
        )
        
        # Should connect with AnonymousUser
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        await communicator.disconnect()

    async def test_websocket_expired_token(self):
        """Test WebSocket connection with expired token"""
        # Create an expired token
        expired_refresh = RefreshToken.for_user(self.user)
        expired_refresh.set_exp(lifetime=-1)  # Expired 1 second ago
        expired_token = str(expired_refresh.access_token)
        
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.user.id}/?token={expired_token}'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)  # Should connect but not authenticated
        
        await communicator.disconnect()
