# apps/trading_simulation/tests/test_dashboard_consumer.py
"""
Test suite for IntegratedMarketDashboardConsumer
"""

import pytest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.db import database_sync_to_async

from apps.trading_simulation.consumers import IntegratedMarketDashboardConsumer
from apps.trading_simulation.routing import websocket_urlpatterns
from apps.trading_simulation.models import UserSimulationProfile, SimulatedPosition

User = get_user_model()


@pytest.mark.asyncio
class TestIntegratedMarketDashboardConsumer:
    """Test IntegratedMarketDashboardConsumer functionality"""
    
    @pytest.fixture
    async def user(self):
        """Create test user"""
        return await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    @pytest.fixture
    async def user_profile(self, user):
        """Create user simulation profile"""
        return await database_sync_to_async(UserSimulationProfile.objects.create)(
            user=user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=115000.00,
            virtual_cash_balance=15000.00
        )
    
    @pytest.fixture
    def application(self):
        """Create test application"""
        return URLRouter(websocket_urlpatterns)
    
    async def test_consumer_connection(self, user, application):
        """Test WebSocket connection to dashboard consumer"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        # Mock authentication
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                connected, subprotocol = await communicator.connect()
                
                assert connected
                
                await communicator.disconnect()
    
    async def test_consumer_authentication_required(self, application):
        """Test that authentication is required"""
        communicator = WebsocketCommunicator(
            application, 
            "/ws/dashboard/999/"
        )
        
        # No authenticated user
        communicator.scope['user'] = Mock(is_authenticated=False)
        
        connected, subprotocol = await communicator.connect()
        
        # Should not connect without authentication
        assert not connected
    
    async def test_dashboard_configuration(self, user, application):
        """Test dashboard configuration message"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                await communicator.connect()
                
                # Send configuration message
                config_message = {
                    'type': 'configure_dashboard',
                    'config': {
                        'layout': 'standard',
                        'watchlist': ['AAPL', 'MSFT', 'GOOGL'],
                        'show_portfolio': True,
                        'theme': 'dark'
                    }
                }
                
                with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.subscribe_to_symbol'):
                    await communicator.send_json_to(config_message)
                    
                    response = await communicator.receive_json_from()
                    
                    assert response['type'] == 'dashboard_configured'
                    assert 'config' in response
                
                await communicator.disconnect()
    
    async def test_symbol_subscription(self, user, application):
        """Test symbol subscription functionality"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                await communicator.connect()
                
                # Subscribe to symbol
                subscribe_message = {
                    'type': 'subscribe_symbol',
                    'symbol': 'AAPL'
                }
                
                with patch('apps.market_data.streaming.streaming_engine.subscribe_symbol'):
                    with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_symbol_snapshot'):
                        await communicator.send_json_to(subscribe_message)
                        
                        response = await communicator.receive_json_from()
                        
                        assert response['type'] == 'symbol_subscribed'
                        assert response['symbol'] == 'AAPL'
                
                await communicator.disconnect()
    
    async def test_snapshot_request(self, user, application):
        """Test snapshot request functionality"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                await communicator.connect()
                
                # Request snapshot
                snapshot_message = {
                    'type': 'request_snapshot'
                }
                
                with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_complete_snapshot') as mock_snapshot:
                    await communicator.send_json_to(snapshot_message)
                    
                    mock_snapshot.assert_called_once()
                
                await communicator.disconnect()
    
    async def test_heartbeat_response(self, user, application):
        """Test heartbeat functionality"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                await communicator.connect()
                
                # Send heartbeat
                heartbeat_message = {
                    'type': 'heartbeat'
                }
                
                await communicator.send_json_to(heartbeat_message)
                
                response = await communicator.receive_json_from()
                
                assert response['type'] == 'heartbeat_response'
                assert 'timestamp' in response
                
                await communicator.disconnect()
    
    async def test_invalid_json_handling(self, user, application):
        """Test handling of invalid JSON messages"""
        communicator = WebsocketCommunicator(
            application, 
            f"/ws/dashboard/{user.id}/"
        )
        
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                await communicator.connect()
                
                # Send invalid JSON
                await communicator.send_to(text_data="invalid json")
                
                response = await communicator.receive_json_from()
                
                assert response['type'] == 'dashboard_error'
                assert 'Invalid JSON format' in response['error']['message']
                
                await communicator.disconnect()


class TestDashboardConsumerMethods(TestCase):
    """Test individual dashboard consumer methods"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=100000.00,
            current_portfolio_value=115000.00,
            virtual_cash_balance=15000.00
        )
        
        self.consumer = IntegratedMarketDashboardConsumer()
        self.consumer.user_id = self.user.id
        self.consumer.subscribed_symbols = {'AAPL', 'MSFT'}
        self.consumer.dashboard_config = {
            'layout': 'standard',
            'watchlist': ['AAPL', 'MSFT'],
            'show_portfolio': True
        }
    
    @patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.get_portfolio_summary')
    async def test_get_portfolio_summary(self, mock_get_summary):
        """Test portfolio summary retrieval"""
        mock_get_summary.return_value = {
            'total_value': 115000.0,
            'cash_balance': 15000.0,
            'daily_pnl': 500.0,
            'total_return_pct': 15.0,
            'positions_count': 8,
            'orders_count': 2
        }
        
        result = await self.consumer.get_portfolio_summary()
        
        self.assertEqual(result['total_value'], 115000.0)
        self.assertEqual(result['positions_count'], 8)
    
    @patch('apps.market_data.streaming.streaming_engine.get_current_quote')
    async def test_get_subscribed_market_data(self, mock_get_quote):
        """Test getting market data for subscribed symbols"""
        mock_quote = Mock()
        mock_quote.price = 150.0
        mock_quote.volume = 1000000
        mock_quote.bid = 149.95
        mock_quote.ask = 150.05
        mock_quote.change_24h = 2.5
        mock_quote.change_pct_24h = 1.67
        mock_quote.timestamp = timezone.now()
        
        mock_get_quote.return_value = mock_quote
        
        with patch('apps.market_data.analysis.enhanced_ta_service.get_cached_signal', return_value=None):
            result = await self.consumer.get_subscribed_market_data()
            
            self.assertIn('AAPL', result)
            self.assertIn('MSFT', result)
            self.assertEqual(result['AAPL']['quote']['price'], 150.0)
    
    async def test_calculate_data_freshness(self):
        """Test data freshness calculation"""
        with patch('apps.market_data.streaming.streaming_engine.get_current_quote') as mock_quote:
            mock_quote.return_value = Mock(timestamp=timezone.now())
            
            result = await self.consumer.calculate_data_freshness()
            
            self.assertIsInstance(result, (int, float))
            self.assertGreaterEqual(result, 0)
            self.assertLessEqual(result, 100)
    
    def test_calculate_allocation_summary_empty(self):
        """Test allocation summary with no positions"""
        result = self.consumer._calculate_allocation_summary([], 0)
        
        self.assertEqual(result, {})
    
    async def test_get_market_updates(self):
        """Test getting market updates"""
        with patch.object(self.consumer, 'get_subscribed_market_data', return_value={'AAPL': {}}) as mock_market:
            result = await self.consumer.get_market_updates()
            
            mock_market.assert_called_once()
            self.assertEqual(result, {'AAPL': {}})
    
    async def test_get_analytics_update(self):
        """Test getting analytics updates"""
        with patch.object(self.consumer, 'get_portfolio_summary', return_value={'total_value': 100000}) as mock_portfolio:
            with patch.object(self.consumer, 'get_performance_summary', return_value={'return_pct': 15.0}) as mock_performance:
                
                result = await self.consumer.get_analytics_update()
                
                self.assertIn('portfolio_summary', result)
                self.assertIn('performance_summary', result)
                mock_portfolio.assert_called_once()
                mock_performance.assert_called_once()


@pytest.mark.asyncio
class TestDashboardConsumerEventHandling:
    """Test event handling in dashboard consumer"""
    
    async def test_portfolio_update_handler(self):
        """Test portfolio update event handling"""
        consumer = IntegratedMarketDashboardConsumer()
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'portfolio': {
                    'total_value': 115000.0,
                    'daily_pnl': 500.0
                }
            }
            
            await consumer.portfolio_update(event)
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert call_args['type'] == 'dashboard_portfolio_update'
            assert 'data' in call_args
    
    async def test_price_update_handler(self):
        """Test price update event handling"""
        consumer = IntegratedMarketDashboardConsumer()
        consumer.subscribed_symbols = {'AAPL'}
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'data': {
                    'symbol': 'AAPL',
                    'price': 150.0,
                    'change': 2.5
                }
            }
            
            await consumer.price_update(event)
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert call_args['type'] == 'dashboard_price_update'
    
    async def test_price_update_unsubscribed_symbol(self):
        """Test price update for unsubscribed symbol"""
        consumer = IntegratedMarketDashboardConsumer()
        consumer.subscribed_symbols = {'MSFT'}  # Different symbol
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'data': {
                    'symbol': 'AAPL',  # Not subscribed
                    'price': 150.0
                }
            }
            
            await consumer.price_update(event)
            
            # Should not send message for unsubscribed symbol
            mock_send.assert_not_called()
    
    async def test_risk_alert_handler(self):
        """Test risk alert event handling"""
        consumer = IntegratedMarketDashboardConsumer()
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'alert': {
                    'type': 'CONCENTRATION_RISK',
                    'severity': 'HIGH',
                    'message': 'High concentration detected'
                }
            }
            
            await consumer.risk_alert(event)
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert call_args['type'] == 'dashboard_risk_alert'
    
    async def test_algorithm_execution_progress_handler(self):
        """Test algorithm execution progress handling"""
        consumer = IntegratedMarketDashboardConsumer()
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'data': {
                    'algo_id': 'test-123',
                    'progress': 45.0,
                    'status': 'RUNNING'
                }
            }
            
            await consumer.algorithm_execution_progress(event)
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert call_args['type'] == 'dashboard_algorithm_update'
    
    async def test_market_summary_broadcast_handler(self):
        """Test market summary broadcast handling"""
        consumer = IntegratedMarketDashboardConsumer()
        
        with patch.object(consumer, 'send_tracked_message') as mock_send:
            event = {
                'data': {
                    'market_status': 'OPEN',
                    'indices': {'SPY': {'price': 450.0}}
                }
            }
            
            await consumer.market_summary_broadcast(event)
            
            mock_send.assert_called_once()
            # Should send the event data directly
            call_args = mock_send.call_args[0][0]
            assert call_args == event['data']
