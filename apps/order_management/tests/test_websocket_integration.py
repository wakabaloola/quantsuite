# apps/order_management/tests/test_websocket_integration.py
import json
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock
from decimal import Decimal

from apps.order_management.models import AlgorithmicOrder
from apps.order_management.algorithm_services import AlgorithmExecutionEngine
from apps.trading_simulation.models import SimulatedInstrument, SimulatedExchange
from apps.market_data.models import Ticker, Exchange, Sector, Industry, DataSource

User = get_user_model()

class AlgorithmWebSocketIntegrationTests(TransactionTestCase):
    """Integration tests for algorithm execution with WebSocket updates"""

    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username='algouser',
            email='algo@test.com',
            password='algopass123'
        )

        self.real_exchange = Exchange.objects.create(
            name='NASDAQ',
            code='NASDAQ'
        )

        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NASDAQ',
            code='SIM_NASDQ',
            real_exchange=self.real_exchange
        )

        self.sector = Sector.objects.create(name='Automotive', code='AUTO')
        self.industry = Industry.objects.create(name='Electric Vehicles', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )

        self.ticker = Ticker.objects.create(
            symbol='TSLA',
            exchange=self.real_exchange,
            name='Tesla Inc',
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

        self.engine = AlgorithmExecutionEngine()

    def test_twap_algorithm_websocket_lifecycle(self):
        """Test TWAP algorithm execution with WebSocket updates"""
        
        # Create TWAP algorithm order (synchronous)
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            limit_price=Decimal('250.00'),
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            algorithm_parameters={
                'slice_count': 5,
                'randomize_timing': False,
                'price_improvement_bps': 2
            }
        )
        
        # Test WebSocket broadcasting without live connections
        with patch('channels.layers.get_channel_layer') as mock_channel_layer:
            mock_layer = MagicMock()
            mock_channel_layer.return_value = mock_layer
            
            # Mock risk validation to pass
            with patch.object(self.engine.risk_service, 'validate_algorithmic_order') as mock_risk:
                mock_risk.return_value = {'approved': True, 'violations': []}
                
                # Start the algorithm
                success = self.engine.start_algorithm(algo_order)
                self.assertTrue(success)
                
                # Verify algorithm status changed
                algo_order.refresh_from_db()
                self.assertEqual(algo_order.status, 'RUNNING')
                
                # Verify WebSocket broadcast was called
                self.assertTrue(mock_layer.group_send.called)
                
                # Pause the algorithm
                success = self.engine.pause_algorithm(algo_order)
                self.assertTrue(success)
                
                algo_order.refresh_from_db()
                self.assertEqual(algo_order.status, 'PAUSED')
                
                # Resume the algorithm
                success = self.engine.resume_algorithm(algo_order)
                self.assertTrue(success)
                
                algo_order.refresh_from_db()
                self.assertEqual(algo_order.status, 'RUNNING')
                
                # Cancel the algorithm
                success = self.engine.cancel_algorithm(algo_order)
                self.assertTrue(success)
                
                algo_order.refresh_from_db()
                self.assertEqual(algo_order.status, 'CANCELLED')

    def test_vwap_algorithm_execution_updates(self):
        """Test VWAP algorithm with real-time execution updates"""
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=2000,
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=2),
            algorithm_parameters={
                'volume_profile': 'AGGRESSIVE',
                'max_participation_rate': 0.25
            }
        )
        
        # Test algorithm execution with mocked market data
        with patch.object(self.engine, '_get_market_data') as mock_market_data:
            mock_market_data.return_value = {
                'last_price': Decimal('245.50'),
                'bid_price': Decimal('245.25'),
                'ask_price': Decimal('245.75'),
                'volume': 50000,
                'spread_bps': Decimal('20.4')
            }
            
            with patch('channels.layers.get_channel_layer') as mock_channel_layer:
                mock_layer = MagicMock()
                mock_channel_layer.return_value = mock_layer
                
                # Mock risk validation
                with patch.object(self.engine.risk_service, 'validate_algorithmic_order') as mock_risk:
                    mock_risk.return_value = {'approved': True, 'violations': []}
                    
                    # Start algorithm
                    success = self.engine.start_algorithm(algo_order)
                    self.assertTrue(success)
                    
                    # Verify executions were created
                    executions = algo_order.executions.all()
                    self.assertTrue(executions.exists())
                    
                    # Verify WebSocket broadcasts occurred
                    self.assertTrue(mock_layer.group_send.called)


    def test_algorithm_risk_rejection_websocket(self):
        """Test algorithm rejection due to risk limits with WebSocket notification"""

        # Create an order that should be rejected by risk management
        large_algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='ICEBERG',
            side='BUY',
            total_quantity=1000000,  # Very large order
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            algorithm_parameters={
                'display_size': 10000,
                'refresh_threshold': 0.5
            }
        )

        # Mock risk service to reject the order
        with patch.object(self.engine.risk_service, 'validate_algorithmic_order') as mock_risk:
            mock_risk.return_value = {
                'approved': False,
                'violations': ['Order size too large', 'Insufficient buying power']
            }

            with patch('channels.layers.get_channel_layer') as mock_channel_layer:
                mock_layer = MagicMock()
                mock_channel_layer.return_value = mock_layer

                # Attempt to start algorithm
                success = self.engine.start_algorithm(large_algo_order)
                self.assertFalse(success)

                # Verify rejection status
                large_algo_order.refresh_from_db()
                self.assertEqual(large_algo_order.status, 'REJECTED')
