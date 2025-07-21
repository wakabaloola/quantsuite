# apps/market_data/streaming/service.py
"""
Enterprise Real-Time Market Data Streaming Service
=================================================

Production-grade streaming service that provides real-time market data with:
- High-frequency data polling and caching
- Event-driven market data distribution
- Redis caching for ultra-low latency
- Automatic technical analysis triggering
- WebSocket real-time broadcasting
- Circuit breaker pattern for external APIs
- Comprehensive monitoring and alerting

Architecture:
- StreamingEngine: Core orchestrator
- DataFeedManager: Manages multiple data sources
- CacheManager: Redis caching with intelligent TTL
- EventPublisher: Integration with event system
- HealthMonitor: Service health and performance tracking
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import concurrent.futures
from collections import defaultdict, deque

from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.core.events import publish_market_data_update, publish_technical_signal
from ..services import YFinanceService, AlphaVantageService
from ..models import Ticker, MarketData, DataSource
from ..technical_analysis import TechnicalAnalysisCalculator
from ..common import MarketDataPoint, StreamStatus, DataQuality

logger = logging.getLogger(__name__)


# StreamStatus, DataQuality, and MarketDataPoint are now imported from common module


@dataclass
class StreamMetrics:
    """Streaming service performance metrics"""
    quotes_processed: int = 0
    quotes_cached: int = 0
    events_published: int = 0
    websocket_broadcasts: int = 0
    technical_signals: int = 0
    errors: int = 0
    avg_latency_ms: float = 0.0
    cache_hit_ratio: float = 0.0
    data_quality: DataQuality = DataQuality.UNKNOWN
    last_update: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        data = asdict(self)
        data['data_quality'] = self.data_quality.value
        data['last_update'] = self.last_update.isoformat() if self.last_update else None
        return data


@dataclass
class MarketDataPoint:
    """Structured market data point"""
    symbol: str
    timestamp: datetime
    price: Decimal
    volume: int
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    high_24h: Optional[Decimal] = None
    low_24h: Optional[Decimal] = None
    change_24h: Optional[Decimal] = None
    change_pct_24h: Optional[float] = None
    market_cap: Optional[int] = None
    
    def to_cache_dict(self) -> Dict[str, Any]:
        """Convert to cache-friendly dictionary"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'price': str(self.price),
            'volume': self.volume,
            'bid': str(self.bid) if self.bid else None,
            'ask': str(self.ask) if self.ask else None,
            'high_24h': str(self.high_24h) if self.high_24h else None,
            'low_24h': str(self.low_24h) if self.low_24h else None,
            'change_24h': str(self.change_24h) if self.change_24h else None,
            'change_pct_24h': self.change_pct_24h,
            'market_cap': self.market_cap
        }
    
    @classmethod
    def from_cache_dict(cls, data: Dict[str, Any]) -> 'MarketDataPoint':
        """Create from cached dictionary"""
        return cls(
            symbol=data['symbol'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            price=Decimal(data['price']),
            volume=data['volume'],
            bid=Decimal(data['bid']) if data['bid'] else None,
            ask=Decimal(data['ask']) if data['ask'] else None,
            high_24h=Decimal(data['high_24h']) if data['high_24h'] else None,
            low_24h=Decimal(data['low_24h']) if data['low_24h'] else None,
            change_24h=Decimal(data['change_24h']) if data['change_24h'] else None,
            change_pct_24h=data['change_pct_24h'],
            market_cap=data['market_cap']
        )


class CircuitBreaker:
    """Circuit breaker pattern for external API calls"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return False
    
    def on_success(self):
        """Handle successful operation"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN: {self.failure_count} failures")


class CacheManager:
    """High-performance Redis cache manager for market data"""
    
    def __init__(self, cache_prefix: str = "streaming"):
        self.cache_prefix = cache_prefix
        self.default_ttl = 300  # 5 minutes
        self.high_frequency_ttl = 30  # 30 seconds for active symbols
        self.metrics = {'hits': 0, 'misses': 0, 'sets': 0}
    
    def _make_key(self, symbol: str, data_type: str = "quote") -> str:
        """Generate cache key"""
        return f"{self.cache_prefix}:{data_type}:{symbol.upper()}"
    
    def get_quote(self, symbol: str) -> Optional[MarketDataPoint]:
        """Get cached market data point"""
        try:
            cache_key = self._make_key(symbol, "quote")
            cached_data = cache.get(cache_key)
            
            if cached_data:
                self.metrics['hits'] += 1
                return MarketDataPoint.from_cache_dict(cached_data)
            else:
                self.metrics['misses'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Cache get error for {symbol}: {e}")
            self.metrics['misses'] += 1
            return None
    
    def set_quote(self, data_point: MarketDataPoint, is_high_frequency: bool = False) -> bool:
        """Cache market data point"""
        try:
            cache_key = self._make_key(data_point.symbol, "quote")
            ttl = self.high_frequency_ttl if is_high_frequency else self.default_ttl
            
            cache.set(cache_key, data_point.to_cache_dict(), ttl)
            self.metrics['sets'] += 1
            
            # Also set latest price for quick access
            price_key = self._make_key(data_point.symbol, "price")
            cache.set(price_key, {
                'price': str(data_point.price),
                'timestamp': data_point.timestamp.isoformat(),
                'volume': data_point.volume
            }, ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for {data_point.symbol}: {e}")
            return False
    
    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Optional[MarketDataPoint]]:
        """Get multiple cached quotes efficiently"""
        results = {}
        
        try:
            # Build cache keys
            cache_keys = [self._make_key(symbol, "quote") for symbol in symbols]
            cached_data = cache.get_many(cache_keys)
            
            # Process results
            for i, symbol in enumerate(symbols):
                cache_key = cache_keys[i]
                if cache_key in cached_data:
                    self.metrics['hits'] += 1
                    results[symbol] = MarketDataPoint.from_cache_dict(cached_data[cache_key])
                else:
                    self.metrics['misses'] += 1
                    results[symbol] = None
            
            return results
            
        except Exception as e:
            logger.error(f"Bulk cache get error: {e}")
            # Return empty results for all symbols
            return {symbol: None for symbol in symbols}
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.metrics['hits'] + self.metrics['misses']
        hit_ratio = self.metrics['hits'] / total_requests if total_requests > 0 else 0
        
        return {
            'hits': self.metrics['hits'],
            'misses': self.metrics['misses'],
            'sets': self.metrics['sets'],
            'hit_ratio': hit_ratio,
            'total_requests': total_requests
        }


class DataFeedManager:
    """Manages multiple data sources with failover"""
    
    def __init__(self):
        self.yfinance = YFinanceService()
        self.alpha_vantage = AlphaVantageService()
        self.circuit_breakers = {
            'yfinance': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
            'alphavantage': CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        }
        self.primary_source = 'yfinance'
        self.fallback_source = 'alphavantage'
    
    async def fetch_quote(self, symbol: str) -> Optional[MarketDataPoint]:
        """Fetch quote with failover logic"""
        # Try primary source first
        if self.circuit_breakers[self.primary_source].can_execute():
            try:
                quote_data = await self._fetch_from_yfinance(symbol)
                if quote_data:
                    self.circuit_breakers[self.primary_source].on_success()
                    return quote_data
                else:
                    self.circuit_breakers[self.primary_source].on_failure()
            except Exception as e:
                logger.warning(f"Primary source failed for {symbol}: {e}")
                self.circuit_breakers[self.primary_source].on_failure()
        
        # Try fallback source
        if self.circuit_breakers[self.fallback_source].can_execute():
            try:
                quote_data = await self._fetch_from_alphavantage(symbol)
                if quote_data:
                    self.circuit_breakers[self.fallback_source].on_success()
                    return quote_data
                else:
                    self.circuit_breakers[self.fallback_source].on_failure()
            except Exception as e:
                logger.warning(f"Fallback source failed for {symbol}: {e}")
                self.circuit_breakers[self.fallback_source].on_failure()
        
        logger.error(f"All data sources failed for {symbol}")
        return None
    
    async def _fetch_from_yfinance(self, symbol: str) -> Optional[MarketDataPoint]:
        """Fetch from Yahoo Finance"""
        try:
            quote_data = self.yfinance.get_real_time_quote(symbol)
            if not quote_data:
                return None
            
            return MarketDataPoint(
                symbol=symbol,
                timestamp=quote_data.get('timestamp', timezone.now()),
                price=Decimal(str(quote_data.get('price', 0))),
                volume=int(quote_data.get('volume', 0)),
                bid=Decimal(str(quote_data.get('bid', 0))) if quote_data.get('bid') else None,
                ask=Decimal(str(quote_data.get('ask', 0))) if quote_data.get('ask') else None,
                change_24h=Decimal(str(quote_data.get('change', 0))) if quote_data.get('change') else None,
                change_pct_24h=quote_data.get('change_percent'),
                market_cap=quote_data.get('market_cap')
            )
            
        except Exception as e:
            logger.error(f"YFinance fetch error for {symbol}: {e}")
            return None
    
    async def _fetch_from_alphavantage(self, symbol: str) -> Optional[MarketDataPoint]:
        """Fetch from Alpha Vantage"""
        try:
            # Alpha Vantage doesn't have real-time quotes in the current implementation
            # This would need to be implemented if using Alpha Vantage for real-time data
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage fetch error for {symbol}: {e}")
            return None
    
    def get_source_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all data sources"""
        return {
            source: {
                'state': breaker.state,
                'failure_count': breaker.failure_count,
                'last_failure': breaker.last_failure_time
            }
            for source, breaker in self.circuit_breakers.items()
        }


class StreamingEngine:
    """
    Core streaming engine that orchestrates real-time market data flow
    
    Features:
    - Multi-symbol concurrent streaming
    - Intelligent caching and data quality monitoring
    - Event-driven architecture integration
    - Technical analysis triggering
    - WebSocket broadcasting
    - Performance optimization
    """
    
    def __init__(self, max_symbols: int = 100, update_interval: float = 1.0):
        self.max_symbols = max_symbols
        self.update_interval = update_interval
        self.status = StreamStatus.STOPPED
        
        # Core components
        self.cache_manager = CacheManager()
        self.data_feed_manager = DataFeedManager()
        self.channel_layer = get_channel_layer()
        
        # Active subscriptions
        self.active_symbols: Set[str] = set()
        self.high_frequency_symbols: Set[str] = set()  # Symbols requiring faster updates
        self.subscriber_counts: Dict[str, int] = defaultdict(int)
        
        # Performance tracking
        self.metrics = StreamMetrics()
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Technical analysis integration
        self.ta_calculators: Dict[str, TechnicalAnalysisCalculator] = {}
        self.last_ta_check: Dict[str, datetime] = {}
        
        # Control flags
        self._shutdown_event = asyncio.Event()
        self._running_tasks: Set[asyncio.Task] = set()
    
    async def start(self) -> bool:
        """Start the streaming engine"""
        try:
            if self.status == StreamStatus.RUNNING:
                logger.warning("Streaming engine already running")
                return True
            
            logger.info("Starting streaming engine...")
            self.status = StreamStatus.STARTING
            
            # Initialize technical analysis calculators for active symbols
            await self._initialize_ta_calculators()
            
            # Start main streaming loop
            main_task = asyncio.create_task(self._main_streaming_loop())
            self._running_tasks.add(main_task)
            
            # Start health monitoring
            health_task = asyncio.create_task(self._health_monitor_loop())
            self._running_tasks.add(health_task)
            
            self.status = StreamStatus.RUNNING
            self.metrics.last_update = timezone.now()
            
            logger.info(f"Streaming engine started for {len(self.active_symbols)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start streaming engine: {e}")
            self.status = StreamStatus.ERROR
            return False
    
    async def stop(self):
        """Stop the streaming engine gracefully"""
        logger.info("Stopping streaming engine...")
        self.status = StreamStatus.STOPPED
        self._shutdown_event.set()
        
        # Cancel all running tasks
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        self._running_tasks.clear()
        logger.info("Streaming engine stopped")
    
    def subscribe_symbol(self, symbol: str, high_frequency: bool = False):
        """Subscribe to real-time data for a symbol"""
        symbol = symbol.upper()
        self.active_symbols.add(symbol)
        self.subscriber_counts[symbol] += 1
        
        if high_frequency:
            self.high_frequency_symbols.add(symbol)
        
        logger.info(f"Subscribed to {symbol} (HF: {high_frequency}). Total: {len(self.active_symbols)}")
    
    def unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from real-time data for a symbol"""
        symbol = symbol.upper()
        
        if symbol in self.subscriber_counts:
            self.subscriber_counts[symbol] -= 1
            
            if self.subscriber_counts[symbol] <= 0:
                self.active_symbols.discard(symbol)
                self.high_frequency_symbols.discard(symbol)
                del self.subscriber_counts[symbol]
                
                # Clean up
                if symbol in self.ta_calculators:
                    del self.ta_calculators[symbol]
                if symbol in self.last_ta_check:
                    del self.last_ta_check[symbol]
                if symbol in self.price_history:
                    del self.price_history[symbol]
        
        logger.info(f"Unsubscribed from {symbol}. Remaining: {len(self.active_symbols)}")
    
    async def get_current_quote(self, symbol: str) -> Optional[MarketDataPoint]:
        """Get current quote for symbol (cache-first)"""
        symbol = symbol.upper()
        
        # Try cache first
        cached_quote = self.cache_manager.get_quote(symbol)
        if cached_quote and self._is_quote_fresh(cached_quote):
            return cached_quote
        
        # Fetch fresh data
        fresh_quote = await self.data_feed_manager.fetch_quote(symbol)
        if fresh_quote:
            # Cache the fresh data
            is_hf = symbol in self.high_frequency_symbols
            self.cache_manager.set_quote(fresh_quote, is_hf)
        
        return fresh_quote
    
    def _is_quote_fresh(self, quote: MarketDataPoint, max_age_seconds: int = 60) -> bool:
        """Check if quote is fresh enough to use"""
        age = (timezone.now() - quote.timestamp).total_seconds()
        return age <= max_age_seconds
    
    async def _main_streaming_loop(self):
        """Main streaming loop that processes all active symbols"""
        while not self._shutdown_event.is_set():
            try:
                start_time = time.time()
                
                if not self.active_symbols:
                    await asyncio.sleep(self.update_interval)
                    continue
                
                # Process symbols in batches for efficiency
                batch_size = min(10, len(self.active_symbols))
                symbol_batches = [
                    list(self.active_symbols)[i:i + batch_size]
                    for i in range(0, len(self.active_symbols), batch_size)
                ]
                
                for batch in symbol_batches:
                    if self._shutdown_event.is_set():
                        break
                    
                    # Process batch concurrently
                    tasks = [self._process_symbol(symbol) for symbol in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # Update metrics
                processing_time = (time.time() - start_time) * 1000
                self.metrics.avg_latency_ms = (
                    self.metrics.avg_latency_ms * 0.9 + processing_time * 0.1
                )
                self.metrics.last_update = timezone.now()
                
                # Dynamic sleep based on processing time
                sleep_time = max(0.1, self.update_interval - (time.time() - start_time))
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Streaming loop error: {e}")
                self.metrics.errors += 1
                await asyncio.sleep(1)  # Brief pause on error
    
    async def _process_symbol(self, symbol: str):
        """Process a single symbol's market data"""
        try:
            # Fetch current quote
            quote = await self.data_feed_manager.fetch_quote(symbol)
            if not quote:
                return
            
            # Cache the quote
            is_hf = symbol in self.high_frequency_symbols
            self.cache_manager.set_quote(quote, is_hf)
            
            # Update price history
            self.price_history[symbol].append({
                'price': quote.price,
                'timestamp': quote.timestamp,
                'volume': quote.volume
            })
            
            # Publish market data event
            await self._publish_market_data_event(quote)
            
            # Check for technical analysis signals
            await self._check_technical_signals(symbol, quote)
            
            # Broadcast via WebSocket
            await self._broadcast_quote_update(quote)
            
            # Update metrics
            self.metrics.quotes_processed += 1
            self.metrics.quotes_cached += 1
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            self.metrics.errors += 1
    
    async def _publish_market_data_event(self, quote: MarketDataPoint):
        """Publish market data update event"""
        try:
            price_data = {
                'close': quote.price,
                'bid': quote.bid or quote.price,
                'ask': quote.ask or quote.price,
                'high_24h': quote.high_24h,
                'low_24h': quote.low_24h,
                'change_24h': quote.change_24h,
                'change_pct_24h': quote.change_pct_24h
            }
            
            # Remove None values
            price_data = {k: v for k, v in price_data.items() if v is not None}
            
            await publish_market_data_update(
                symbol=quote.symbol,
                price_data=price_data,
                volume=quote.volume,
                exchange="REAL_TIME"
            )
            
            self.metrics.events_published += 1
            
        except Exception as e:
            logger.error(f"Event publishing failed for {quote.symbol}: {e}")
    
    async def _check_technical_signals(self, symbol: str, quote: MarketDataPoint):
        """Check for technical analysis signals"""
        try:
            # Throttle TA checks - once per minute
            now = timezone.now()
            last_check = self.last_ta_check.get(symbol)
            
            if last_check and (now - last_check).total_seconds() < 60:
                return
            
            self.last_ta_check[symbol] = now
            
            # Get price history for calculations
            if len(self.price_history[symbol]) < 14:  # Need minimum data for RSI
                return
            
            # Initialize TA calculator if needed
            if symbol not in self.ta_calculators:
                try:
                    ticker = Ticker.objects.get(symbol=symbol, is_active=True)
                    self.ta_calculators[symbol] = TechnicalAnalysisCalculator(symbol)
                except Ticker.DoesNotExist:
                    return
            
            calculator = self.ta_calculators[symbol]
            
            # Calculate RSI for signal detection
            try:
                rsi_data = calculator.calculate_rsi(period=14, timeframe='1m')
                current_rsi = rsi_data.get('current_value')
                
                if current_rsi:
                    # Generate signals based on RSI
                    signal_type = "neutral"
                    signal_strength = 0.5
                    
                    if current_rsi > 70:
                        signal_type = "sell"
                        signal_strength = min(1.0, (current_rsi - 70) / 20)
                    elif current_rsi < 30:
                        signal_type = "buy"
                        signal_strength = min(1.0, (30 - current_rsi) / 20)
                    
                    # Only publish strong signals
                    if signal_strength > 0.6:
                        await publish_technical_signal(
                            symbol=symbol,
                            indicator="rsi",
                            signal_type=signal_type,
                            signal_strength=signal_strength,
                            indicator_value=float(current_rsi)
                        )
                        
                        self.metrics.technical_signals += 1
                        
                        logger.info(f"Technical signal: {symbol} RSI {signal_type} "
                                  f"(strength: {signal_strength:.2f}, value: {current_rsi:.2f})")
            
            except Exception as ta_error:
                logger.debug(f"TA calculation error for {symbol}: {ta_error}")
            
        except Exception as e:
            logger.error(f"Technical signal check failed for {symbol}: {e}")
    
    async def _broadcast_quote_update(self, quote: MarketDataPoint):
        """Broadcast quote update via WebSocket"""
        try:
            if not self.channel_layer:
                return
            
            message = {
                'type': 'price_update',
                'data': {
                    'symbol': quote.symbol,
                    'price': float(quote.price),
                    'volume': quote.volume,
                    'timestamp': quote.timestamp.isoformat(),
                    'bid': float(quote.bid) if quote.bid else None,
                    'ask': float(quote.ask) if quote.ask else None,
                    'change_24h': float(quote.change_24h) if quote.change_24h else None,
                    'change_pct_24h': quote.change_pct_24h
                }
            }
            
            # Broadcast to symbol-specific group
            await self.channel_layer.group_send(f'market_{quote.symbol}', message)
            
            # Broadcast to global market data group
            await self.channel_layer.group_send('market_data_global', message)
            
            self.metrics.websocket_broadcasts += 1
            
        except Exception as e:
            logger.error(f"WebSocket broadcast failed for {quote.symbol}: {e}")
    
    async def _initialize_ta_calculators(self):
        """Initialize technical analysis calculators for active symbols"""
        for symbol in list(self.active_symbols):
            try:
                ticker = Ticker.objects.get(symbol=symbol, is_active=True)
                self.ta_calculators[symbol] = TechnicalAnalysisCalculator(symbol)
            except Ticker.DoesNotExist:
                logger.warning(f"Ticker not found for symbol {symbol}")
                continue
    
    async def _health_monitor_loop(self):
        """Monitor service health and performance"""
        while not self._shutdown_event.is_set():
            try:
                # Update cache statistics
                cache_stats = self.cache_manager.get_cache_stats()
                self.metrics.cache_hit_ratio = cache_stats['hit_ratio']
                
                # Assess data quality
                if self.metrics.quotes_processed > 0:
                    error_rate = self.metrics.errors / self.metrics.quotes_processed
                    if error_rate < 0.01:
                        self.metrics.data_quality = DataQuality.EXCELLENT
                    elif error_rate < 0.05:
                        self.metrics.data_quality = DataQuality.GOOD
                    elif error_rate < 0.15:
                        self.metrics.data_quality = DataQuality.FAIR
                    else:
                        self.metrics.data_quality = DataQuality.POOR
                
                # Log performance summary every 5 minutes
                if self.metrics.quotes_processed % 100 == 0:
                    logger.info(f"Streaming performance: "
                              f"{self.metrics.quotes_processed} quotes, "
                              f"{self.metrics.avg_latency_ms:.1f}ms avg latency, "
                              f"{self.metrics.cache_hit_ratio:.1%} cache hit rate, "
                              f"{self.metrics.data_quality.value} quality")
                
                await asyncio.sleep(30)  # Health check every 30 seconds
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive streaming metrics"""
        data_sources_status = self.data_feed_manager.get_source_status()
        cache_stats = self.cache_manager.get_cache_stats()
        
        return {
            'status': self.status.value,
            'active_symbols': len(self.active_symbols),
            'high_frequency_symbols': len(self.high_frequency_symbols),
            'total_subscribers': sum(self.subscriber_counts.values()),
            'performance': self.metrics.to_dict(),
            'cache_stats': cache_stats,
            'data_sources': data_sources_status,
            'symbol_counts': dict(self.subscriber_counts)
        }
    
    def get_active_symbols(self) -> List[str]:
        """Get list of actively streamed symbols"""
        return sorted(list(self.active_symbols))


# Global streaming engine instance
streaming_engine = StreamingEngine()
