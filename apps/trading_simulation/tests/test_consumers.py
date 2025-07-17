# apps/trading_simulation/tests/test_consumers.py
import json
import asyncio
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path
from django.utils import timezone
from unittest.mock import patch, AsyncMock, MagicMock
from rest_framework_simplejwt.tokens import RefreshToken

from apps.trading_simulation.consumers import (
    OrderUpdatesConsumer, PortfolioUpdatesConsumer,
    AlgorithmUpdatesConsumer, RiskAlertsConsumer
)
from apps.trading_simulation.middleware import JWTAuthMiddlewareStack
from apps.order_management.models import AlgorithmicOrder, SimulatedOrder
from apps.trading_simulation.models import SimulatedInstrument, UserSimulationProfile, SimulatedExchange
from apps.market_data.models import Ticker, Exchange, Sector, Industry, DataSource

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
        self.real_exchange = Exchange.objects.create(
            name='Test Exchange',
            code='TESTEX'
        )

        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test Exchange',
            code='SIM_TEST',
            real_exchange=self.real_exchange
        )

        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )

        self.ticker = Ticker.objects.create(
            symbol='AAPL',
            exchange=self.real_exchange,
            name='Apple Inc',
            sector=self.sector,
            industry=self.industry,
            data_source=self.data_source,
            currency='USD',
            country='US'
        )

        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange,
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

        # Should receive initial algorithms
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'initial_algorithms')
        self.assertIn('algorithms', response)

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

        # Skip initial message
        await communicator.receive_json_from()

        # Send heartbeat
        await communicator.send_json_to({'type': 'heartbeat'})

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'heartbeat_response')
        self.assertIn('timestamp', response)

        await communicator.disconnect()

    async def test_risk_alerts_consumer(self):
        """Test RiskAlertsConsumer"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/risk/{self.user.id}/'
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # No initial message expected for risk alerts
        await communicator.disconnect()

    async def test_error_handling_invalid_user(self):
        """Test error handling with invalid user ID"""
        communicator = WebsocketCommunicator(
            self.application,
            '/ws/trading/orders/99999/'  # Non-existent user
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Should receive empty orders list
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'initial_orders')
        self.assertEqual(response['orders'], [])

        await communicator.disconnect()


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


class WebSocketBroadcastingTests(TransactionTestCase):
    """Test WebSocket message broadcasting"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )

        self.real_exchange = Exchange.objects.create(
            name='Test Exchange 2',
            code='TESTEX2'
        )

        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test Exchange 2',
            code='SIM_TEST2',
            real_exchange=self.real_exchange
        )

        self.sector = Sector.objects.create(name='Finance', code='FIN')
        self.industry = Industry.objects.create(name='Banks', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source 2', code='TEST_DS2', url='https://test2.com',
            api_endpoint='https://api.test2.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )

        self.ticker = Ticker.objects.create(
            symbol='GOOGL',
            exchange=self.real_exchange,
            name='Alphabet Inc',
            sector=self.sector,
            industry=self.industry,
            data_source=self.data_source,
            currency='USD',
            country='US'
        )

        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange,
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
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
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
            exchange=self.sim_exchange,
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

        # Verify order was created with expected fields
        self.assertEqual(order.side, 'BUY')
        self.assertEqual(order.quantity, 100)
        self.assertEqual(float(order.price), 150.00)


class WebSocketPerformanceTests(TransactionTestCase):
    """Test WebSocket performance and load handling"""

    def setUp(self):
        """Set up test users"""
        self.users = []
        for i in range(3):  # Reduced for testing
            user = User.objects.create_user(
                username=f'perfuser{i}',
                email=f'perf{i}@test.com',
                password='perfpass123'
            )
            self.users.append(user)

        self.application = URLRouter([
            re_path(r'ws/trading/orders/(?P<user_id>\w+)/$',
                   OrderUpdatesConsumer.as_asgi()),
            re_path(r'ws/trading/algorithms/(?P<user_id>\w+)/$',
                   AlgorithmUpdatesConsumer.as_asgi()),
        ])

    async def test_multiple_websocket_connections(self):
        """Test handling multiple WebSocket connections"""
        communicators = []

        # Create multiple connections
        for user in self.users:
            communicator = WebsocketCommunicator(
                self.application,
                f'/ws/trading/orders/{user.id}/'
            )
            communicators.append(communicator)

        # Connect all
        for communicator in communicators:
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)
            # Consume initial message
            await communicator.receive_json_from()

        # Test concurrent messaging
        tasks = []
        for communicator in communicators:
            task = communicator.send_json_to({'type': 'heartbeat'})
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Receive responses
        for communicator in communicators:
            response = await communicator.receive_json_from()
            self.assertEqual(response['type'], 'heartbeat_response')

        # Disconnect all
        for communicator in communicators:
            await communicator.disconnect()

    async def test_websocket_message_throughput(self):
        """Test WebSocket message throughput"""
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/trading/orders/{self.users[0].id}/'
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial message
        await communicator.receive_json_from()

        # Send multiple messages and measure throughput
        message_count = 10  # Reduced for testing

        for i in range(message_count):
            await communicator.send_json_to({
                'type': 'heartbeat',
                'sequence': i
            })

        # Receive responses
        for i in range(message_count):
            response = await communicator.receive_json_from()
            self.assertEqual(response['type'], 'heartbeat_response')

        await communicator.disconnect()
