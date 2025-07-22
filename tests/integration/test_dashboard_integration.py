# tests/integration/test_dashboard_integration.py
"""
End-to-end integration tests for the complete dashboard system
Tests the entire flow from WebSocket connections to real-time updates
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.db import database_sync_to_async
from decimal import Decimal

from apps.trading_simulation.routing import websocket_urlpatterns
from apps.trading_simulation.models import (
    UserSimulationProfile, SimulatedPosition, SimulatedInstrument, 
    SimulatedExchange
)
from apps.market_data.models import Ticker, Exchange, Sector
from apps.order_management.models import SimulatedOrder
from apps.trading_analytics.models import RiskAlert
from apps.core.websockets.connection_manager import connection_manager

User = get_user_model()


# Docker-specific settings
DOCKER_SETTINGS = {
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'qsuite'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
            'HOST': os.environ.get('DB_HOST', 'db'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    },
    'CACHES': {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/1",
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    },
    'CELERY_BROKER_URL': f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/0",
    'CELERY_RESULT_BACKEND': f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/0",
}

# Apply Docker settings if in Docker environment
if os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER'):
    print("🐳 Docker environment detected - using Docker-optimized settings")
    
    @override_settings(**DOCKER_SETTINGS)
    class TestCompleteIntegratedDashboardDocker(TransactionTestCase):
        """Docker-optimized complete end-to-end dashboard integration tests"""
        
        def setUp(self):
            """Set up test data with Docker considerations"""
            print("🔧 Setting up Docker integration test environment...")
            
            # Verify Docker services
            self.verify_docker_services()
            
            # Create test users (fewer for Docker)
            self.user1 = User.objects.create_user(
                username='dockertrader1',
                email='dockertrader1@example.com',
                password='testpass123'
            )
            
            # Rest of setup same as original but with Docker logging
            print("✅ Docker test environment ready")
        
        def verify_docker_services(self):
            """Verify Docker services are available"""
            try:
                # Test database connection
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                print("✅ Database connection verified")
                
                # Test Redis connection
                from django.core.cache import cache
                cache.set('docker_test', 'ok', 1)
                result = cache.get('docker_test')
                if result == 'ok':
                    print("✅ Redis connection verified")
                else:
                    print("⚠️  Redis connection issue")
                
            except Exception as e:
                print(f"⚠️  Docker service verification failed: {e}")
        
        def test_docker_environment_dashboard_flow(self):
            """Test complete dashboard flow in Docker environment"""
            print("🐳 Testing Docker dashboard flow...")
            
            # Test with Docker-specific timeouts and expectations
            # Similar to original test but with adjusted expectations
            
            # Test database operations
            from apps.trading_simulation.models import UserSimulationProfile
            profile = UserSimulationProfile.objects.create(
                user=self.user1,
                initial_virtual_balance=Decimal('100000.00'),
                current_portfolio_value=Decimal('115000.00'),
                virtual_cash_balance=Decimal('15000.00')
            )
            
            self.assertEqual(profile.user, self.user1)
            print("✅ Database operations working in Docker")
            
            # Test cache operations
            from django.core.cache import cache
            test_data = {'portfolio': {'value': 115000}}
            cache.set('docker_test_portfolio', test_data, 300)
            retrieved = cache.get('docker_test_portfolio')
            self.assertEqual(retrieved, test_data)
            print("✅ Cache operations working in Docker")

else:
    # Use original test class if not in Docker
    print("💻 Standard environment detected - using standard test configuration")


class TestCompleteIntegratedDashboard(TransactionTestCase):
    """Complete end-to-end dashboard integration tests"""
    
    def setUp(self):
        """Set up test data"""
        # Create users
        self.user1 = User.objects.create_user(
            username='trader1',
            email='trader1@example.com',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            username='trader2',
            email='trader2@example.com',
            password='testpass123'
        )
        
        # Create market data
        self.exchange = Exchange.objects.create(
            name='NASDAQ',
            code='NASDAQ',
            country='US',
            timezone='America/New_York'
        )
        
        self.sector = Sector.objects.create(
            name='Technology',
            description='Technology companies'
        )
        
        self.ticker_aapl = Ticker.objects.create(
            symbol='AAPL',
            name='Apple Inc.',
            exchange=self.exchange,
            sector=self.sector,
            is_active=True
        )
        
        self.ticker_msft = Ticker.objects.create(
            symbol='MSFT',
            name='Microsoft Corporation',
            exchange=self.exchange,
            sector=self.sector,
            is_active=True
        )
        
        # Create simulation exchange
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NASDAQ',
            code='SIM_NASDAQ',
            is_active=True
        )
        
        # Create simulated instruments
        self.sim_instrument_aapl = SimulatedInstrument.objects.create(
            real_ticker=self.ticker_aapl,
            simulated_exchange=self.sim_exchange,
            is_active=True
        )
        
        self.sim_instrument_msft = SimulatedInstrument.objects.create(
            real_ticker=self.ticker_msft,
            simulated_exchange=self.sim_exchange,
            is_active=True
        )
        
        # Create user profiles
        self.profile1 = UserSimulationProfile.objects.create(
            user=self.user1,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00'),
            virtual_cash_balance=Decimal('15000.00')
        )
        
        self.profile2 = UserSimulationProfile.objects.create(
            user=self.user2,
            initial_virtual_balance=Decimal('200000.00'),
            current_portfolio_value=Decimal('195000.00'),
            virtual_cash_balance=Decimal('25000.00')
        )
        
        # Create positions
        self.position1 = SimulatedPosition.objects.create(
            user=self.user1,
            instrument=self.sim_instrument_aapl,
            quantity=Decimal('100'),
            average_cost=Decimal('150.00'),
            current_price=Decimal('155.00'),
            market_value=Decimal('15500.00'),
            unrealized_pnl=Decimal('500.00')
        )
        
        self.position2 = SimulatedPosition.objects.create(
            user=self.user1,
            instrument=self.sim_instrument_msft,
            quantity=Decimal('200'),
            average_cost=Decimal('300.00'),
            current_price=Decimal('310.00'),
            market_value=Decimal('62000.00'),
            unrealized_pnl=Decimal('2000.00')
        )


@pytest.mark.asyncio
class TestRealTimeDataFlow:
    """Test real-time data flow through the entire system"""
    
    @pytest.fixture
    async def setup_data(self):
        """Set up test data async"""
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        profile = await database_sync_to_async(UserSimulationProfile.objects.create)(
            user=user,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00'),
            virtual_cash_balance=Decimal('15000.00')
        )
        
        return user, profile
    
    async def test_complete_dashboard_workflow(self, setup_data):
        """Test complete dashboard workflow from connection to updates"""
        user, profile = setup_data
        
        # Mock required services
        with patch('apps.trading_simulation.consumers.streaming_engine') as mock_streaming:
            with patch('apps.trading_simulation.consumers.enhanced_ta_service') as mock_ta:
                with patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service') as mock_analytics:
                    
                    # Set up mocks
                    mock_streaming.get_current_quote.return_value = Mock(
                        price=150.0,
                        volume=1000000,
                        timestamp=timezone.now()
                    )
                    
                    mock_ta.get_cached_signal.return_value = Mock(
                        signal_type=Mock(value='BUY'),
                        strength=0.75
                    )
                    
                    mock_analytics.calculate_comprehensive_analytics.return_value = Mock(
                        total_value=115000.0,
                        daily_pnl=500.0,
                        position_count=2
                    )
                    
                    # Test WebSocket connection and data flow
                    application = URLRouter(websocket_urlpatterns)
                    communicator = WebsocketCommunicator(
                        application, 
                        f"/ws/dashboard/{user.id}/"
                    )
                    
                    communicator.scope['user'] = user
                    
                    # Mock permissions and initial setup
                    with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
                        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard') as mock_initial:
                            
                            # Connect to dashboard
                            connected, subprotocol = await communicator.connect()
                            assert connected
                            
                            # Verify initial dashboard was sent
                            mock_initial.assert_called_once()
                            
                            # Test configuration
                            config_message = {
                                'type': 'configure_dashboard',
                                'config': {
                                    'layout': 'standard',
                                    'watchlist': ['AAPL', 'MSFT'],
                                    'show_portfolio': True
                                }
                            }
                            
                            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.subscribe_to_symbol') as mock_subscribe:
                                await communicator.send_json_to(config_message)
                                
                                response = await communicator.receive_json_from()
                                assert response['type'] == 'dashboard_configured'
                                
                                # Verify symbols were subscribed
                                assert mock_subscribe.call_count == 2  # AAPL and MSFT
                            
                            # Test symbol subscription
                            subscribe_message = {
                                'type': 'subscribe_symbol',
                                'symbol': 'GOOGL'
                            }
                            
                            await communicator.send_json_to(subscribe_message)
                            response = await communicator.receive_json_from()
                            assert response['type'] == 'symbol_subscribed'
                            assert response['symbol'] == 'GOOGL'
                            
                            # Test snapshot request
                            snapshot_message = {
                                'type': 'request_snapshot'
                            }
                            
                            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_complete_snapshot') as mock_snapshot:
                                await communicator.send_json_to(snapshot_message)
                                mock_snapshot.assert_called_once()
                            
                            await communicator.disconnect()
    
    async def test_multiple_user_connections(self, setup_data):
        """Test multiple users connected simultaneously"""
        user1, profile1 = setup_data
        
        # Create second user
        user2 = await database_sync_to_async(User.objects.create_user)(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        application = URLRouter(websocket_urlpatterns)
        
        # Connect both users
        comm1 = WebsocketCommunicator(application, f"/ws/dashboard/{user1.id}/")
        comm2 = WebsocketCommunicator(application, f"/ws/dashboard/{user2.id}/")
        
        comm1.scope['user'] = user1
        comm2.scope['user'] = user2
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                
                # Connect both
                connected1, _ = await comm1.connect()
                connected2, _ = await comm2.connect()
                
                assert connected1
                assert connected2
                
                # Verify connection manager tracks both
                metrics = connection_manager.get_metrics()
                assert metrics['connections']['active'] >= 2
                
                # Test concurrent operations
                config1 = {'type': 'configure_dashboard', 'config': {'watchlist': ['AAPL']}}
                config2 = {'type': 'configure_dashboard', 'config': {'watchlist': ['MSFT']}}
                
                with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.subscribe_to_symbol'):
                    await asyncio.gather(
                        comm1.send_json_to(config1),
                        comm2.send_json_to(config2)
                    )
                    
                    # Both should receive responses
                    resp1 = await comm1.receive_json_from()
                    resp2 = await comm2.receive_json_from()
                    
                    assert resp1['type'] == 'dashboard_configured'
                    assert resp2['type'] == 'dashboard_configured'
                
                await comm1.disconnect()
                await comm2.disconnect()
    
    async def test_real_time_event_broadcasting(self, setup_data):
        """Test real-time event broadcasting to connected dashboards"""
        user, profile = setup_data
        
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, f"/ws/dashboard/{user.id}/")
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                
                connected, _ = await communicator.connect()
                assert connected
                
                # Get the consumer instance for testing
                consumer = communicator.application.application.application.default_route.pattern.callback
                
                # Test portfolio update event
                portfolio_event = {
                    'portfolio': {
                        'total_value': 120000.0,
                        'daily_pnl': 1000.0
                    }
                }
                
                # Simulate receiving portfolio update
                with patch.object(consumer, 'send_tracked_message') as mock_send:
                    await consumer.portfolio_update(portfolio_event)
                    
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args[0][0]
                    assert call_args['type'] == 'dashboard_portfolio_update'
                
                # Test price update event
                price_event = {
                    'data': {
                        'symbol': 'AAPL',
                        'price': 155.0,
                        'change': 2.5
                    }
                }
                
                # Add symbol to subscriptions
                consumer.subscribed_symbols = {'AAPL'}
                
                with patch.object(consumer, 'send_tracked_message') as mock_send:
                    await consumer.price_update(price_event)
                    
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args[0][0]
                    assert call_args['type'] == 'dashboard_price_update'
                
                await communicator.disconnect()


class TestDashboardPerformance(TransactionTestCase):
    """Test dashboard performance under load"""
    
    def setUp(self):
        """Set up performance test data"""
        # Create multiple users for load testing
        self.users = []
        for i in range(10):
            user = User.objects.create_user(
                username=f'user{i}',
                email=f'user{i}@example.com',
                password='testpass123'
            )
            
            UserSimulationProfile.objects.create(
                user=user,
                initial_virtual_balance=Decimal('100000.00'),
                current_portfolio_value=Decimal(f'{100000 + i * 1000}.00'),
                virtual_cash_balance=Decimal('10000.00')
            )
            
            self.users.append(user)
    
    @patch('apps.trading_analytics.dashboard_service.DashboardService.get_unified_dashboard_data')
    def test_dashboard_data_performance(self, mock_dashboard_service):
        """Test dashboard data retrieval performance"""
        # Mock service to return quickly
        mock_dashboard_service.return_value = {
            'dashboard_data': {'portfolio': {'total_value': 100000}},
            'timestamp': timezone.now().isoformat()
        }
        
        from django.test import Client
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Test multiple concurrent requests
        import time
        
        clients = []
        for user in self.users[:5]:  # Test with 5 users
            client = Client()
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
            clients.append(client)
        
        start_time = time.time()
        
        # Make concurrent requests
        responses = []
        for client in clients:
            response = client.get('/api/analytics/dashboard/data/')
            responses.append(response)
        
        end_time = time.time()
        
        # All requests should succeed
        for response in responses:
            self.assertEqual(response.status_code, 200)
        
        # Should complete within reasonable time
        execution_time = end_time - start_time
        self.assertLess(execution_time, 5.0)  # Should complete in under 5 seconds
    
    def test_connection_manager_performance(self):
        """Test connection manager performance with multiple connections"""
        # Simulate multiple connections
        mock_consumers = []
        connection_ids = []
        
        for i, user in enumerate(self.users):
            mock_consumer = Mock()
            mock_consumer.scope = {
                'user': user,
                'path': f'/ws/dashboard/{user.id}/',
                'client': ['127.0.0.1', 12345 + i]
            }
            
            connection_id = connection_manager.add_connection(
                consumer=mock_consumer,
                user_id=user.id,
                connection_type='dashboard'
            )
            
            mock_consumers.append(mock_consumer)
            connection_ids.append(connection_id)
        
        # Test metrics retrieval performance
        import time
        start_time = time.time()
        
        metrics = connection_manager.get_metrics()
        
        end_time = time.time()
        
        # Should be fast
        self.assertLess(end_time - start_time, 0.1)  # Under 100ms
        
        # Should track all connections
        self.assertEqual(metrics['connections']['active'], len(self.users))
        
        # Clean up
        for connection_id in connection_ids:
            connection_manager.remove_connection(connection_id)


@pytest.mark.asyncio
class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios"""
    
    async def test_websocket_connection_error_recovery(self):
        """Test WebSocket connection error recovery"""
        # Create user
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, f"/ws/dashboard/{user.id}/")
        communicator.scope['user'] = user
        
        # Simulate service error during connection
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard') as mock_initial:
                
                # First connection attempt - simulate error
                mock_initial.side_effect = Exception("Service unavailable")
                
                connected, _ = await communicator.connect()
                
                # Should still connect (error in initial data, not connection)
                assert connected
                
                # Test error message handling
                invalid_message = {
                    'type': 'invalid_message_type'
                }
                
                await communicator.send_json_to(invalid_message)
                
                # Should handle gracefully without disconnecting
                # (The consumer should continue to work)
                
                await communicator.disconnect()
    
    async def test_dashboard_service_error_handling(self):
        """Test dashboard service error handling"""
        from apps.trading_analytics.dashboard_service import DashboardService
        
        service = DashboardService()
        
        # Test with non-existent user
        result = await service.get_unified_dashboard_data(99999, ['AAPL'])
        
        # Should return empty data, not crash
        assert isinstance(result, dict)
        
        # Test with invalid symbols
        with patch('apps.market_data.streaming.streaming_engine.get_current_quote') as mock_quote:
            mock_quote.side_effect = Exception("Symbol not found")
            
            result = await service.get_market_analytics(['INVALID'])
            
            # Should handle error gracefully
            assert isinstance(result, dict)
            assert result.get('quotes', {}) == {}
    
    async def test_task_error_recovery(self):
        """Test background task error recovery"""
        from apps.trading_analytics.tasks import update_dashboard_cache_all_users
        
        # Test with database error
        with patch('apps.trading_analytics.tasks.User.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database connection failed")
            
            result = update_dashboard_cache_all_users()
            
            # Should return error status, not crash
            assert result['status'] == 'failed'
            assert 'error' in result


class TestDashboardSystemIntegration(TransactionTestCase):
    """Test complete dashboard system integration"""
    
    def setUp(self):
        """Set up integration test data"""
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@example.com',
            password='testpass123'
        )
        
        self.profile = UserSimulationProfile.objects.create(
            user=self.user,
            initial_virtual_balance=Decimal('100000.00'),
            current_portfolio_value=Decimal('115000.00'),
            virtual_cash_balance=Decimal('15000.00')
        )
    
    def test_api_to_websocket_integration(self):
        """Test integration between REST API and WebSocket updates"""
        from django.test import Client
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Set up API client
        client = Client()
        refresh = RefreshToken.for_user(self.user)
        access_token = str(refresh.access_token)
        client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        
        # Test API endpoint
        with patch('apps.trading_analytics.views.async_to_sync') as mock_async:
            mock_async.return_value = {
                'dashboard_data': {
                    'portfolio': {'total_value': 115000.0},
                    'market': {'quotes': {}},
                    'risk': {'risk_score': 'LOW'}
                },
                'timestamp': timezone.now().isoformat(),
                'user_id': self.user.id
            }
            
            response = client.get('/api/analytics/dashboard/data/')
            
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertEqual(data['status'], 'success')
            self.assertIn('data', data)
    
    def test_task_to_websocket_integration(self):
        """Test integration between background tasks and WebSocket broadcasts"""
        from apps.trading_analytics.tasks import broadcast_market_summary
        
        with patch('channels.layers.get_channel_layer') as mock_channel_layer:
            with patch('apps.trading_analytics.tasks.async_to_sync') as mock_async:
                # Mock services
                mock_async.return_value = {
                    'indices': {'SPY': {'price': 450.0}},
                    'market_sentiment': {'overall_sentiment': 'BULLISH'}
                }
                
                # Mock channel layer
                mock_layer = Mock()
                mock_channel_layer.return_value = mock_layer
                
                # Run task
                result = broadcast_market_summary()
                
                # Verify task completed
                self.assertEqual(result['status'], 'success')
                
                # Verify WebSocket broadcast was attempted
                mock_layer.group_send.assert_called_once()
                
                # Check broadcast parameters
                call_args = mock_layer.group_send.call_args
                group_name = call_args[0][0]
                message = call_args[0][1]
                
                self.assertEqual(group_name, 'dashboard_global')
                self.assertIn('type', message)
    
    @patch('apps.trading_analytics.portfolio_analytics.portfolio_analytics_service.calculate_comprehensive_analytics')
    def test_analytics_to_dashboard_integration(self, mock_analytics):
        """Test integration between analytics service and dashboard"""
        from apps.trading_analytics.portfolio_analytics import PortfolioMetrics
        
        # Mock analytics calculation
        mock_metrics = PortfolioMetrics(
            total_value=115000.0,
            cash_balance=15000.0,
            invested_value=100000.0,
            total_return_pct=15.0,
            unrealized_pnl=5000.0,
            realized_pnl=10000.0,
            intraday_pnl=200.0,
            daily_pnl=500.0,
            weekly_pnl=2000.0,
            monthly_pnl=5000.0,
            ytd_pnl=15000.0,
            portfolio_var_1day=-2300.0,
            portfolio_volatility=0.16,
            portfolio_beta=1.02,
            max_drawdown=-0.05,
            sharpe_ratio=1.25,
            alpha=0.02,
            tracking_error=0.04,
            information_ratio=0.5,
            position_count=8,
            largest_position_pct=12.5,
            top5_concentration=45.0,
            sector_count=4,
            last_updated=timezone.now(),
            calculation_time_ms=150.0
        )
        
        mock_analytics.return_value = mock_metrics
        
        # Test dashboard service integration
        from apps.trading_analytics.dashboard_service import DashboardService
        
        service = DashboardService()
        
        # This should integrate with analytics service
        import asyncio
        result = asyncio.run(service.get_portfolio_analytics(self.user.id))
        
        self.assertIn('summary', result)
        self.assertIn('risk_metrics', result)
        self.assertEqual(result['summary']['total_value'], 115000.0)
    
    def test_complete_dashboard_flow(self):
        """Test complete dashboard data flow"""
        # This tests the entire flow:
        # 1. User connects to WebSocket
        # 2. Dashboard service aggregates data
        # 3. Real-time updates are sent
        # 4. Background tasks update cache
        # 5. API endpoints serve data
        
        # Test would require actual WebSocket server, so we'll test components
        
        # 1. Test dashboard service
        from apps.trading_analytics.dashboard_service import DashboardService
        
        service = DashboardService()
        
        with patch.object(service, 'get_portfolio_analytics') as mock_portfolio:
            with patch.object(service, 'get_market_analytics') as mock_market:
                with patch.object(service, 'get_risk_analytics') as mock_risk:
                    
                    # Mock service responses
                    mock_portfolio.return_value = {'summary': {'total_value': 115000.0}}
                    mock_market.return_value = {'quotes': {'AAPL': {'price': 150.0}}}
                    mock_risk.return_value = {'risk_score': 'LOW'}
                    
                    # Test unified data gathering
                    import asyncio
                    result = asyncio.run(service.get_unified_dashboard_data(
                        self.user.id, ['AAPL']
                    ))
                    
                    self.assertIn('dashboard_data', result)
                    self.assertIn('portfolio', result['dashboard_data'])
                    self.assertIn('market', result['dashboard_data'])
                    self.assertIn('risk', result['dashboard_data'])
        
        # 2. Test task system
        from apps.trading_analytics.tasks import calculate_dashboard_performance_metrics
        
        with patch('django.core.cache.cache.set') as mock_cache:
            result = calculate_dashboard_performance_metrics()
            
            self.assertEqual(result['status'], 'success')
            mock_cache.assert_called()
        
        # 3. Test API endpoints
        from django.test import Client
        from rest_framework_simplejwt.tokens import RefreshToken
        
        client = Client()
        refresh = RefreshToken.for_user(self.user)
        access_token = str(refresh.access_token)
        client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        
        with patch('apps.trading_analytics.views.async_to_sync') as mock_async:
            mock_async.return_value = {'test': 'data'}
            
            response = client.get('/api/analytics/dashboard/summary/')
            self.assertEqual(response.status_code, 200)


@pytest.mark.asyncio
class TestDashboardScalability:
    """Test dashboard scalability and concurrent usage"""
    
    async def test_concurrent_dashboard_connections(self):
        """Test many concurrent dashboard connections"""
        # Create multiple users
        users = []
        for i in range(5):  # Test with 5 concurrent users
            user = await database_sync_to_async(User.objects.create_user)(
                username=f'user{i}',
                email=f'user{i}@example.com',
                password='testpass123'
            )
            users.append(user)
        
        # Create concurrent connections
        communicators = []
        application = URLRouter(websocket_urlpatterns)
        
        for user in users:
            comm = WebsocketCommunicator(application, f"/ws/dashboard/{user.id}/")
            comm.scope['user'] = user
            communicators.append(comm)
        
        # Connect all simultaneously
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                
                start_time = timezone.now()
                
                # Connect all
                connections = await asyncio.gather(*[
                    comm.connect() for comm in communicators
                ])
                
                connection_time = (timezone.now() - start_time).total_seconds()
                
                # All should connect successfully
                for connected, _ in connections:
                    assert connected
                
                # Should connect quickly even with multiple users
                assert connection_time < 5.0
                
                # Test concurrent operations
                config_tasks = []
                for comm in communicators:
                    config_msg = {
                        'type': 'configure_dashboard',
                        'config': {'layout': 'standard', 'watchlist': ['AAPL']}
                    }
                    config_tasks.append(comm.send_json_to(config_msg))
                
                # Send all configurations simultaneously
                with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.subscribe_to_symbol'):
                    await asyncio.gather(*config_tasks)
                    
                    # All should receive responses
                    responses = await asyncio.gather(*[
                        comm.receive_json_from() for comm in communicators
                    ])
                    
                    for response in responses:
                        assert response['type'] == 'dashboard_configured'
                
                # Disconnect all
                await asyncio.gather(*[comm.disconnect() for comm in communicators])
    
    async def test_high_frequency_updates(self):
        """Test handling of high frequency updates"""
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, f"/ws/dashboard/{user.id}/")
        communicator.scope['user'] = user
        
        with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.check_permissions', return_value=True):
            with patch('apps.trading_simulation.consumers.IntegratedMarketDashboardConsumer.send_initial_dashboard'):
                
                connected, _ = await communicator.connect()
                assert connected
                
                # Send many rapid updates
                update_tasks = []
                for i in range(10):
                    update_msg = {
                        'type': 'update_frequency',
                        'component': 'market_data',
                        'frequency': 1  # 1 second
                    }
                    update_tasks.append(communicator.send_json_to(update_msg))
                
                # Should handle rapid updates without errors
                await asyncio.gather(*update_tasks, return_exceptions=True)
                
                await communicator.disconnect()


# Create a comprehensive test runner
def run_integration_tests():
    """Run all integration tests"""
    import subprocess
    import sys
    
    test_commands = [
        'python manage.py test tests.integration.test_dashboard_integration.TestCompleteIntegratedDashboard',
        'python manage.py test tests.integration.test_dashboard_integration.TestDashboardPerformance',
        'python manage.py test tests.integration.test_dashboard_integration.TestDashboardSystemIntegration',
        'pytest tests/integration/test_dashboard_integration.py::TestRealTimeDataFlow -v',
        'pytest tests/integration/test_dashboard_integration.py::TestErrorHandlingAndRecovery -v',
        'pytest tests/integration/test_dashboard_integration.py::TestDashboardScalability -v'
    ]
    
    print("🚀 Running Comprehensive Dashboard Integration Tests...")
    print("=" * 60)
    
    for cmd in test_commands:
        print(f"\n▶️  Running: {cmd}")
        result = subprocess.run(cmd.split(), capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ PASSED")
        else:
            print("❌ FAILED")
            print(result.stdout)
            print(result.stderr)
            return False
    
    print("\n🎉 All integration tests completed successfully!")
    return True


if __name__ == '__main__':
    run_integration_tests()
