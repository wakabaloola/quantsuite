# apps/order_management/tests/test_tasks.py
"""
Focused tests for Celery tasks created in Step 18
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from apps.order_management.models import AlgorithmicOrder, AlgorithmExecution
from apps.order_management.tasks import (
    sync_algorithm_market_data, 
    update_algorithm_technical_indicators
)
from apps.trading_simulation.models import SimulatedExchange, SimulatedInstrument
from apps.market_data.models import Exchange, Ticker, Sector, DataSource

User = get_user_model()


class MarketDataSyncTaskTestCase(TestCase):
    """Test sync_algorithm_market_data Celery task"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='sync_user', email='sync@test.com')
        
        # Create minimal structure
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test',
            code='SIM_TEST',
            real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.data_source = DataSource.objects.create(
            name='Test Source',
            code='TEST_DS',
            url='https://test.com',
            is_active=True,
            requires_api_key=False,
            rate_limit_per_minute=60,
            supported_markets=[],
            supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='TEST_SYNC',
            name='Test Sync Corp.',
            exchange=self.real_exchange,
            sector=self.sector,
            data_source=self.data_source,
            currency='USD',
            country='US'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange
        )
    
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine.process_algorithm_step')
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine._get_enhanced_market_data')
    def test_sync_with_pending_executions(self, mock_enhanced_data, mock_process_step):
        """Test sync task with pending algorithm executions"""
        # Create running algorithm
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            status='RUNNING'
        )
        
        # Create pending execution (scheduled in the past)
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now() - timedelta(minutes=10),
            market_price=Decimal('100.00')
        )
        
        # Mock market data
        mock_enhanced_data.return_value = {
            'last_price': Decimal('101.50'),
            'volume': 50000,
            'market_status': 'open'
        }
        
        # Mock successful processing
        mock_process_step.return_value = True
        
        # Run task
        result = sync_algorithm_market_data()
        
        # Verify result
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['algorithms_checked'], 1)
        self.assertEqual(result['executions_processed'], 1)
        
        # Verify algorithm was updated
        algo_order.refresh_from_db()
        self.assertIsNotNone(algo_order.last_market_check)
        
        # Verify methods were called
        mock_enhanced_data.assert_called_once()
        mock_process_step.assert_called_once_with(execution)
    
    def test_sync_with_no_algorithms(self):
        """Test sync task when no algorithms are running"""
        result = sync_algorithm_market_data()
        
        self.assertEqual(result['status'], 'NO_RUNNING_ALGORITHMS')
    
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine._get_enhanced_market_data')
    def test_sync_error_handling(self, mock_enhanced_data):
        """Test sync task error handling"""
        # Create algorithm
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            status='RUNNING'
        )
        
        # Mock market data to raise exception
        mock_enhanced_data.side_effect = Exception("Market data service error")
        
        # Task should handle error gracefully
        result = sync_algorithm_market_data()
        
        # Should still return success but with 0 executions processed
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['algorithms_checked'], 1)
        self.assertEqual(result['executions_processed'], 0)


class TechnicalIndicatorsUpdateTaskTestCase(TestCase):
    """Test update_algorithm_technical_indicators Celery task"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='indicators_user', email='ind@test.com')
        
        # Create test structure
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test',
            code='SIM_TEST',
            real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.data_source = DataSource.objects.create(
            name='Test Source',
            code='TEST_DS',
            url='https://test.com',
            is_active=True,
            requires_api_key=False,
            rate_limit_per_minute=60,
            supported_markets=[],
            supported_timeframes=[]
        )
    
    @patch('apps.market_data.tasks.calculate_technical_indicators_single.delay')
    def test_update_indicators_multiple_symbols(self, mock_calculate_task):
        """Test indicators update with multiple symbols"""
        # Create multiple tickers and algorithms
        symbols = ['AAPL', 'GOOGL', 'MSFT']
        
        for symbol in symbols:
            ticker = Ticker.objects.create(
                symbol=symbol,
                name=f'{symbol} Corp.',
                exchange=self.real_exchange,
                sector=self.sector,
                data_source=self.data_source,
                currency='USD',
                country='US',
                yfinance_symbol=symbol
            )
            
            instrument = SimulatedInstrument.objects.create(
                real_ticker=ticker,
                exchange=self.sim_exchange
            )
            
            AlgorithmicOrder.objects.create(
                user=self.user,
                exchange=self.sim_exchange,
                instrument=instrument,
                algorithm_type='TWAP',
                side='BUY',
                total_quantity=1000,
                start_time=timezone.now(),
                end_time=timezone.now() + timedelta(hours=2),
                status='RUNNING'
            )
        
        # Mock task return
        mock_task = MagicMock()
        mock_task.id = 'test-task-id'
        mock_calculate_task.return_value = mock_task
        
        # Run task
        result = update_algorithm_technical_indicators()
        
        # Verify result
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['symbols_updated'], 3)
        self.assertEqual(len(result['task_ids']), 3)
        
        # Verify task was called for each symbol
        self.assertEqual(mock_calculate_task.call_count, 3)
        
        # Verify correct parameters
        call_args_list = mock_calculate_task.call_args_list
        for call_args in call_args_list:
            kwargs = call_args[1]
            self.assertIn('symbol', kwargs)
            self.assertEqual(kwargs['timeframe'], '1d')
            self.assertIn('indicators', kwargs)
            expected_indicators = ['rsi', 'macd', 'bollinger_bands', 'sma_20', 'sma_50']
            self.assertEqual(kwargs['indicators'], expected_indicators)
    
    def test_update_indicators_no_algorithms(self):
        """Test indicators update with no running algorithms"""
        result = update_algorithm_technical_indicators()
        
        self.assertEqual(result['status'], 'NO_SYMBOLS')
    
    @patch('apps.market_data.tasks.calculate_technical_indicators_single.delay')
    def test_update_indicators_with_paused_algorithms(self, mock_calculate_task):
        """Test indicators update includes paused algorithms"""
        # Create ticker and instruments
        ticker = Ticker.objects.create(
            symbol='NVDA',
            name='NVIDIA Corp.',
            exchange=self.real_exchange,
            sector=self.sector,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='NVDA'
        )
        
        instrument = SimulatedInstrument.objects.create(
            real_ticker=ticker,
            exchange=self.sim_exchange
        )
        
        # Create both running and paused algorithms
        AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            status='RUNNING'
        )
        
        AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            status='PAUSED'
        )
        
        # Mock task return
        mock_task = MagicMock()
        mock_task.id = 'test-task-id'
        mock_calculate_task.return_value = mock_task
        
        # Run task
        result = update_algorithm_technical_indicators()
        
        # Should update indicators for symbol (both running and paused algorithms use same symbol)
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['symbols_updated'], 1)  # Unique symbols only
        
        # Should be called once for the unique symbol
        mock_calculate_task.assert_called_once()
