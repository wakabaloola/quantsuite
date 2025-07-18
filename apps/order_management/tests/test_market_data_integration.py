# apps/order_management/tests/test_market_data_integration.py
"""
Test Step 18: Market Data Integration with Algorithmic Trading

Tests the integration between algorithmic trading and real-time market data,
including enhanced market data services, technical indicators, WebSocket
consumers, and Celery task synchronization.
"""

import json
import asyncio
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock, AsyncMock, call

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.urls import re_path

from apps.order_management.models import AlgorithmicOrder, AlgorithmExecution
from apps.order_management.algorithm_services import AlgorithmExecutionEngine
from apps.trading_simulation.models import (
    SimulatedExchange, SimulatedInstrument, UserSimulationProfile, OrderBook
)
from apps.trading_simulation.consumers import MarketDataConsumer
from apps.market_data.models import (
    Exchange, Ticker, Sector, Industry, DataSource, MarketData, TechnicalIndicator
)

User = get_user_model()


class EnhancedMarketDataServiceTestCase(TransactionTestCase):
    """Test enhanced market data integration in algorithm services"""
    
    def setUp(self):
        """Set up test data with complete market data structure"""
        self.user = User.objects.create_user(
            username='market_data_user', 
            email='md@test.com'
        )
        
        # Create complete market data hierarchy
        self.real_exchange = Exchange.objects.create(
            name='NASDAQ', 
            code='NASDAQ'
        )
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NASDAQ', 
            code='SIM_NASDAQ', 
            real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(
            name='Technology', 
            code='TECH'
        )
        self.industry = Industry.objects.create(
            name='Software', 
            sector=self.sector
        )
        self.data_source = DataSource.objects.create(
            name='YFinance Integration', 
            code='YFINANCE_INT',
            url='https://yfinance.test.com',
            api_endpoint='https://api.yfinance.test.com',
            is_active=True,
            requires_api_key=False,
            rate_limit_per_minute=2000,
            supported_markets=['US'],
            supported_timeframes=['1m', '5m', '1h', '1d']
        )
        
        self.ticker = Ticker.objects.create(
            symbol='TSLA',
            name='Tesla Inc.',
            exchange=self.real_exchange,
            sector=self.sector,
            industry=self.industry,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='TSLA',
            market_cap=800000000000  # $800B market cap
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange,
            is_active=True
        )
        
        # Create order book for the instrument
        OrderBook.objects.create(
            instrument=self.instrument,
            best_bid_price=Decimal('245.50'),
            best_ask_price=Decimal('245.75'),
            last_trade_price=Decimal('245.60'),
            daily_volume=1500000,
            trade_count=25000
        )
        
        # Create user simulation profile
        UserSimulationProfile.objects.create(
            user=self.user,
            virtual_cash_balance=Decimal('100000.00')
        )
        
        # Create recent market data
        base_timestamp = timezone.now() - timedelta(days=1)
        for i in range(20):
            MarketData.objects.create(
                ticker=self.ticker,
                timestamp=base_timestamp + timedelta(hours=i),
                timeframe='1h',
                open=Decimal('240.00') + Decimal(str(i * 0.5)),
                high=Decimal('242.00') + Decimal(str(i * 0.5)),
                low=Decimal('239.00') + Decimal(str(i * 0.5)),
                close=Decimal('241.00') + Decimal(str(i * 0.5)),
                volume=100000 + (i * 5000),
                data_source=self.data_source
            )
        
        # Create technical indicators
        indicators_data = [
            ('rsi', Decimal('65.5')),
            ('macd', None),  # Will store complex data in values field
            ('sma_20', Decimal('244.75')),
            ('sma_50', Decimal('240.25')),
            ('bollinger_bands', None)
        ]
        
        for indicator_name, value in indicators_data:
            if indicator_name == 'macd':
                indicator_values = {
                    'macd_line': 2.45,
                    'signal_line': 1.85,
                    'histogram': 0.60,
                    'signal': 'bullish'
                }
            elif indicator_name == 'bollinger_bands':
                indicator_values = {
                    'upper_band': 248.50,
                    'middle_band': 244.75,
                    'lower_band': 241.00,
                    'signal': 'neutral'
                }
            else:
                indicator_values = None
            
            TechnicalIndicator.objects.create(
                ticker=self.ticker,
                timestamp=timezone.now() - timedelta(minutes=30),
                timeframe='1d',
                indicator_name=indicator_name,
                value=value,
                values=indicator_values,
                parameters={'period': 14} if 'rsi' in indicator_name else {}
            )
        
        self.engine = AlgorithmExecutionEngine()
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    def test_enhanced_market_data_integration(self, mock_real_time_quote):
        """Test enhanced market data integration with real-time feeds"""
        # Mock real-time quote response
        mock_real_time_quote.return_value = {
            'symbol': 'TSLA',
            'price': Decimal('246.25'),
            'bid': Decimal('246.10'),
            'ask': Decimal('246.40'),
            'volume': 1850000,
            'market_status': 'open',
            'timestamp': timezone.now()
        }
        
        # Test enhanced market data retrieval
        enhanced_data = self.engine._get_enhanced_market_data(self.instrument)
        
        # Verify real-time integration
        self.assertEqual(enhanced_data['last_price'], Decimal('246.25'))
        self.assertEqual(enhanced_data['bid_price'], Decimal('246.10'))
        self.assertEqual(enhanced_data['ask_price'], Decimal('246.40'))
        self.assertEqual(enhanced_data['volume'], 1850000)
        self.assertEqual(enhanced_data['market_status'], 'open')
        self.assertEqual(enhanced_data['data_source'], 'market_data_integration')
        
        # Verify technical indicators integration
        self.assertIn('technical_indicators', enhanced_data)
        indicators = enhanced_data['technical_indicators']
        
        # Check RSI integration
        self.assertIn('rsi', indicators)
        self.assertEqual(indicators['rsi']['value'], 65.5)
        
        # Check MACD integration
        self.assertIn('macd', indicators)
        self.assertIsNone(indicators['macd']['value'])  # Complex data in values
        
        # Check SMA integration
        self.assertIn('sma_20', indicators)
        self.assertEqual(indicators['sma_20']['value'], 244.75)
        
        # Verify spread calculation
        expected_spread_bps = ((Decimal('246.40') - Decimal('246.10')) / 
                              ((Decimal('246.40') + Decimal('246.10')) / 2)) * 10000
        self.assertAlmostEqual(
            float(enhanced_data['spread_bps']), 
            float(expected_spread_bps), 
            places=2
        )
        
        # Verify volatility calculation
        self.assertIn('volatility_24h', enhanced_data)
        self.assertGreater(enhanced_data['volatility_24h'], 0)
        
        # Verify YFinance service was called
        mock_real_time_quote.assert_called_once_with('TSLA')
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    def test_enhanced_market_data_fallback(self, mock_real_time_quote):
        """Test fallback to stored data when real-time feed fails"""
        # Mock YFinance service failure
        mock_real_time_quote.return_value = None
        
        # Test fallback mechanism
        enhanced_data = self.engine._get_enhanced_market_data(self.instrument)
        
        # Should fall back to latest stored market data
        latest_market_data = MarketData.objects.filter(
            ticker=self.ticker
        ).latest('timestamp')
        
        self.assertEqual(enhanced_data['last_price'], latest_market_data.close)
        self.assertEqual(enhanced_data['data_source'], 'market_data_integration')
        
        # Technical indicators should still be available
        self.assertIn('technical_indicators', enhanced_data)
        self.assertIn('rsi', enhanced_data['technical_indicators'])
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    def test_technical_indicator_based_execution(self, mock_real_time_quote):
        """Test algorithm execution with technical indicator triggers"""
        mock_real_time_quote.return_value = {
            'symbol': 'TSLA',
            'price': Decimal('245.80'),
            'bid': Decimal('245.70'),
            'ask': Decimal('245.90'),
            'volume': 1200000,
            'market_status': 'open'
        }
        
        # Create SNIPER algorithm with technical indicator triggers
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='SNIPER',
            side='BUY',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            limit_price=Decimal('246.00'),
            algorithm_parameters={
                'max_spread_bps': 30,
                'min_volume': 1000000,
                'patience_seconds': 600,
                'use_rsi_trigger': True,
                'rsi_threshold': 70,  # RSI < 70 for BUY (current RSI is 65.5)
                'use_macd_trigger': True
            }
        )
        
        # Test execution with favorable technical indicators
        from apps.order_management.algorithm_services import SniperAlgorithm
        sniper = SniperAlgorithm(algo_order)
        
        # Get enhanced market data
        market_data = self.engine._get_enhanced_market_data(self.instrument)
        
        # Test enhanced execution logic
        should_execute = sniper.should_execute_with_indicators(market_data)
        self.assertTrue(should_execute)  # RSI 65.5 < 70, MACD bullish
        
        # Test with unfavorable RSI (change algorithm to SELL)
        algo_order.side = 'SELL'
        algo_order.algorithm_parameters['rsi_threshold'] = 60  # RSI > 60 for SELL
        algo_order.save()
        
        sniper = SniperAlgorithm(algo_order)
        should_execute = sniper.should_execute_with_indicators(market_data)
        self.assertTrue(should_execute)  # RSI 65.5 > 60 for SELL
        
        # Test with RSI trigger disabled but MACD enabled
        algo_order.algorithm_parameters = {
            'max_spread_bps': 30,
            'min_volume': 1000000,
            'patience_seconds': 600,
            'use_rsi_trigger': False,
            'use_macd_trigger': True
        }
        algo_order.save()
        
        sniper = SniperAlgorithm(algo_order)
        should_execute = sniper.should_execute_with_indicators(market_data)
        self.assertTrue(should_execute)  # MACD signal is bullish for SELL


class EnhancedWebSocketConsumerTestCase(TransactionTestCase):
    """Test enhanced WebSocket market data consumer"""
    
    def setUp(self):
        """Set up WebSocket testing environment"""
        self.user = User.objects.create_user(
            username='ws_user',
            email='ws@test.com'
        )
        
        # Create market data structure
        self.real_exchange = Exchange.objects.create(name='NYSE', code='NYSE')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NYSE',
            code='SIM_NYSE',
            real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Finance', code='FIN')
        self.industry = Industry.objects.create(name='Investment Services', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source',
            code='TEST_DS',
            url='https://test.com',
            is_active=True,
            requires_api_key=False,
            rate_limit_per_minute=1000,
            supported_markets=['US'],
            supported_timeframes=['1m', '1d']
        )
        
        self.ticker = Ticker.objects.create(
            symbol='SPY',
            name='SPDR S&P 500 ETF',
            exchange=self.real_exchange,
            sector=self.sector,
            industry=self.industry,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='SPY'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange,
            is_active=True
        )
        
        # Create order book
        OrderBook.objects.create(
            instrument=self.instrument,
            best_bid_price=Decimal('420.10'),
            best_ask_price=Decimal('420.25'),
            last_trade_price=Decimal('420.18'),
            daily_volume=5000000,
            trade_count=75000
        )
        
        # Create technical indicators
        TechnicalIndicator.objects.create(
            ticker=self.ticker,
            timestamp=timezone.now() - timedelta(minutes=15),
            timeframe='1d',
            indicator_name='rsi',
            value=Decimal('58.5'),
            parameters={'period': 14}
        )
        
        TechnicalIndicator.objects.create(
            ticker=self.ticker,
            timestamp=timezone.now() - timedelta(minutes=15),
            timeframe='1d',
            indicator_name='macd',
            values={
                'macd_line': 1.25,
                'signal_line': 0.95,
                'histogram': 0.30,
                'signal': 'bullish'
            }
        )
        
        # WebSocket application
        self.application = URLRouter([
            re_path(r'ws/trading/market/(?P<symbol>\w+)/$', MarketDataConsumer.as_asgi()),
        ])
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    async def test_enhanced_market_data_consumer_initial_data(self, mock_real_time_quote):
        """Test enhanced MarketDataConsumer initial data loading"""
        # Mock real-time quote
        mock_real_time_quote.return_value = {
            'symbol': 'SPY',
            'price': Decimal('420.55'),
            'change': Decimal('1.25'),
            'change_percent': Decimal('0.30'),
            'volume': 5200000,
            'market_status': 'open',
            'bid': Decimal('420.50'),
            'ask': Decimal('420.60'),
            'timestamp': timezone.now()
        }
        
        communicator = WebsocketCommunicator(
            self.application,
            '/ws/trading/market/SPY/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Should receive comprehensive initial market data
        response = await communicator.receive_json_from()
        
        # Verify message structure
        self.assertEqual(response['type'], 'market_data_update')
        self.assertEqual(response['symbol'], 'SPY')
        self.assertIn('timestamp', response)
        self.assertIn('real_time_data', response)
        self.assertIn('technical_indicators', response)
        self.assertIn('algorithm_metrics', response)
        
        # Verify real-time data integration
        real_time_data = response['real_time_data']
        self.assertEqual(real_time_data['price'], 420.55)
        self.assertEqual(real_time_data['market_status'], 'open')
        
        # Verify technical indicators
        indicators = response['technical_indicators']
        self.assertGreater(len(indicators), 0)
        
        # Find RSI indicator
        rsi_indicator = next((ind for ind in indicators if ind['name'] == 'rsi'), None)
        self.assertIsNotNone(rsi_indicator)
        self.assertEqual(rsi_indicator['value'], 58.5)
        
        # Verify algorithm metrics
        algorithm_metrics = response['algorithm_metrics']
        self.assertIn('volatility_score', algorithm_metrics)
        self.assertIn('liquidity_score', algorithm_metrics)
        self.assertIn('execution_favorability', algorithm_metrics)
        
        # Verify score ranges (0-1)
        self.assertGreaterEqual(algorithm_metrics['volatility_score'], 0)
        self.assertLessEqual(algorithm_metrics['volatility_score'], 1)
        self.assertGreaterEqual(algorithm_metrics['liquidity_score'], 0)
        self.assertLessEqual(algorithm_metrics['liquidity_score'], 1)
        
        await communicator.disconnect()
    
    async def test_market_data_consumer_subscription_messages(self):
        """Test market data consumer subscription functionality"""
        communicator = WebsocketCommunicator(
            self.application,
            '/ws/trading/market/SPY/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Consume initial message
        await communicator.receive_json_from()
        
        # Test indicator subscription
        await communicator.send_json_to({
            'type': 'subscribe_indicators',
            'indicators': ['rsi', 'macd', 'bollinger_bands']
        })
        
        # Test algorithm data request
        await communicator.send_json_to({
            'type': 'request_algorithm_data'
        })
        
        await communicator.disconnect()
    
    async def test_market_data_consumer_error_handling(self):
        """Test error handling in enhanced market data consumer"""
        # Test with non-existent symbol
        communicator = WebsocketCommunicator(
            self.application,
            '/ws/trading/market/INVALID/'
        )
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Should receive error message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'error')
        self.assertIn('message', response)
        
        await communicator.disconnect()


class MarketDataSynchronizationTasksTestCase(TransactionTestCase):
    """Test Celery tasks for market data synchronization"""
    
    def setUp(self):
        """Set up task testing environment"""
        self.user = User.objects.create_user(
            username='task_user',
            email='task@test.com'
        )
        
        # Create minimal required structure
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
            symbol='AMZN',
            name='Amazon.com Inc.',
            exchange=self.real_exchange,
            sector=self.sector,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='AMZN'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
    
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine._get_enhanced_market_data')
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine.process_algorithm_step')
    def test_sync_algorithm_market_data_task(self, mock_process_step, mock_enhanced_data):
        """Test market data synchronization task"""
        # Create running algorithm
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now() - timedelta(minutes=30),
            end_time=timezone.now() + timedelta(hours=1),
            status='RUNNING'
        )
        
        # Create pending execution
        from apps.order_management.models import AlgorithmExecution
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now() - timedelta(minutes=5),  # Past due
            market_price=Decimal('3200.00')
        )
        
        # Mock enhanced market data
        mock_enhanced_data.return_value = {
            'last_price': Decimal('3205.50'),
            'bid_price': Decimal('3205.25'),
            'ask_price': Decimal('3205.75'),
            'volume': 2500000,
            'market_status': 'open',
            'technical_indicators': {
                'rsi': {'value': 62.5},
                'macd': {'value': {'signal': 'bullish'}}
            },
            'spread_bps': Decimal('15.6'),
            'data_source': 'market_data_integration'
        }
        
        # Mock successful execution
        mock_process_step.return_value = True
        
        # Import and run the task
        from apps.order_management.tasks import sync_algorithm_market_data
        result = sync_algorithm_market_data()
        
        # Verify task execution
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['algorithms_checked'], 1)
        self.assertEqual(result['executions_processed'], 1)
        
        # Verify algorithm was updated
        algo_order.refresh_from_db()
        self.assertIsNotNone(algo_order.last_market_check)
        
        # Verify method calls
        mock_enhanced_data.assert_called_once()
        mock_process_step.assert_called_once_with(execution)
    
    @patch('apps.market_data.tasks.calculate_technical_indicators_single.delay')
    def test_update_algorithm_technical_indicators_task(self, mock_calculate_indicators):
        """Test technical indicators update task"""
        # Create multiple running algorithms with different symbols
        symbols = ['AMZN', 'GOOGL', 'MSFT']
        for i, symbol in enumerate(symbols):
            if i > 0:  # Create additional tickers for other symbols
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
            else:
                instrument = self.instrument
            
            AlgorithmicOrder.objects.create(
                user=self.user,
                exchange=self.sim_exchange,
                instrument=instrument,
                algorithm_type='VWAP',
                side='BUY',
                total_quantity=500,
                start_time=timezone.now(),
                end_time=timezone.now() + timedelta(hours=2),
                status='RUNNING'
            )
        
        # Mock task return value
        mock_task = MagicMock()
        mock_task.id = 'test-task-id'
        mock_calculate_indicators.return_value = mock_task
        
        # Import and run the task
        from apps.order_management.tasks import update_algorithm_technical_indicators
        result = update_algorithm_technical_indicators()
        
        # Verify task execution
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['symbols_updated'], 3)
        self.assertEqual(len(result['task_ids']), 3)
        
        # Verify indicator calculation was called for each symbol
        self.assertEqual(mock_calculate_indicators.call_count, 3)
        
        # Verify call arguments
        call_args_list = mock_calculate_indicators.call_args_list
        called_symbols = [call[1]['symbol'] for call in call_args_list]
        self.assertEqual(set(called_symbols), set(symbols))
    
    def test_sync_task_with_no_running_algorithms(self):
        """Test sync task when no algorithms are running"""
        from apps.order_management.tasks import sync_algorithm_market_data
        result = sync_algorithm_market_data()
        
        self.assertEqual(result['status'], 'NO_RUNNING_ALGORITHMS')


class AlgorithmMarketDataAPITestCase(APITestCase):
    """Test algorithm market data API endpoint"""
    
    def setUp(self):
        """Set up API testing environment"""
        self.user = User.objects.create_user(
            username='api_user',
            email='api@test.com',
            password='testpass123'
        )
        
        # Create market data structure
        self.real_exchange = Exchange.objects.create(name='NYSE', code='NYSE')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated NYSE',
            code='SIM_NYSE',
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
            symbol='NVDA',
            name='NVIDIA Corporation',
            exchange=self.real_exchange,
            sector=self.sector,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='NVDA'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
        
        # Create test algorithm
        self.algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            status='RUNNING'
        )
        
        # Authenticate user
        self.client.force_authenticate(user=self.user)
    
    @patch('apps.order_management.algorithm_services.AlgorithmExecutionEngine._get_enhanced_market_data')
    def test_algorithm_market_data_endpoint(self, mock_enhanced_data):
        """Test algorithm market data API endpoint"""
        # Mock enhanced market data response
        mock_enhanced_data.return_value = {
            'last_price': Decimal('875.50'),
            'bid_price': Decimal('875.25'),
            'ask_price': Decimal('875.75'),
            'volume': 18500000,
            'market_status': 'open',
            'technical_indicators': {
                'rsi': {'value': 72.5, 'timestamp': timezone.now()},
                'macd': {'value': {'signal': 'bearish'}, 'timestamp': timezone.now()},
                'sma_20': {'value': 870.25, 'timestamp': timezone.now()}
            },
            'spread_bps': Decimal('57.1'),
            'volatility_24h': 0.035,
            'data_source': 'market_data_integration',
            'timestamp': timezone.now()
        }
        
        # Make API request
        url = reverse('algorithmic-orders-market-data', kwargs={'pk': self.algo_order.algo_order_id})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['algorithm_id'], str(self.algo_order.algo_order_id))
        self.assertEqual(data['symbol'], 'NVDA')
        self.assertIn('market_data', data)
        self.assertIn('algorithm_metrics', data)
        self.assertIn('timestamp', data)
        
        # Verify market data
        market_data = data['market_data']
        self.assertEqual(market_data['last_price'], '875.50')
        self.assertEqual(market_data['market_status'], 'open')
        self.assertIn('technical_indicators', market_data)
        
        # Verify algorithm metrics
        algorithm_metrics = data['algorithm_metrics']
        self.assertIn('execution_favorability', algorithm_metrics)
        self.assertIn('price_impact_estimate', algorithm_metrics)
        self.assertIn('optimal_execution_time', algorithm_metrics)
        
        # Verify execution favorability is calculated
        favorability = algorithm_metrics['execution_favorability']
        self.assertGreaterEqual(favorability, 0)
        self.assertLessEqual(favorability, 1)
        
        # Verify price impact estimate
        impact = algorithm_metrics['price_impact_estimate']
        self.assertIn('estimated_impact_bps', impact)
        self.assertIn('participation_rate', impact)
        self.assertIn('impact_level', impact)
        self.assertIn(impact['impact_level'], ['LOW', 'MEDIUM', 'HIGH'])
        
        # Verify enhanced market data service was called
        mock_enhanced_data.assert_called_once_with(self.instrument)
    
    def test_algorithm_market_data_not_found(self):
        """Test API endpoint with non-existent algorithm"""
        # Use random UUID
        import uuid
        random_uuid = uuid.uuid4()
        
        url = reverse('algorithmic-orders-market-data', kwargs={'pk': random_uuid})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.json())
    
    def test_algorithm_market_data_unauthorized(self):
        """Test API endpoint without authentication"""
        self.client.force_authenticate(user=None)
        
        url = reverse('algorithmic-orders-market-data', kwargs={'pk': self.algo_order.algo_order_id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_algorithm_market_data_wrong_user(self):
        """Test API endpoint with wrong user"""
        # Create another user
        other_user = User.objects.create_user(
            username='other_user',
            email='other@test.com',
            password='testpass123'
        )
        
        # Authenticate as other user
        self.client.force_authenticate(user=other_user)
        
        url = reverse('algorithmic-orders-market-data', kwargs={'pk': self.algo_order.algo_order_id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MarketDataIntegrationErrorHandlingTestCase(TransactionTestCase):
    """Test error handling and edge cases in market data integration"""
    
    def setUp(self):
        """Set up error testing environment"""
        self.user = User.objects.create_user(username='error_user', email='error@test.com')
        
        # Minimal setup
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
            symbol='ERROR_TEST',
            name='Error Test Corp.',
            exchange=self.real_exchange,
            sector=self.sector,
            data_source=self.data_source,
            currency='USD',
            country='US',
            yfinance_symbol='ERROR_TEST'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker,
            exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
        self.engine = AlgorithmExecutionEngine()
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    @patch('apps.market_data.models.MarketData.objects.filter')
    def test_enhanced_market_data_complete_failure(self, mock_market_data_filter, mock_real_time_quote):
        """Test enhanced market data when all sources fail"""
        # Mock all data sources to fail
        mock_real_time_quote.side_effect = Exception("YFinance API Error")
        mock_market_data_filter.side_effect = Exception("Database Error")
        
        # Should fall back to original method without crashing
        with patch.object(self.engine, '_get_market_data') as mock_original:
            mock_original.return_value = {
                'last_price': Decimal('100.00'),
                'bid_price': Decimal('99.95'),
                'ask_price': Decimal('100.05'),
                'volume': 10000,
                'spread_bps': Decimal('10.0')
            }
            
            result = self.engine._get_enhanced_market_data(self.instrument)
            
            # Should return fallback data
            self.assertEqual(result['last_price'], Decimal('100.00'))
            mock_original.assert_called_once_with(self.instrument)
    
    @patch('apps.market_data.services.YFinanceService.get_real_time_quote')
    def test_technical_indicator_execution_fallback(self, mock_real_time_quote):
        """Test technical indicator execution with missing indicators"""
        mock_real_time_quote.return_value = {
            'symbol': 'ERROR_TEST',
            'price': Decimal('50.00'),
            'market_status': 'open'
        }
        
        # Create algorithm with technical triggers but no indicators in database
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='SNIPER',
            side='BUY',
            total_quantity=100,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters={
                'use_rsi_trigger': True,
                'rsi_threshold': 70,
                'use_macd_trigger': True
            }
        )
        
        from apps.order_management.algorithm_services import SniperAlgorithm
        sniper = SniperAlgorithm(algo_order)
        
        # Get market data (should have empty technical indicators)
        market_data = self.engine._get_enhanced_market_data(self.instrument)
        
        # Should fall back to basic execution logic without crashing
        with patch.object(sniper, 'should_execute') as mock_basic_execute:
            mock_basic_execute.return_value = True
            
            result = sniper.should_execute_with_indicators(market_data)
            self.assertTrue(result)
            
            # Should have called basic execution as fallback
            mock_basic_execute.assert_called_once()
    
    @patch('apps.market_data.services.YFinanceService')
    def test_invalid_technical_indicator_data(self, mock_yfinance_service):
        """Test handling of corrupted technical indicator data"""
        # Create corrupted technical indicator
        TechnicalIndicator.objects.create(
            ticker=self.ticker,
            timestamp=timezone.now(),
            timeframe='1d',
            indicator_name='rsi',
            value=None,  # Invalid value
            values={'corrupted': 'data'},  # Invalid values structure
            parameters={}
        )
        
        # Mock YFinance service
        mock_service_instance = MagicMock()
        mock_service_instance.get_real_time_quote.return_value = {
            'symbol': 'ERROR_TEST',
            'price': Decimal('75.00'),
            'market_status': 'open'
        }
        mock_yfinance_service.return_value = mock_service_instance
        
        # Should handle corrupted data gracefully
        result = self.engine._get_enhanced_market_data(self.instrument)
        
        # Should include technical indicators section but handle invalid data
        self.assertIn('technical_indicators', result)
        indicators = result['technical_indicators']
        
        # Should include the indicator but with None value
        self.assertIn('rsi', indicators)
        self.assertIsNone(indicators['rsi']['value'])
