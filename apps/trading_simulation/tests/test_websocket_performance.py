# apps/trading_simulation/tests/test_websocket_performance.py
import asyncio
import time
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path
from unittest.mock import patch, MagicMock

from apps.trading_simulation.consumers import (
    OrderUpdatesConsumer, AlgorithmUpdatesConsumer
)

User = get_user_model()

class WebSocketPerformanceTests(TransactionTestCase):
    """Test WebSocket performance and load handling"""
    
    def setUp(self):
        """Set up test users"""
        self.users = []
        for i in range(5):
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
        start_time = time.time()
        
        for communicator in communicators:
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)
        
        connect_time = time.time() - start_time
        print(f"Connected {len(communicators)} WebSockets in {connect_time:.2f}s")
        
        # Test concurrent messaging
        start_time = time.time()
        
        tasks = []
        for communicator in communicators:
            task = communicator.send_json_to({'type': 'heartbeat'})
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        message_time = time.time() - start_time
        print(f"Sent {len(tasks)} messages in {message_time:.2f}s")
        
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
        
        # Send multiple messages and measure throughput
        message_count = 100
        start_time = time.time()
        
        for i in range(message_count):
            await communicator.send_json_to({
                'type': 'heartbeat',
                'sequence': i
            })
        
        # Receive responses
        for i in range(message_count):
            response = await communicator.receive_json_from()
            self.assertEqual(response['type'], 'heartbeat_response')
        
        total_time = time.time() - start_time
        throughput = (message_count * 2) / total_time  # Send + receive
        
        print(f"WebSocket throughput: {throughput:.2f} messages/second")
        self.assertGreater(throughput, 50)  # Should handle at least 50 msg/s
        
        await communicator.disconnect()

    async def test_websocket_memory_usage(self):
        """Test WebSocket memory usage with long-running connections"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        communicators = []
        
        # Create many connections
        for user in self.users:
            for endpoint in ['orders', 'algorithms']:
                communicator = WebsocketCommunicator(
                    self.application,
                    f'/ws/trading/{endpoint}/{user.id}/'
                )
                connected, subprotocol = await communicator.connect()
                self.assertTrue(connected)
                communicators.append(communicator)
        
        # Send messages to keep connections active
        for _ in range(10):
            for communicator in communicators:
                await communicator.send_json_to({'type': 'heartbeat'})
                await communicator.receive_json_from()
            
            await asyncio.sleep(0.1)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB "
              f"(+{memory_increase:.1f}MB for {len(communicators)} connections)")
        
        # Cleanup
        for communicator in communicators:
            await communicator.disconnect()
        
        # Memory increase should be reasonable
        self.assertLess(memory_increase, 100)  # Less than 100MB increase
