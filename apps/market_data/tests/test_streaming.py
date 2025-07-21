# apps/market_data/tests/test_streaming.py
"""
Tests for real-time streaming service
"""

import asyncio
import pytest
from django.test import TestCase
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from django.utils import timezone

from ..streaming.service import StreamingEngine, MarketDataPoint, StreamStatus, CacheManager
from ..models import Ticker, Exchange, DataSource


class StreamingServiceTests(TestCase):
    """Test suite for real-time streaming service"""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create test data source
        self.data_source = DataSource.objects.create(
            name="Test Data Source",
            code="TEST",
            url="https://test.com",
            requires_api_key=False
        )
        
        # Create test exchange and ticker
        self.exchange = Exchange.objects.create(
            name="Test Exchange",
            code="TEST",
            country="US",
            currency="USD"
        )
        
        self.ticker = Ticker.objects.create(
            symbol="TSLA",
            name="Tesla Inc",
            exchange=self.exchange,
            data_source=self.data_source
        )
    
    def tearDown(self):
        self.loop.close()
    
    def test_streaming_engine_initialization(self):
        """Test streaming engine initializes correctly"""
        engine = StreamingEngine(max_symbols=50, update_interval=2.0)
        
        self.assertEqual(engine.max_symbols, 50)
        self.assertEqual(engine.update_interval, 2.0)
        self.assertEqual(engine.status, StreamStatus.STOPPED)
        self.assertEqual(len(engine.active_symbols), 0)
        self.assertIsNotNone(engine.cache_manager)
        self.assertIsNotNone(engine.data_feed_manager)
    
    def test_symbol_subscription_and_unsubscription(self):
        """Test symbol subscription and unsubscription workflow"""
        engine = StreamingEngine()
        
        # Test subscription
        engine.subscribe_symbol("AAPL", high_frequency=True)
        self.assertIn("AAPL", engine.active_symbols)
        self.assertIn("AAPL", engine.high_frequency_symbols)
        self.assertEqual(engine.subscriber_counts["AAPL"], 1)
        
        # Test multiple subscriptions to same symbol
        engine.subscribe_symbol("AAPL", high_frequency=False)
        self.assertEqual(engine.subscriber_counts["AAPL"], 2)
        
        # Test partial unsubscription
        engine.unsubscribe_symbol("AAPL")
        self.assertEqual(engine.subscriber_counts["AAPL"], 1)
        self.assertIn("AAPL", engine.active_symbols)
        
        # Test complete unsubscription
        engine.unsubscribe_symbol("AAPL")
        self.assertNotIn("AAPL", engine.active_symbols)
        self.assertNotIn("AAPL", engine.high_frequency_symbols)
        self.assertNotIn("AAPL", engine.subscriber_counts)
    
    def test_market_data_point_creation_and_serialization(self):
        """Test MarketDataPoint creation, validation, and serialization"""
        now = timezone.now()
        data_point = MarketDataPoint(
            symbol="AAPL",
            timestamp=now,
            price=Decimal("150.00"),
            volume=1000,
            bid=Decimal("149.95"),
            ask=Decimal("150.05"),
            high_24h=Decimal("152.00"),
            low_24h=Decimal("148.00"),
            change_24h=Decimal("2.50"),
            change_pct_24h=1.69
        )
        
        # Test basic properties
        self.assertEqual(data_point.symbol, "AAPL")
        self.assertEqual(data_point.price, Decimal("150.00"))
        self.assertEqual(data_point.volume, 1000)
        self.assertEqual(data_point.bid, Decimal("149.95"))
        self.assertEqual(data_point.ask, Decimal("150.05"))
        
        # Test serialization to cache format
        cache_dict = data_point.to_cache_dict()
        self.assertIn('symbol', cache_dict)
        self.assertIn('price', cache_dict)
        self.assertIn('timestamp', cache_dict)
        self.assertEqual(cache_dict['symbol'], "AAPL")
        self.assertEqual(cache_dict['price'], "150.00")
        
        # Test deserialization from cache format
        reconstructed = MarketDataPoint.from_cache_dict(cache_dict)
        self.assertEqual(reconstructed.symbol, data_point.symbol)
        self.assertEqual(reconstructed.price, data_point.price)
        self.assertEqual(reconstructed.volume, data_point.volume)
        self.assertEqual(reconstructed.bid, data_point.bid)
        self.assertEqual(reconstructed.ask, data_point.ask)
    
    def test_cache_manager_basic_operations(self):
        """Test cache manager set/get operations"""
        cache_manager = CacheManager(cache_prefix="test_streaming")
        
        # Create test data point
        data_point = MarketDataPoint(
            symbol="AAPL",
            timestamp=timezone.now(),
            price=Decimal("150.00"),
            volume=1000
        )
        
        # Test caching with mocked cache
        with patch('apps.market_data.streaming.service.cache') as mock_cache:
            mock_cache.set.return_value = True
            mock_cache.get.return_value = data_point.to_cache_dict()
            
            # Test set operation
            result = cache_manager.set_quote(data_point, is_high_frequency=True)
            self.assertTrue(result)
            self.assertEqual(cache_manager.metrics['sets'], 1)
            
            # Test get operation - cache hit
            retrieved = cache_manager.get_quote("AAPL")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.symbol, "AAPL")
            self.assertEqual(retrieved.price, Decimal("150.00"))
            self.assertEqual(cache_manager.metrics['hits'], 1)
    
    def test_cache_manager_miss_scenario(self):
        """Test cache manager miss scenario"""
        cache_manager = CacheManager(cache_prefix="test_streaming")
        
        with patch('apps.market_data.streaming.service.cache') as mock_cache:
            mock_cache.get.return_value = None
            
            # Test cache miss
            retrieved = cache_manager.get_quote("NONEXISTENT")
            self.assertIsNone(retrieved)
            self.assertEqual(cache_manager.metrics['misses'], 1)
    
    def test_cache_manager_bulk_operations(self):
        """Test cache manager bulk get operations"""
        cache_manager = CacheManager(cache_prefix="test_streaming")
        
        # Create test data
        symbols = ["AAPL", "GOOGL", "MSFT"]
        test_data = {
            "test_streaming:quote:AAPL": {
                'symbol': 'AAPL',
                'timestamp': timezone.now().isoformat(),
                'price': '150.00',
                'volume': 1000,
                'bid': None,
                'ask': None,
                'high_24h': None,
                'low_24h': None,
                'change_24h': None,
                'change_pct_24h': None,
                'market_cap': None
            }
        }
        
        with patch('apps.market_data.streaming.service.cache') as mock_cache:
            mock_cache.get_many.return_value = test_data
            
            results = cache_manager.get_multiple_quotes(symbols)
            
            self.assertEqual(len(results), 3)
            self.assertIsNotNone(results["AAPL"])
            self.assertIsNone(results["GOOGL"])
            self.assertIsNone(results["MSFT"])
            self.assertEqual(cache_manager.metrics['hits'], 1)
            self.assertEqual(cache_manager.metrics['misses'], 2)
    
    def test_cache_stats_calculation(self):
        """Test cache statistics calculation"""
        cache_manager = CacheManager()
        
        # Simulate some cache operations
        cache_manager.metrics['hits'] = 80
        cache_manager.metrics['misses'] = 20
        cache_manager.metrics['sets'] = 50
        
        stats = cache_manager.get_cache_stats()
        
        self.assertEqual(stats['hits'], 80)
        self.assertEqual(stats['misses'], 20)
        self.assertEqual(stats['sets'], 50)
        self.assertEqual(stats['total_requests'], 100)
        self.assertEqual(stats['hit_ratio'], 0.8)
    
    @patch('apps.market_data.streaming.service.cache')
    def test_quote_freshness_validation(self, mock_cache):
        """Test quote freshness validation logic"""
        engine = StreamingEngine()
        
        # Use a fixed timestamp to avoid timing issues
        fixed_now = timezone.now()
        
        with patch('apps.market_data.streaming.service.timezone.now') as mock_now:
            mock_now.return_value = fixed_now
            
            # Test fresh quote (within 60 seconds)
            fresh_quote = MarketDataPoint(
                symbol="AAPL",
                timestamp=fixed_now - timezone.timedelta(seconds=30),
                price=Decimal("150.00"),
                volume=1000
            )
            self.assertTrue(engine._is_quote_fresh(fresh_quote, max_age_seconds=60))
            
            # Test stale quote (older than 60 seconds)
            stale_quote = MarketDataPoint(
                symbol="AAPL",
                timestamp=fixed_now - timezone.timedelta(seconds=120),
                price=Decimal("150.00"),
                volume=1000
            )
            self.assertFalse(engine._is_quote_fresh(stale_quote, max_age_seconds=60))
            
            # Test edge case - exactly at threshold
            edge_quote = MarketDataPoint(
                symbol="AAPL",
                timestamp=fixed_now - timezone.timedelta(seconds=60),
                price=Decimal("150.00"),
                volume=1000
            )
            self.assertTrue(engine._is_quote_fresh(edge_quote, max_age_seconds=60))
            
            # Test just over threshold
            over_threshold_quote = MarketDataPoint(
                symbol="AAPL",
                timestamp=fixed_now - timezone.timedelta(seconds=61),
                price=Decimal("150.00"),
                volume=1000
            )
            self.assertFalse(engine._is_quote_fresh(over_threshold_quote, max_age_seconds=60))
    
    def test_circuit_breaker_functionality(self):
        """Test circuit breaker pattern implementation"""
        from ..streaming.service import CircuitBreaker
        
        # Test initial state
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self.assertEqual(breaker.state, "CLOSED")
        self.assertTrue(breaker.can_execute())
        
        # Test failure accumulation
        breaker.on_failure()
        breaker.on_failure()
        self.assertEqual(breaker.state, "CLOSED")  # Still closed
        self.assertTrue(breaker.can_execute())
        
        # Test circuit opening
        breaker.on_failure()  # Third failure
        self.assertEqual(breaker.state, "OPEN")
        self.assertFalse(breaker.can_execute())
        
        # Test success resets counter
        breaker.state = "CLOSED"  # Reset for test
        breaker.failure_count = 2
        breaker.on_success()
        self.assertEqual(breaker.failure_count, 0)
        self.assertEqual(breaker.state, "CLOSED")
    
    def test_streaming_metrics_initialization(self):
        """Test streaming metrics data structure"""
        from ..streaming.service import StreamMetrics, DataQuality
        
        metrics = StreamMetrics()
        
        # Test default values
        self.assertEqual(metrics.quotes_processed, 0)
        self.assertEqual(metrics.quotes_cached, 0)
        self.assertEqual(metrics.events_published, 0)
        self.assertEqual(metrics.errors, 0)
        self.assertEqual(metrics.avg_latency_ms, 0.0)
        self.assertEqual(metrics.data_quality, DataQuality.UNKNOWN)
        
        # Test serialization
        metrics_dict = metrics.to_dict()
        self.assertIn('quotes_processed', metrics_dict)
        self.assertIn('data_quality', metrics_dict)
        self.assertEqual(metrics_dict['data_quality'], 'unknown')
    
    def test_streaming_engine_metrics_collection(self):
        """Test streaming engine metrics collection"""
        engine = StreamingEngine()
        
        # Add some symbols
        engine.subscribe_symbol("AAPL")
        engine.subscribe_symbol("GOOGL", high_frequency=True)
        
        # Mock data feed manager status
        with patch.object(engine.data_feed_manager, 'get_source_status') as mock_status:
            mock_status.return_value = {
                'yfinance': {'state': 'CLOSED', 'failure_count': 0, 'last_failure': None},
                'alphavantage': {'state': 'CLOSED', 'failure_count': 0, 'last_failure': None}
            }
            
            # Mock cache stats
            with patch.object(engine.cache_manager, 'get_cache_stats') as mock_cache_stats:
                mock_cache_stats.return_value = {
                    'hits': 100, 'misses': 10, 'sets': 90, 'hit_ratio': 0.91, 'total_requests': 110
                }
                
                metrics = engine.get_metrics()
                
                self.assertEqual(metrics['status'], 'stopped')
                self.assertEqual(metrics['active_symbols'], 2)
                self.assertEqual(metrics['high_frequency_symbols'], 1)
                self.assertEqual(metrics['total_subscribers'], 2)
                self.assertIn('performance', metrics)
                self.assertIn('cache_stats', metrics)
                self.assertIn('data_sources', metrics)
    
    def test_streaming_engine_symbol_management(self):
        """Test streaming engine symbol list management"""
        engine = StreamingEngine()
        
        # Test empty state
        self.assertEqual(len(engine.get_active_symbols()), 0)
        
        # Add symbols in random order
        symbols = ["MSFT", "AAPL", "GOOGL", "AMZN"]
        for symbol in symbols:
            engine.subscribe_symbol(symbol)
        
        # Test alphabetical sorting
        active_symbols = engine.get_active_symbols()
        expected_sorted = ["AAPL", "AMZN", "GOOGL", "MSFT"]
        self.assertEqual(active_symbols, expected_sorted)
        
        # Remove a symbol
        engine.unsubscribe_symbol("GOOGL")
        active_symbols = engine.get_active_symbols()
        self.assertEqual(len(active_symbols), 3)
        self.assertNotIn("GOOGL", active_symbols)


class StreamingIntegrationTests(TestCase):
    """Integration tests for streaming service with other components"""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create minimal test data
        self.data_source = DataSource.objects.create(
            name="Test Source", code="TEST", requires_api_key=False
        )
        self.exchange = Exchange.objects.create(
            name="NASDAQ", code="NASDAQ", country="US", currency="USD"
        )
        self.ticker = Ticker.objects.create(
            symbol="AAPL", name="Apple Inc", exchange=self.exchange, data_source=self.data_source
        )
    
    def tearDown(self):
        self.loop.close()
    
    @patch('apps.market_data.streaming.service.publish_market_data_update')
    @patch('apps.market_data.streaming.service.YFinanceService')
    def test_streaming_with_event_publishing(self, mock_yfinance_service, mock_publish_event):
        """Test streaming service integration with event system"""
        # Mock yfinance response
        mock_service_instance = mock_yfinance_service.return_value
        mock_service_instance.get_real_time_quote.return_value = {
            'price': 150.00,
            'volume': 1000,
            'timestamp': timezone.now(),
            'bid': 149.95,
            'ask': 150.05,
            'change': 2.50,
            'change_percent': 1.69
        }
        
        # Mock event publishing
        mock_publish_event.return_value = asyncio.Future()
        mock_publish_event.return_value.set_result(True)
        
        engine = StreamingEngine()
        engine.subscribe_symbol("AAPL")
        
        # Test symbol processing
        async def test_process():
            await engine._process_symbol("AAPL")
        
        self.loop.run_until_complete(test_process())
        
        # Verify event was published
        self.assertTrue(mock_publish_event.called)
        
        # Check call arguments
        call_args = mock_publish_event.call_args[1]  # Get keyword arguments
        self.assertEqual(call_args['symbol'], 'AAPL')
        self.assertEqual(call_args['volume'], 1000)
        self.assertEqual(call_args['exchange'], 'REAL_TIME')
    
    def test_streaming_engine_start_stop_cycle(self):
        """Test streaming engine start/stop lifecycle"""
        engine = StreamingEngine()
        
        # Test initial state
        self.assertEqual(engine.status, StreamStatus.STOPPED)
        
        # Add a symbol
        engine.subscribe_symbol("AAPL")
        
        # Mock the async operations to avoid actual network calls
        with patch.object(engine, '_main_streaming_loop') as mock_main_loop, \
             patch.object(engine, '_health_monitor_loop') as mock_health_loop, \
             patch.object(engine, '_initialize_ta_calculators') as mock_init_ta:
            
            # Mock coroutines
            mock_main_loop.return_value = asyncio.Future()
            mock_main_loop.return_value.set_result(None)
            mock_health_loop.return_value = asyncio.Future() 
            mock_health_loop.return_value.set_result(None)
            mock_init_ta.return_value = asyncio.Future()
            mock_init_ta.return_value.set_result(None)
            
            # Test start
            async def test_start():
                result = await engine.start()
                self.assertTrue(result)
                self.assertEqual(engine.status, StreamStatus.RUNNING)
            
            self.loop.run_until_complete(test_start())
            
            # Test stop
            async def test_stop():
                await engine.stop()
                self.assertEqual(engine.status, StreamStatus.STOPPED)
            
            self.loop.run_until_complete(test_stop())
