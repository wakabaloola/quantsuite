# Performance Optimization Guide

## ⚡ Executive Summary

Comprehensive performance optimization for QSuite trading platform, implementing high-frequency trading optimizations, database tuning, caching strategies, and system-level performance enhancements.

---

## 🗄️ Database Optimization

### PostgreSQL Configuration for Trading Workloads

```sql
-- postgresql.conf optimizations for trading platform
-- Apply these in production PostgreSQL configuration

-- Memory settings
shared_buffers = 4GB                    # 25% of RAM for dedicated DB server
effective_cache_size = 12GB             # 75% of RAM
work_mem = 256MB                        # For complex queries and sorts
maintenance_work_mem = 2GB              # For index builds and maintenance

-- Connection settings
max_connections = 200                   # Adjust based on load
superuser_reserved_connections = 3

-- WAL settings for high write throughput
wal_level = replica
max_wal_size = 4GB
min_wal_size = 1GB
checkpoint_completion_target = 0.9
wal_buffers = 64MB

-- Query planner
random_page_cost = 1.1                  # For SSD storage
effective_io_concurrency = 200          # Number of concurrent disk I/O operations

-- Background writer
bgwriter_delay = 50ms
bgwriter_lru_maxpages = 1000
bgwriter_lru_multiplier = 10.0

-- Logging for performance monitoring
log_min_duration_statement = 100        # Log queries > 100ms
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
```

### Database Index Optimization

```python
# apps/market_data/migrations/0002_optimize_indexes.py
from django.db import migrations

class Migration(migrations.Migration):
    
    dependencies = [
        ('market_data', '0001_initial'),
    ]
    
    operations = [
        # Composite indexes for common query patterns
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_market_data_ticker_timestamp ON market_data_marketdata (ticker_id, timestamp DESC);",
            reverse_sql="DROP INDEX IF EXISTS idx_market_data_ticker_timestamp;"
        ),
        
        # Partial indexes for active records
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_active_tickers ON market_data_ticker (symbol) WHERE is_active = true;",
            reverse_sql="DROP INDEX IF EXISTS idx_active_tickers;"
        ),
        
        # Index for real-time queries
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_recent_market_data ON market_data_marketdata (timestamp DESC) WHERE timestamp > (NOW() - INTERVAL '1 day');",
            reverse_sql="DROP INDEX IF EXISTS idx_recent_market_data;"
        ),
        
        # Covering index for order queries
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_orders_covering ON execution_engine_order (created_by_id, status, created_at DESC) INCLUDE (ticker_id, order_type, side, quantity);",
            reverse_sql="DROP INDEX IF EXISTS idx_orders_covering;"
        ),
        
        # Hash index for exact matches
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_ticker_symbol_hash ON market_data_ticker USING hash (symbol);",
            reverse_sql="DROP INDEX IF EXISTS idx_ticker_symbol_hash;"
        ),
        
        # Functional index for case-insensitive searches
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_ticker_symbol_lower ON market_data_ticker (LOWER(symbol));",
            reverse_sql="DROP INDEX IF EXISTS idx_ticker_symbol_lower;"
        ),
        
        # Index for time-series analytics
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_market_data_analytics ON market_data_marketdata (ticker_id, timestamp) INCLUDE (open, high, low, close, volume);",
            reverse_sql="DROP INDEX IF EXISTS idx_market_data_analytics;"
        ),
    ]
```

### Query Optimization

```python
# apps/market_data/optimized_queries.py
from django.db import models, connection
from django.db.models import Prefetch, Q, F, Window
from django.db.models.functions import Lag, Lead, Row_Number
from decimal import Decimal
from typing import List, Dict, Optional

class OptimizedMarketDataManager(models.Manager):
    """Optimized queries for market data operations"""
    
    def get_latest_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Get latest prices for multiple symbols efficiently"""
        
        # Use window function to get latest price per symbol
        latest_prices = self.filter(
            ticker__symbol__in=symbols,
            ticker__is_active=True
        ).annotate(
            row_num=Window(
                expression=Row_Number(),
                partition_by=[F('ticker_id')],
                order_by=F('timestamp').desc()
            )
        ).filter(row_num=1).values('ticker__symbol', 'close')
        
        return {item['ticker__symbol']: item['close'] for item in latest_prices}
    
    def get_ohlcv_data(self, symbol: str, limit: int = 100):
        """Get OHLCV data with optimized query"""
        
        return self.select_related('ticker').filter(
            ticker__symbol=symbol,
            ticker__is_active=True
        ).order_by('-timestamp').values(
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        )[:limit]
    
    def get_price_changes(self, symbols: List[str]):
        """Calculate price changes efficiently using window functions"""
        
        return self.filter(
            ticker__symbol__in=symbols
        ).annotate(
            prev_close=Window(
                expression=Lag('close', 1),
                partition_by=[F('ticker_id')],
                order_by=F('timestamp')
            ),
            price_change=F('close') - F('prev_close'),
            price_change_pct=(F('close') - F('prev_close')) / F('prev_close') * 100
        ).filter(
            prev_close__isnull=False
        ).order_by('-timestamp')

class OptimizedOrderManager(models.Manager):
    """Optimized queries for order operations"""
    
    def get_user_positions(self, user_id: int):
        """Calculate user positions efficiently"""
        
        # Use aggregation to calculate net positions
        positions = self.filter(
            created_by_id=user_id,
            status='FILLED'
        ).values('ticker__symbol').annotate(
            net_quantity=models.Sum(
                models.Case(
                    models.When(side='BUY', then=F('filled_quantity')),
                    default=-F('filled_quantity'),
                    output_field=models.DecimalField()
                )
            ),
            avg_price=models.Avg('avg_fill_price'),
            total_value=models.Sum(
                F('filled_quantity') * F('avg_fill_price')
            )
        ).filter(net_quantity__gt=0)
        
        return positions
    
    def get_order_book_depth(self, symbol: str, levels: int = 10):
        """Get order book depth efficiently"""
        
        buy_orders = self.filter(
            ticker__symbol=symbol,
            side='BUY',
            status='PENDING',
            order_type='LIMIT'
        ).values('price').annotate(
            total_quantity=models.Sum('quantity')
        ).order_by('-price')[:levels]
        
        sell_orders = self.filter(
            ticker__symbol=symbol,
            side='SELL', 
            status='PENDING',
            order_type='LIMIT'
        ).values('price').annotate(
            total_quantity=models.Sum('quantity')
        ).order_by('price')[:levels]
        
        return {
            'bids': list(buy_orders),
            'asks': list(sell_orders)
        }

# Raw SQL for complex analytics
class MarketDataAnalytics:
    """Raw SQL queries for complex market data analytics"""
    
    @staticmethod
    def get_trading_volume_by_hour():
        """Get trading volume aggregated by hour"""
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    DATE_TRUNC('hour', timestamp) as hour,
                    ticker__symbol,
                    SUM(volume) as total_volume,
                    COUNT(*) as tick_count,
                    AVG(close) as avg_price
                FROM market_data_marketdata 
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', timestamp), ticker__symbol
                ORDER BY hour DESC, total_volume DESC
            """)
            
            return [
                {
                    'hour': row[0],
                    'symbol': row[1], 
                    'volume': row[2],
                    'tick_count': row[3],
                    'avg_price': row[4]
                }
                for row in cursor.fetchall()
            ]
    
    @staticmethod
    def get_price_volatility(symbol: str, days: int = 30):
        """Calculate price volatility using raw SQL"""
        
        with connection.cursor() as cursor:
            cursor.execute("""
                WITH daily_returns AS (
                    SELECT 
                        DATE(timestamp) as trade_date,
                        close,
                        LAG(close) OVER (ORDER BY DATE(timestamp)) as prev_close
                    FROM market_data_marketdata md
                    JOIN market_data_ticker t ON md.ticker_id = t.id
                    WHERE t.symbol = %s 
                    AND timestamp >= NOW() - INTERVAL '%s days'
                    GROUP BY DATE(timestamp), close
                    ORDER BY trade_date
                ),
                returns AS (
                    SELECT 
                        trade_date,
                        (close - prev_close) / prev_close as daily_return
                    FROM daily_returns 
                    WHERE prev_close IS NOT NULL
                )
                SELECT 
                    STDDEV(daily_return) * SQRT(252) as annualized_volatility,
                    AVG(daily_return) * 252 as annualized_return,
                    MIN(daily_return) as min_daily_return,
                    MAX(daily_return) as max_daily_return
                FROM returns
            """, [symbol, days])
            
            row = cursor.fetchone()
            return {
                'annualized_volatility': float(row[0]) if row[0] else 0,
                'annualized_return': float(row[1]) if row[1] else 0,
                'min_daily_return': float(row[2]) if row[2] else 0,
                'max_daily_return': float(row[3]) if row[3] else 0,
            }
```

---

## 🚀 Caching Strategy

### Redis Caching Implementation

```python
# apps/core/cache.py
from django.core.cache import cache
from django.conf import settings
import json
import hashlib
from decimal import Decimal
from typing import Any, Optional, Dict, List
import redis

class TradingCache:
    """High-performance caching for trading operations"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.CACHES['default']['LOCATION'])
        self.default_timeout = 300  # 5 minutes
    
    def get_market_data_key(self, symbol: str) -> str:
        """Generate cache key for market data"""
        return f"market_data:{symbol}"
    
    def get_order_book_key(self, symbol: str) -> str:
        """Generate cache key for order book"""
        return f"order_book:{symbol}"
    
    def get_user_positions_key(self, user_id: int) -> str:
        """Generate cache key for user positions"""
        return f"positions:{user_id}"
    
    def cache_latest_price(self, symbol: str, price: Decimal, timeout: int = 10):
        """Cache latest price with short TTL"""
        key = f"price:{symbol}"
        self.redis_client.setex(key, timeout, str(price))
    
    def get_latest_price(self, symbol: str) -> Optional[Decimal]:
        """Get latest price from cache"""
        key = f"price:{symbol}"
        cached_price = self.redis_client.get(key)
        
        if cached_price:
            return Decimal(cached_price.decode())
        return None
    
    def cache_order_book(self, symbol: str, order_book: Dict, timeout: int = 5):
        """Cache order book with very short TTL"""
        key = self.get_order_book_key(symbol)
        data = json.dumps(order_book, default=str)
        self.redis_client.setex(key, timeout, data)
    
    def get_order_book(self, symbol: str) -> Optional[Dict]:
        """Get order book from cache"""
        key = self.get_order_book_key(symbol)
        cached_data = self.redis_client.get(key)
        
        if cached_data:
            return json.loads(cached_data.decode())
        return None
    
    def cache_market_data(self, symbol: str, data: List[Dict], timeout: int = 60):
        """Cache market data with medium TTL"""
        key = self.get_market_data_key(symbol)
        serialized_data = json.dumps(data, default=str)
        self.redis_client.setex(key, timeout, serialized_data)
    
    def get_market_data(self, symbol: str) -> Optional[List[Dict]]:
        """Get market data from cache"""
        key = self.get_market_data_key(symbol)
        cached_data = self.redis_client.get(key)
        
        if cached_data:
            return json.loads(cached_data.decode())
        return None
    
    def invalidate_symbol_cache(self, symbol: str):
        """Invalidate all cache entries for a symbol"""
        pattern = f"*:{symbol}"
        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)
    
    def cache_user_positions(self, user_id: int, positions: List[Dict], timeout: int = 300):
        """Cache user positions"""
        key = self.get_user_positions_key(user_id)
        data = json.dumps(positions, default=str)
        self.redis_client.setex(key, timeout, data)
    
    def get_user_positions(self, user_id: int) -> Optional[List[Dict]]:
        """Get user positions from cache"""
        key = self.get_user_positions_key(user_id)
        cached_data = self.redis_client.get(key)
        
        if cached_data:
            return json.loads(cached_data.decode())
        return None
    
    def cache_analytics_result(self, query_hash: str, result: Any, timeout: int = 1800):
        """Cache analytics computation results"""
        key = f"analytics:{query_hash}"
        data = json.dumps(result, default=str)
        self.redis_client.setex(key, timeout, data)
    
    def get_analytics_result(self, query_hash: str) -> Optional[Any]:
        """Get cached analytics result"""
        key = f"analytics:{query_hash}"
        cached_data = self.redis_client.get(key)
        
        if cached_data:
            return json.loads(cached_data.decode())
        return None

# Global cache instance
trading_cache = TradingCache()

# Cache decorators
def cache_market_data(timeout=60):
    """Decorator to cache market data queries"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"query:{func.__name__}:{hashlib.md5(str(args + tuple(kwargs.items())).encode()).hexdigest()}"
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            return result
        
        return wrapper
    return decorator

def cache_user_data(timeout=300):
    """Decorator to cache user-specific data"""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            user_id = getattr(self, 'user_id', args[0] if args else 'unknown')
            cache_key = f"user:{user_id}:{func.__name__}:{hashlib.md5(str(args[1:] + tuple(kwargs.items())).encode()).hexdigest()}"
            
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            result = func(self, *args, **kwargs)
            cache.set(cache_key, result, timeout)
            return result
        
        return wrapper
    return decorator
```

### Cache Warming and Preloading

```python
# apps/market_data/cache_warming.py
from celery import shared_task
from .models import Ticker, MarketData
from apps.core.cache import trading_cache
from django.utils import timezone
from datetime import timedelta

@shared_task
def warm_price_cache():
    """Warm cache with latest prices for all active symbols"""
    
    active_tickers = Ticker.objects.filter(is_active=True)
    
    for ticker in active_tickers:
        try:
            latest_data = MarketData.objects.filter(
                ticker=ticker
            ).latest('timestamp')
            
            # Cache latest price with short TTL
            trading_cache.cache_latest_price(
                ticker.symbol, 
                latest_data.close, 
                timeout=30
            )
            
        except MarketData.DoesNotExist:
            continue

@shared_task
def warm_market_data_cache():
    """Warm cache with recent market data for popular symbols"""
    
    # Get most actively traded symbols
    popular_symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']
    
    for symbol in popular_symbols:
        try:
            ticker = Ticker.objects.get(symbol=symbol, is_active=True)
            
            # Get recent OHLCV data
            recent_data = MarketData.objects.filter(
                ticker=ticker,
                timestamp__gte=timezone.now() - timedelta(days=1)
            ).order_by('-timestamp').values(
                'timestamp', 'open', 'high', 'low', 'close', 'volume'
            )[:100]
            
            # Cache market data
            trading_cache.cache_market_data(
                symbol,
                list(recent_data),
                timeout=300
            )
            
        except Ticker.DoesNotExist:
            continue

@shared_task
def preload_user_positions():
    """Preload positions for active users"""
    from django.contrib.auth import get_user_model
    from apps.execution_engine.models import Order
    
    User = get_user_model()
    
    # Get users with recent trading activity
    recent_date = timezone.now() - timedelta(days=7)
    active_users = User.objects.filter(
        order__created_at__gte=recent_date
    ).distinct()
    
    for user in active_users:
        try:
            # Calculate positions
            positions = Order.objects.filter(
                created_by=user,
                status='FILLED'
            ).values('ticker__symbol').annotate(
                net_quantity=models.Sum(
                    models.Case(
                        models.When(side='BUY', then=F('filled_quantity')),
                        default=-F('filled_quantity'),
                        output_field=models.DecimalField()
                    )
                )
            ).filter(net_quantity__gt=0)
            
            # Cache positions
            trading_cache.cache_user_positions(
                user.id,
                list(positions),
                timeout=600
            )
            
        except Exception:
            continue

# Schedule cache warming tasks
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'warm-price-cache': {
        'task': 'apps.market_data.cache_warming.warm_price_cache',
        'schedule': 30.0,  # Every 30 seconds
    },
    'warm-market-data-cache': {
        'task': 'apps.market_data.cache_warming.warm_market_data_cache',
        'schedule': 300.0,  # Every 5 minutes
    },
    'preload-user-positions': {
        'task': 'apps.market_data.cache_warming.preload_user_positions',
        'schedule': crontab(minute='*/10'),  # Every 10 minutes
    },
}
```

---

## ⚡ API Performance Optimization

### Optimized Serializers

```python
# apps/market_data/optimized_serializers.py
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from .models import MarketData, Ticker
from apps.core.cache import cache_market_data
import time

class HighPerformanceMarketDataSerializer(serializers.ModelSerializer):
    """Optimized serializer for high-frequency market data"""
    
    symbol = serializers.CharField(source='ticker.symbol', read_only=True)
    
    class Meta:
        model = MarketData
        fields = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    def to_representation(self, instance):
        """Optimized serialization using minimal processing"""
        
        # Use direct attribute access to avoid ORM overhead
        return {
            'symbol': instance.ticker_symbol if hasattr(instance, 'ticker_symbol') else instance.ticker.symbol,
            'timestamp': instance.timestamp.isoformat(),
            'open': str(instance.open),
            'high': str(instance.high),
            'low': str(instance.low),
            'close': str(instance.close),
            'volume': str(instance.volume),
        }

class BulkMarketDataSerializer(serializers.Serializer):
    """Optimized serializer for bulk operations"""
    
    data = serializers.ListField(
        child=serializers.DictField(),
        max_length=10000  # Limit bulk size
    )
    
    def validate_data(self, value):
        """Validate bulk data efficiently"""
        
        if len(value) > 10000:
            raise serializers.ValidationError("Maximum 10,000 records per batch")
        
        # Batch validation
        required_fields = {'symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume'}
        
        for i, record in enumerate(value):
            missing_fields = required_fields - set(record.keys())
            if missing_fields:
                raise serializers.ValidationError(
                    f"Record {i}: Missing fields {missing_fields}"
                )
        
        return value

class CachedTickerSerializer(serializers.ModelSerializer):
    """Ticker serializer with caching"""
    
    latest_price = SerializerMethodField()
    
    class Meta:
        model = Ticker
        fields = ['id', 'symbol', 'name', 'currency', 'latest_price']
    
    @cache_market_data(timeout=30)  # Cache for 30 seconds
    def get_latest_price(self, obj):
        """Get latest price with caching"""
        from apps.core.cache import trading_cache
        
        # Try cache first
        cached_price = trading_cache.get_latest_price(obj.symbol)
        if cached_price:
            return str(cached_price)
        
        # Fallback to database
        try:
            latest_data = obj.marketdata_set.latest('timestamp')
            price = latest_data.close
            
            # Cache the result
            trading_cache.cache_latest_price(obj.symbol, price, timeout=30)
            
            return str(price)
        except MarketData.DoesNotExist:
            return None
```

### High-Performance ViewSets

```python
# apps/market_data/optimized_views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Prefetch
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from .models import MarketData, Ticker
from .optimized_serializers import HighPerformanceMarketDataSerializer
from apps.core.cache import trading_cache
import time

class HighPerformanceMarketDataViewSet(viewsets.ReadOnlyModelViewSet):
    """Optimized viewset for market data operations"""
    
    serializer_class = HighPerformanceMarketDataSerializer
    
    def get_queryset(self):
        """Optimized queryset with select_related"""
        return MarketData.objects.select_related(
            'ticker'
        ).prefetch_related(
            Prefetch(
                'ticker',
                queryset=Ticker.objects.only('symbol', 'name')
            )
        )
    
    @method_decorator(cache_page(60))  # Cache for 1 minute
    @method_decorator(vary_on_headers('Authorization'))
    def list(self, request):
        """Cached list endpoint"""
        return super().list(request)
    
    @action(detail=False, methods=['get'])
    def latest_prices(self, request):
        """Get latest prices for multiple symbols"""
        symbols = request.query_params.get('symbols', '').split(',')
        
        if not symbols or symbols == ['']:
            return Response({'error': 'symbols parameter required'}, status=400)
        
        # Check cache first
        cache_key = f"latest_prices:{','.join(sorted(symbols))}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return Response(cached_result)
        
        # Use optimized manager method
        from .optimized_queries import OptimizedMarketDataManager
        manager = OptimizedMarketDataManager()
        manager.model = MarketData
        
        latest_prices = manager.get_latest_prices(symbols)
        
        result = {
            'prices': latest_prices,
            'timestamp': time.time(),
            'count': len(latest_prices)
        }
        
        # Cache result for 10 seconds
        cache.set(cache_key, result, 10)
        
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def ohlcv(self, request):
        """Get OHLCV data with caching"""
        symbol = request.query_params.get('symbol')
        limit = min(int(request.query_params.get('limit', 100)), 1000)
        
        if not symbol:
            return Response({'error': 'symbol parameter required'}, status=400)
        
        # Check cache
        cached_data = trading_cache.get_market_data(symbol)
        if cached_data:
            return Response({
                'symbol': symbol,
                'data': cached_data[:limit],
                'cached': True
            })
        
        # Use optimized query
        from .optimized_queries import OptimizedMarketDataManager
        manager = OptimizedMarketDataManager()
        manager.model = MarketData
        
        ohlcv_data = list(manager.get_ohlcv_data(symbol, limit))
        
        # Cache result
        trading_cache.cache_market_data(symbol, ohlcv_data, timeout=60)
        
        return Response({
            'symbol': symbol,
            'data': ohlcv_data,
            'cached': False
        })
    
    @action(detail=False, methods=['post'])
    def bulk_ingest(self, request):
        """High-performance bulk data ingestion"""
        start_time = time.time()
        
        serializer = BulkMarketDataSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        data_records = serializer.validated_data['data']
        
        # Use bulk_create for performance
        market_data_objects = []
        ticker_cache = {}
        
        for record in data_records:
            symbol = record['symbol']
            
            # Cache ticker lookups
            if symbol not in ticker_cache:
                try:
                    ticker_cache[symbol] = Ticker.objects.get(symbol=symbol)
                except Ticker.DoesNotExist:
                    continue
            
            ticker = ticker_cache[symbol]
            
            market_data_objects.append(MarketData(
                ticker=ticker,
                timestamp=record['timestamp'],
                open=record['open'],
                high=record['high'],
                low=record['low'],
                close=record['close'],
                volume=record['volume']
            ))
        
        # Bulk create with batch size
        created_objects = MarketData.objects.bulk_create(
            market_data_objects,
            batch_size=1000,
            ignore_conflicts=True
        )
        
        # Invalidate related caches
        affected_symbols = set(ticker_cache.keys())
        for symbol in affected_symbols:
            trading_cache.invalidate_symbol_cache(symbol)
        
        processing_time = time.time() - start_time
        
        return Response({
            'created': len(created_objects),
            'processing_time_ms': round(processing_time * 1000, 2),
            'records_per_second': round(len(created_objects) / processing_time, 2) if processing_time > 0 else 0
        })
```

---

## 🔄 Celery Performance Optimization

### Optimized Celery Configuration

```python
# config/celery_optimized.py
from celery import Celery
from kombu import Queue, Exchange
import os

app = Celery('qsuite')

# Optimized broker settings
app.conf.update(
    # Connection settings
    broker_url='redis://redis:6379/0',
    result_backend='redis://redis:6379/0',
    
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Performance settings
    worker_prefetch_multiplier=1,  # Disable prefetching for better load balancing
    task_acks_late=True,           # Acknowledge tasks after completion
    worker_disable_rate_limits=True,
    
    # Result settings
    result_expires=3600,           # Expire results after 1 hour
    result_compression='gzip',     # Compress results
    
    # Task routing
    task_routes={
        'apps.execution_engine.tasks.execute_market_order': {'queue': 'execution'},
        'apps.analytics.tasks.*': {'queue': 'analytics'},
        'apps.market_data.tasks.*': {'queue': 'data_processing'},
        'apps.core.tasks.*': {'queue': 'general'},
    },
    
    # Queue configuration
    task_queues=(
        Queue('execution', Exchange('execution'), routing_key='execution',
              queue_arguments={'x-max-priority': 10}),
        Queue('analytics', Exchange('analytics'), routing_key='analytics'),
        Queue('data_processing', Exchange('data_processing'), routing_key='data_processing'),
        Queue('general', Exchange('general'), routing_key='general'),
    ),
    
    # Priority settings
    task_default_priority=5,
    worker_hijack_root_logger=False,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Memory optimization
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_max_memory_per_child=200000,  # 200MB memory limit
)

# Priority task configuration
HIGH_PRIORITY_TASKS = [
    'apps.execution_engine.tasks.execute_market_order',
    'apps.execution_engine.tasks.risk_check_order',
]

MEDIUM_PRIORITY_TASKS = [
    'apps.market_data.tasks.process_real_time_data',
    'apps.analytics.tasks.calculate_technical_indicators',
]

LOW_PRIORITY_TASKS = [
    'apps.analytics.tasks.run_backtest',
    'apps.core.tasks.cleanup_old_data',
]
```

### High-Performance Tasks

```python
# apps/execution_engine/optimized_tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction
from decimal import Decimal
import time
import redis

logger = get_task_logger(__name__)
redis_client = redis.Redis.from_url('redis://redis:6379/0')

@shared_task(bind=True, priority=9, max_retries=3)
def execute_order_high_performance(self, order_id, priority='normal'):
    """High-performance order execution with optimizations"""
    
    start_time = time.time()
    
    try:
        from .models import Order, Execution
        
        # Use select_for_update to prevent race conditions
        with transaction.atomic():
            order = Order.objects.select_for_update().select_related(
                'ticker', 'strategy', 'created_by'
            ).get(id=order_id)
            
            if order.status != 'PENDING':
                return {'error': 'Order already processed', 'order_id': order_id}
            
            # Fast market data lookup using Redis
            market_price = get_market_price_from_cache(order.ticker.symbol)
            
            if not market_price:
                # Fallback to database with optimized query
                from apps.market_data.models import MarketData
                latest_data = MarketData.objects.filter(
                    ticker=order.ticker
                ).latest('timestamp')
                market_price = latest_data.close
            
            # Calculate execution price with slippage
            slippage_factor = Decimal('0.0001')  # 0.01% slippage
            if order.side == 'BUY':
                execution_price = market_price * (1 + slippage_factor)
            else:
                execution_price = market_price * (1 - slippage_factor)
            
            # Create execution record
            execution = Execution.objects.create(
                order=order,
                quantity=order.quantity,
                price=execution_price,
                commission=calculate_commission(order.quantity, execution_price)
            )
            
            # Update order status
            order.status = 'FILLED'
            order.filled_quantity = order.quantity
            order.avg_fill_price = execution_price
            order.save(update_fields=['status', 'filled_quantity', 'avg_fill_price'])
            
            # Cache latest price
            cache_market_price(order.ticker.symbol, execution_price)
            
            # Update metrics
            from apps.core.metrics import TradingMetrics
            execution_time = time.time() - start_time
            TradingMetrics.record_order_filled(order, execution_time)
            
            return {
                'order_id': order_id,
                'execution_price': float(execution_price),
                'quantity': float(order.quantity),
                'execution_time_ms': round(execution_time * 1000, 2),
                'execution_id': execution.id
            }
    
    except Exception as exc:
        logger.error(f"Order execution failed: {exc}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** self.request.retries, exc=exc)
        
        # Mark order as rejected after max retries
        try:
            Order.objects.filter(id=order_id).update(status='REJECTED')
        except:
            pass
        
        return {'error': str(exc), 'order_id': order_id}

def get_market_price_from_cache(symbol):
    """Get market price from Redis cache"""
    cache_key = f"price:{symbol}"
    cached_price = redis_client.get(cache_key)
    
    if cached_price:
        return Decimal(cached_price.decode())
    return None

def cache_market_price(symbol, price):
    """Cache market price in Redis"""
    cache_key = f"price:{symbol}"
    redis_client.setex(cache_key, 30, str(price))  # Cache for 30 seconds

def calculate_commission(quantity, price):
    """Calculate trading commission"""
    # Simple commission: $0.005 per share
    return quantity * Decimal('0.005')

@shared_task(priority=7)
def batch_process_market_data(data_batch):
    """Batch process market data for better throughput"""
    
    from apps.market_data.models import MarketData, Ticker
    from django.db import transaction
    
    start_time = time.time()
    
    # Pre-fetch all tickers to avoid N+1 queries
    symbols = {record['symbol'] for record in data_batch}
    ticker_map = {
        ticker.symbol: ticker 
        for ticker in Ticker.objects.filter(symbol__in=symbols)
    }
    
    market_data_objects = []
    
    for record in data_batch:
        symbol = record['symbol']
        if symbol in ticker_map:
            market_data_objects.append(MarketData(
                ticker=ticker_map[symbol],
                timestamp=record['timestamp'],
                open=record['open'],
                high=record['high'], 
                low=record['low'],
                close=record['close'],
                volume=record['volume']
            ))
    
    # Bulk create with optimized batch size
    with transaction.atomic():
        created_objects = MarketData.objects.bulk_create(
            market_data_objects,
            batch_size=5000,
            ignore_conflicts=True
        )
    
    # Update cache for affected symbols
    for symbol in symbols:
        if symbol in ticker_map:
            # Invalidate cache to force refresh
            redis_client.delete(f"market_data:{symbol}")
    
    processing_time = time.time() - start_time
    
    return {
        'processed': len(created_objects),
        'processing_time_ms': round(processing_time * 1000, 2),
        'throughput': round(len(created_objects) / processing_time, 2)
    }

@shared_task(priority=3)
def cleanup_expired_cache():
    """Clean up expired cache entries"""
    
    # Get all cache keys
    keys = redis_client.keys('*')
    
    expired_count = 0
    for key in keys:
        ttl = redis_client.ttl(key)
        if ttl == -1:  # No expiration set
            # Set default expiration for cache entries
            if key.decode().startswith(('price:', 'market_data:', 'order_book:')):
                redis_client.expire(key, 3600)  # 1 hour default
                expired_count += 1
    
    return {'keys_processed': len(keys), 'expirations_set': expired_count}
```

---

## 📊 System Performance Monitoring

### Performance Monitoring Tasks

```python
# apps/core/performance_monitoring.py
from celery import shared_task
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import psutil
import time

@shared_task
def monitor_system_performance():
    """Monitor system performance metrics"""
    
    metrics = {
        'timestamp': timezone.now().isoformat(),
        'database': get_database_metrics(),
        'cache': get_cache_metrics(),
        'system': get_system_metrics(),
        'application': get_application_metrics()
    }
    
    # Store metrics for trending
    cache.set('system_metrics', metrics, 300)  # 5 minutes
    
    # Check for performance issues
    check_performance_thresholds(metrics)
    
    return metrics

def get_database_metrics():
    """Get database performance metrics"""
    
    with connection.cursor() as cursor:
        # Active connections
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
        active_connections = cursor.fetchone()[0]
        
        # Long running queries
        cursor.execute("""
            SELECT count(*) FROM pg_stat_activity 
            WHERE state = 'active' 
            AND query_start < NOW() - INTERVAL '30 seconds'
        """)
        long_queries = cursor.fetchone()[0]
        
        # Database size
        cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        db_size = cursor.fetchone()[0]
        
        # Cache hit ratio
        cursor.execute("""
            SELECT round(
                sum(blks_hit) * 100.0 / (sum(blks_hit) + sum(blks_read)), 2
            ) as cache_hit_ratio
            FROM pg_stat_database 
            WHERE datname = current_database()
        """)
        cache_hit_ratio = cursor.fetchone()[0]
    
    return {
        'active_connections': active_connections,
        'long_running_queries': long_queries,
        'database_size': db_size,
        'cache_hit_ratio': float(cache_hit_ratio) if cache_hit_ratio else 0
    }

def get_cache_metrics():
    """Get Redis cache metrics"""
    
    from apps.core.cache import trading_cache
    
    try:
        info = trading_cache.redis_client.info()
        
        return {
            'used_memory': info['used_memory_human'],
            'connected_clients': info['connected_clients'],
            'ops_per_sec': info.get('instantaneous_ops_per_sec', 0),
            'keyspace_hits': info.get('keyspace_hits', 0),
            'keyspace_misses': info.get('keyspace_misses', 0),
            'hit_rate': calculate_hit_rate(info)
        }
    
    except Exception:
        return {'error': 'Unable to get cache metrics'}

def calculate_hit_rate(redis_info):
    """Calculate cache hit rate"""
    hits = redis_info.get('keyspace_hits', 0)
    misses = redis_info.get('keyspace_misses', 0)
    
    if hits + misses == 0:
        return 0
    
    return round((hits / (hits + misses)) * 100, 2)

def get_system_metrics():
    """Get system resource metrics"""
    
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent': psutil.disk_usage('/').percent,
        'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
    }

def get_application_metrics():
    """Get application-specific metrics"""
    
    from apps.execution_engine.models import Order
    from apps.market_data.models import MarketData
    
    now = timezone.now()
    last_hour = now - timedelta(hours=1)
    last_minute = now - timedelta(minutes=1)
    
    return {
        'orders_last_hour': Order.objects.filter(created_at__gte=last_hour).count(),
        'orders_last_minute': Order.objects.filter(created_at__gte=last_minute).count(),
        'market_data_last_hour': MarketData.objects.filter(timestamp__gte=last_hour).count(),
        'pending_orders': Order.objects.filter(status='PENDING').count(),
    }

def check_performance_thresholds(metrics):
    """Check performance thresholds and alert if needed"""
    
    alerts = []
    
    # Database thresholds
    db_metrics = metrics.get('database', {})
    if db_metrics.get('cache_hit_ratio', 100) < 95:
        alerts.append('Database cache hit ratio below 95%')
    
    if db_metrics.get('long_running_queries', 0) > 5:
        alerts.append('Too many long-running queries')
    
    # System thresholds
    sys_metrics = metrics.get('system', {})
    if sys_metrics.get('cpu_percent', 0) > 80:
        alerts.append('High CPU usage')
    
    if sys_metrics.get('memory_percent', 0) > 90:
        alerts.append('High memory usage')
    
    # Cache thresholds
    cache_metrics = metrics.get('cache', {})
    if cache_metrics.get('hit_rate', 100) < 80:
        alerts.append('Low cache hit rate')
    
    # Send alerts if any issues found
    if alerts:
        from apps.core.alerting import alert_manager
        alert_manager.send_trading_alert(
            alert_type='performance_degradation',
            message=f"Performance issues detected: {', '.join(alerts)}",
            severity='warning',
            metrics=metrics
        )

@shared_task
def performance_report():
    """Generate performance report"""
    
    metrics = cache.get('system_metrics', {})
    
    if not metrics:
        return {'error': 'No recent metrics available'}
    
    # Calculate performance scores
    scores = {
        'database_score': calculate_database_score(metrics.get('database', {})),
        'cache_score': calculate_cache_score(metrics.get('cache', {})),
        'system_score': calculate_system_score(metrics.get('system', {})),
    }
    
    overall_score = sum(scores.values()) / len(scores)
    
    return {
        'overall_score': round(overall_score, 2),
        'individual_scores': scores,
        'metrics': metrics,
        'recommendations': generate_recommendations(scores, metrics)
    }

def calculate_database_score(db_metrics):
    """Calculate database performance score"""
    score = 100
    
    # Deduct points for performance issues
    cache_hit_ratio = db_metrics.get('cache_hit_ratio', 100)
    if cache_hit_ratio < 95:
        score -= (95 - cache_hit_ratio) * 2
    
    long_queries = db_metrics.get('long_running_queries', 0)
    if long_queries > 0:
        score -= long_queries * 5
    
    return max(0, score)

def calculate_cache_score(cache_metrics):
    """Calculate cache performance score"""
    hit_rate = cache_metrics.get('hit_rate', 100)
    return max(0, hit_rate)

def calculate_system_score(sys_metrics):
    """Calculate system performance score"""
    score = 100
    
    cpu_usage = sys_metrics.get('cpu_percent', 0)
    if cpu_usage > 70:
        score -= (cpu_usage - 70) * 2
    
    memory_usage = sys_metrics.get('memory_percent', 0)
    if memory_usage > 80:
        score -= (memory_usage - 80) * 3
    
    return max(0, score)

def generate_recommendations(scores, metrics):
    """Generate performance improvement recommendations"""
    recommendations = []
    
    if scores['database_score'] < 80:
        recommendations.append("Consider optimizing database queries and adding indexes")
    
    if scores['cache_score'] < 80:
        recommendations.append("Review cache strategy and increase cache TTL where appropriate")
    
    if scores['system_score'] < 80:
        recommendations.append("Monitor system resources and consider scaling")
    
    return recommendations
```

This comprehensive performance optimization guide provides:

✅ **Database tuning** with PostgreSQL optimizations for trading workloads  
✅ **Advanced caching** with Redis and intelligent cache warming  
✅ **API optimization** with efficient serializers and viewsets  
✅ **Celery performance** with optimized task routing and prioritization  
✅ **System monitoring** with automated performance tracking  
✅ **Query optimization** using database indexes and efficient ORM usage  

The optimizations are specifically tailored for high-frequency trading operations and financial data processing.
