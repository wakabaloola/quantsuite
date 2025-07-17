# apps/trading_simulation/tests/test_websocket_consumers.py
import json
import pytest
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path
from unittest.mock import patch, AsyncMock

from apps.trading_simulation.consumers import (
    OrderUpdatesConsumer, PortfolioUpdatesConsumer, 
    AlgorithmUpdatesConsumer, RiskAlertsConsumer
)
from apps.trading_simulation.middleware import JWTAuthMiddlewareStack
from apps.order_management.models import AlgorithmicOrder, SimulatedOrder
from apps.trading_simulation.models import SimulatedInstrument, UserSimulationProfile
from apps.market_data.models import Ticker, Exchange

User = get_user_model()

class WebSocketConsumerTests(TransactionTestCase):
    """Test WebSocket consumers functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test market data
        self.exchange = Exchange.objects.create(
            name='Test Exchange',
            symbol='TESTEX',
            timezone='UTC'
        )
        
        self.ticker = Ticker.objects.create(
            symbol='AAPL',
            exchange=self.exchange,
            name='Apple Inc'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            is_active=True
        )
        
        # Create simulation profile
        self.profile = UserSimulationProfile.objects.create(
            user=self.user,
            virtual_cash_balance=100000
        )
        
        # WebSocket application for testing
        self.application = URLRouter([
            re_path(r'ws/trading/orders/(?P<user_id>\w+)/$', OrderUpdatesConsumer.as_asgi()),
            re_path(r'ws/trading/algorithms/(?P<user_id>\w+)/$', AlgorithmUpdatesConsumer.as_asgi()),
            re_path(r'ws/trading/portfolio/(?P<user_id>\w+)/$', PortfolioUpdatesConsumer.as_asgi()),
            re_path(r'ws/trading/risk/(?P<user_id>\w+)/$', RiskAlertsConsumer.as_asgi()),
        ])

    async def test_order_updates_consumer_connection(self):
        """Test OrderUpdatesConsumer connection and initial data"""
        communicator = WebsocketCommunicator(
            self.application, 
            f'/ws/trading/orders/{self.user.id}/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Should receive initial orders
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'initial_orders')
        self.assertIn('orders', response)
        
        await communicator.disconnect()

    async def test_algorithm_updates_consumer_lifecycle(self):
        """Test AlgorithmUpdatesConsumer with algorithm lifecycle"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/algorithms/{self.user.id}/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Test subscription message
        await communicator.send_json_to({
            'type': 'subscribe_algorithms'
        })
        
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'initial_algorithms')
        
        await communicator.disconnect()

    async def test_portfolio_updates_consumer(self):
        """Test PortfolioUpdatesConsumer"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/portfolio/{self.user.id}/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Should receive initial portfolio
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'initial_portfolio')
        self.assertIn('portfolio', response)
        
        await communicator.disconnect()

    async def test_heartbeat_mechanism(self):
        """Test heartbeat functionality"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.user.id}/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Send heartbeat
        await communicator.send_json_to({'type': 'heartbeat'})
        
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'heartbeat_response')
        self.assertIn('timestamp', response)
        
        await communicator.disconnect()

    async def test_error_handling(self):
        """Test error handling in consumers"""
        # Test with invalid user ID
        communicator = WebsocketCommunicator(
            self.application,
            '/ws/trading/orders/invalid_user/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Should handle gracefully
        await communicator.disconnect()

class WebSocketBroadcastingTests(TransactionTestCase):
    """Test WebSocket message broadcasting"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        self.exchange = Exchange.objects.create(
            name='Test Exchange 2',
            symbol='TESTEX2',
            timezone='UTC'
        )
        
        self.ticker = Ticker.objects.create(
            symbol='GOOGL',
            exchange=self.exchange,
            name='Alphabet Inc'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            is_active=True
        )

    @patch('channels.layers.get_channel_layer')
    def test_algorithm_update_broadcasting(self, mock_channel_layer):
        """Test algorithm update broadcasting"""
        # Mock channel layer
        mock_layer = AsyncMock()
        mock_channel_layer.return_value = mock_layer
        
        # Create algorithmic order
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            algorithm_parameters={'slice_count': 10}
        )
        
        # Import the broadcasting function
        from apps.order_management.algorithm_services import AlgorithmExecutionEngine
        engine = AlgorithmExecutionEngine()
        
        # Test broadcasting
        engine._broadcast_algorithm_update(algo_order, 'STARTED')
        
        # Verify calls were made
        self.assertTrue(mock_layer.group_send.called)
        
    def test_order_update_message_format(self):
        """Test order update message format"""
        order = SimulatedOrder.objects.create(
            user=self.user,
            exchange=self.exchange,
            instrument=self.instrument,
            side='BUY',
            order_type='LIMIT',
            quantity=100,
            price=150.00
        )
        
        # Test message formatting
        expected_fields = [
            'order_id', 'symbol', 'side', 'quantity', 
            'price', 'status', 'timestamp'
        ]
        
        # This would test the actual message format
        # when implemented in the broadcasting logic
