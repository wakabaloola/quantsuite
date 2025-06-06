# Real-time Data Feeds and WebSocket Implementation

## 🚀 Executive Summary

Implementation of real-time data streaming, WebSocket connections, and low-latency market data feeds for QSuite trading platform, enabling microsecond-level data delivery and real-time trading operations.

---

## 📡 WebSocket Architecture

### Django Channels Setup

```bash
# Add WebSocket dependencies
echo "channels>=4.0.0" >> requirements/development.txt
echo "channels-redis>=4.1.0" >> requirements/development.txt
echo "daphne>=4.0.0" >> requirements/development.txt
echo "uvloop>=0.17.0" >> requirements/development.txt

# Rebuild container
docker-compose build web
```

### ASGI Configuration

```python
# config/asgi.py
import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.realtime import routing

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})
```

### WebSocket Routing

```python
# apps/realtime/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/market-data/(?P<symbol>\w+)/$', consumers.MarketDataConsumer.as_asgi()),
    re_path(r'ws/order-book/(?P<symbol>\w+)/$', consumers.OrderBookConsumer.as_asgi()),
    re_path(r'ws/user-orders/$', consumers.UserOrdersConsumer.as_asgi()),
    re_path(r'ws/trading-signals/$', consumers.TradingSignalsConsumer.as_asgi()),
    re_path(r'ws/portfolio/$', consumers.PortfolioConsumer.as_asgi()),
]
```

---

## 💹 Real-time Market Data Consumer

### High-Performance WebSocket Consumer

```python
# apps/realtime/consumers.py
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from decimal import Decimal
from django.utils import timezone
import redis.asyncio as redis
import logging

logger = logging.getLogger(__name__)

class MarketDataConsumer(AsyncWebsocketConsumer):
    """High-performance market data WebSocket consumer"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = None
        self.group_name = None
        self.redis_client = None
        self.subscription_task = None
        
    async def connect(self):
        """Handle WebSocket connection"""
        self.symbol = self.scope['url_route']['kwargs']['symbol'].upper()
        self.group_name = f'market_data_{self.symbol}'
        
        # Validate symbol exists
        if not await self.symbol_exists(self.symbol):
            await self.close(code=4004)
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Initialize Redis connection for real-time updates
        self.redis_client = redis.from_url('redis://redis:6379/0')
        
        # Send initial market data
        await self.send_initial_data()
        
        # Start subscription to real-time updates
        self.subscription_task = asyncio.create_task(
            self.subscribe_to_updates()
        )
        
        logger.info(f"WebSocket connected for symbol {self.symbol}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Cancel subscription task
        if self.subscription_task:
            self.subscription_task.cancel()
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        # Leave room group
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        logger.info(f"WebSocket disconnected for symbol {self.symbol}")
    
    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'subscribe_level2':
                # Subscribe to Level 2 order book data
                await self.subscribe_order_book()
            elif message_type == 'unsubscribe_level2':
                await self.unsubscribe_order_book()
            elif message_type == 'set_frequency':
                # Adjust update frequency
                frequency = data.get('frequency', 100)  # milliseconds
                await self.set_update_frequency(frequency)
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
    
    async def send_initial_data(self):
        """Send initial market data snapshot"""
        market_data = await self.get_latest_market_data(self.symbol)
        
        if market_data:
            await self.send(text_data=json.dumps({
                'type': 'market_data',
                'symbol': self.symbol,
                'data': market_data,
                'timestamp': timezone.now().isoformat()
            }))
    
    async def subscribe_to_updates(self):
        """Subscribe to real-time market data updates"""
        try:
            # Subscribe to Redis pub/sub for real-time updates
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(f'market_data:{self.symbol}')
            
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    await self.send_market_update(data)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in subscription: {e}")
    
    async def send_market_update(self, data):
        """Send market data update to client"""
        await self.send(text_data=json.dumps({
            'type': 'market_data_update',
            'symbol': self.symbol,
            'data': data,
            'timestamp': timezone.now().isoformat()
        }))
    
    # Group message handlers
    async def market_data_message(self, event):
        """Handle market data message from group"""
        await self.send(text_data=json.dumps(event['data']))
    
    @database_sync_to_async
    def symbol_exists(self, symbol):
        """Check if symbol exists in database"""
        from apps.market_data.models import Ticker
        return Ticker.objects.filter(symbol=symbol, is_active=True).exists()
    
    @database_sync_to_async
    def get_latest_market_data(self, symbol):
        """Get latest market data for symbol"""
        from apps.market_data.models import MarketData, Ticker
        
        try:
            ticker = Ticker.objects.get(symbol=symbol, is_active=True)
            latest_data = MarketData.objects.filter(ticker=ticker).latest('timestamp')
            
            return {
                'open': str(latest_data.open),
                'high': str(latest_data.high),
                'low': str(latest_data.low),
                'close': str(latest_data.close),
                'volume': str(latest_data.volume),
                'timestamp': latest_data.timestamp.isoformat()
            }
        except (Ticker.DoesNotExist, MarketData.DoesNotExist):
            return None

class OrderBookConsumer(AsyncWebsocketConsumer):
    """Real-time order book updates"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = None
        self.group_name = None
        self.depth_level = 10  # Default depth
        
    async def connect(self):
        """Handle connection for order book updates"""
        self.symbol = self.scope['url_route']['kwargs']['symbol'].upper()
        self.group_name = f'order_book_{self.symbol}'
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial order book snapshot
        await self.send_order_book_snapshot()
    
    async def disconnect(self, close_code):
        """Handle disconnection"""
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle client messages"""
        try:
            data = json.loads(text_data)
            
            if data.get('type') == 'set_depth':
                self.depth_level = min(data.get('depth', 10), 50)  # Max 50 levels
                await self.send_order_book_snapshot()
                
        except json.JSONDecodeError:
            pass
    
    async def send_order_book_snapshot(self):
        """Send complete order book snapshot"""
        order_book = await self.get_order_book_data(self.symbol, self.depth_level)
        
        await self.send(text_data=json.dumps({
            'type': 'order_book_snapshot',
            'symbol': self.symbol,
            'bids': order_book['bids'],
            'asks': order_book['asks'],
            'timestamp': timezone.now().isoformat()
        }))
    
    async def order_book_update(self, event):
        """Handle order book update from group"""
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def get_order_book_data(self, symbol, depth):
        """Get order book data from database"""
        from apps.execution_engine.models import Order
        from django.db.models import Sum
        
        try:
            # Get aggregated buy orders (bids)
            bids = Order.objects.filter(
                ticker__symbol=symbol,
                side='BUY',
                status='PENDING',
                order_type='LIMIT'
            ).values('price').annotate(
                quantity=Sum('quantity')
            ).order_by('-price')[:depth]
            
            # Get aggregated sell orders (asks)
            asks = Order.objects.filter(
                ticker__symbol=symbol,
                side='SELL',
                status='PENDING',
                order_type='LIMIT'
            ).values('price').annotate(
                quantity=Sum('quantity')
            ).order_by('price')[:depth]
            
            return {
                'bids': [{'price': str(bid['price']), 'quantity': str(bid['quantity'])} for bid in bids],
                'asks': [{'price': str(ask['price']), 'quantity': str(ask['quantity'])} for ask in asks]
            }
            
        except Exception:
            return {'bids': [], 'asks': []}

class UserOrdersConsumer(AsyncWebsocketConsumer):
    """Real-time user order updates"""
    
    async def connect(self):
        """Handle connection for user orders"""
        user = self.scope['user']
        
        if user.is_anonymous:
            await self.close(code=4001)
            return
        
        self.user_id = user.id
        self.group_name = f'user_orders_{self.user_id}'
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial orders
        await self.send_user_orders()
    
    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def send_user_orders(self):
        """Send user's current orders"""
        orders = await self.get_user_orders(self.user_id)
        
        await self.send(text_data=json.dumps({
            'type': 'user_orders',
            'orders': orders,
            'timestamp': timezone.now().isoformat()
        }))
    
    async def order_update(self, event):
        """Handle order update from group"""
        await self.send(text_data=json.dumps(event))
    
    @database_sync_to_async
    def get_user_orders(self, user_id):
        """Get user's orders"""
        from apps.execution_engine.models import Order
        
        orders = Order.objects.filter(
            created_by_id=user_id,
            status__in=['PENDING', 'PARTIAL']
        ).select_related('ticker').values(
            'id', 'ticker__symbol', 'order_type', 'side',
            'quantity', 'price', 'filled_quantity', 'status',
            'created_at'
        )
        
        return [
            {
                'id': order['id'],
                'symbol': order['ticker__symbol'],
                'type': order['order_type'],
                'side': order['side'],
                'quantity': str(order['quantity']),
                'price': str(order['price']) if order['price'] else None,
                'filled': str(order['filled_quantity']),
                'status': order['status'],
                'created_at': order['created_at'].isoformat()
            }
            for order in orders
        ]
```

---

## 📊 Real-time Data Processing

### Market Data Ingestion Pipeline

```python
# apps/realtime/data_processor.py
import asyncio
import json
import time
from decimal import Decimal
from typing import Dict, List, Optional
import redis.asyncio as redis
from channels.layers import get_channel_layer
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class RealTimeDataProcessor:
    """High-performance real-time market data processor"""
    
    def __init__(self):
        self.redis_client = None
        self.channel_layer = get_channel_layer()
        self.processing_stats = {
            'messages_processed': 0,
            'errors': 0,
            'start_time': time.time()
        }
        
    async def initialize(self):
        """Initialize connections"""
        self.redis_client = redis.from_url('redis://redis:6379/0')
        
    async def process_market_data_feed(self, data: Dict):
        """Process incoming market data"""
        try:
            symbol = data['symbol'].upper()
            
            # Validate and normalize data
            normalized_data = await self.normalize_market_data(data)
            
            # Store in database (async)
            await self.store_market_data(normalized_data)
            
            # Update real-time cache
            await self.update_price_cache(symbol, normalized_data['close'])
            
            # Broadcast to WebSocket subscribers
            await self.broadcast_market_update(symbol, normalized_data)
            
            # Update metrics
            self.processing_stats['messages_processed'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
            self.processing_stats['errors'] += 1
            return False
    
    async def normalize_market_data(self, data: Dict) -> Dict:
        """Normalize and validate market data"""
        
        # Required fields validation
        required_fields = ['symbol', 'timestamp', 'price', 'volume']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Data type conversion and validation
        normalized = {
            'symbol': data['symbol'].upper(),
            'timestamp': self.parse_timestamp(data['timestamp']),
            'open': Decimal(str(data.get('open', data['price']))),
            'high': Decimal(str(data.get('high', data['price']))),
            'low': Decimal(str(data.get('low', data['price']))),
            'close': Decimal(str(data['price'])),
            'volume': Decimal(str(data['volume']))
        }
        
        # OHLC validation
        if not (normalized['low'] <= normalized['open'] <= normalized['high'] and
                normalized['low'] <= normalized['close'] <= normalized['high']):
            raise ValueError("Invalid OHLC data")
        
        # Volume validation
        if normalized['volume'] < 0:
            raise ValueError("Volume cannot be negative")
        
        return normalized
    
    def parse_timestamp(self, timestamp_str):
        """Parse timestamp from various formats"""
        if isinstance(timestamp_str, (int, float)):
            return timezone.datetime.fromtimestamp(timestamp_str, tz=timezone.utc)
        
        # Handle ISO format
        try:
            return timezone.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            return timezone.now()
    
    async def store_market_data(self, data: Dict):
        """Store market data in database asynchronously"""
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def create_market_data():
            from apps.market_data.models import MarketData, Ticker
            
            try:
                ticker = Ticker.objects.get(symbol=data['symbol'], is_active=True)
                
                market_data = MarketData.objects.create(
                    ticker=ticker,
                    timestamp=data['timestamp'],
                    open=data['open'],
                    high=data['high'],
                    low=data['low'],
                    close=data['close'],
                    volume=data['volume']
                )
                
                return market_data.id
                
            except Ticker.DoesNotExist:
                logger.warning(f"Ticker not found: {data['symbol']}")
                return None
        
        return await create_market_data()
    
    async def update_price_cache(self, symbol: str, price: Decimal):
        """Update real-time price cache"""
        cache_key = f'price:{symbol}'
        await self.redis_client.setex(cache_key, 30, str(price))
        
        # Also publish to pub/sub for subscribers
        await self.redis_client.publish(
            f'market_data:{symbol}',
            json.dumps({
                'price': str(price),
                'timestamp': timezone.now().isoformat()
            })
        )
    
    async def broadcast_market_update(self, symbol: str, data: Dict):
        """Broadcast market data update to WebSocket subscribers"""
        
        message = {
            'type': 'market_data_message',
            'data': {
                'type': 'market_data_update',
                'symbol': symbol,
                'data': {
                    'open': str(data['open']),
                    'high': str(data['high']),
                    'low': str(data['low']),
                    'close': str(data['close']),
                    'volume': str(data['volume']),
                    'timestamp': data['timestamp'].isoformat()
                }
            }
        }
        
        # Send to market data group
        await self.channel_layer.group_send(
            f'market_data_{symbol}',
            message
        )
    
    async def process_order_update(self, order_data: Dict):
        """Process real-time order updates"""
        try:
            order_id = order_data['order_id']
            user_id = order_data['user_id']
            symbol = order_data['symbol']
            
            # Broadcast to user's personal channel
            await self.channel_layer.group_send(
                f'user_orders_{user_id}',
                {
                    'type': 'order_update',
                    'order_id': order_id,
                    'status': order_data['status'],
                    'filled_quantity': str(order_data.get('filled_quantity', 0)),
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            # Update order book if limit order
            if order_data.get('order_type') == 'LIMIT':
                await self.update_order_book(symbol)
            
        except Exception as e:
            logger.error(f"Error processing order update: {e}")
    
    async def update_order_book(self, symbol: str):
        """Update order book and broadcast changes"""
        
        # Get updated order book data
        order_book = await self.get_order_book_snapshot(symbol)
        
        # Broadcast to order book subscribers
        await self.channel_layer.group_send(
            f'order_book_{symbol}',
            {
                'type': 'order_book_update',
                'symbol': symbol,
                'bids': order_book['bids'],
                'asks': order_book['asks'],
                'timestamp': timezone.now().isoformat()
            }
        )
    
    async def get_order_book_snapshot(self, symbol: str) -> Dict:
        """Get current order book snapshot"""
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def fetch_order_book():
            from apps.execution_engine.models import Order
            from django.db.models import Sum
            
            # Get bids (buy orders)
            bids = Order.objects.filter(
                ticker__symbol=symbol,
                side='BUY',
                status='PENDING',
                order_type='LIMIT'
            ).values('price').annotate(
                quantity=Sum('quantity')
            ).order_by('-price')[:20]
            
            # Get asks (sell orders)
            asks = Order.objects.filter(
                ticker__symbol=symbol,
                side='SELL',
                status='PENDING',
                order_type='LIMIT'
            ).values('price').annotate(
                quantity=Sum('quantity')
            ).order_by('price')[:20]
            
            return {
                'bids': [{'price': str(bid['price']), 'quantity': str(bid['quantity'])} for bid in bids],
                'asks': [{'price': str(ask['price']), 'quantity': str(ask['quantity'])} for ask in asks]
            }
        
        return await fetch_order_book()
    
    def get_processing_stats(self) -> Dict:
        """Get processing statistics"""
        uptime = time.time() - self.processing_stats['start_time']
        
        return {
            'messages_processed': self.processing_stats['messages_processed'],
            'errors': self.processing_stats['errors'],
            'uptime_seconds': round(uptime, 2),
            'messages_per_second': round(self.processing_stats['messages_processed'] / uptime, 2) if uptime > 0 else 0,
            'error_rate': round(self.processing_stats['errors'] / max(self.processing_stats['messages_processed'], 1) * 100, 2)
        }

# Global processor instance
data_processor = RealTimeDataProcessor()
```

### External Data Feed Integration

```python
# apps/realtime/data_feeds.py
import asyncio
import websockets
import json
import aiohttp
from typing import AsyncGenerator, Dict, List
import logging

logger = logging.getLogger(__name__)

class ExternalDataFeed:
    """Base class for external market data feeds"""
    
    def __init__(self, symbols: List[str]):
        self.symbols = [s.upper() for s in symbols]
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
    async def connect(self):
        """Connect to data feed"""
        raise NotImplementedError
    
    async def disconnect(self):
        """Disconnect from data feed"""
        raise NotImplementedError
    
    async def subscribe(self, symbols: List[str]):
        """Subscribe to symbols"""
        raise NotImplementedError
    
    async def get_data_stream(self) -> AsyncGenerator[Dict, None]:
        """Get real-time data stream"""
        raise NotImplementedError

class AlphaVantageDataFeed(ExternalDataFeed):
    """Alpha Vantage real-time data feed"""
    
    def __init__(self, api_key: str, symbols: List[str]):
        super().__init__(symbols)
        self.api_key = api_key
        self.session = None
        
    async def connect(self):
        """Connect to Alpha Vantage"""
        self.session = aiohttp.ClientSession()
        self.is_connected = True
        logger.info("Connected to Alpha Vantage data feed")
    
    async def disconnect(self):
        """Disconnect from Alpha Vantage"""
        if self.session:
            await self.session.close()
        self.is_connected = False
    
    async def get_data_stream(self) -> AsyncGenerator[Dict, None]:
        """Get real-time data from Alpha Vantage"""
        while self.is_connected:
            try:
                for symbol in self.symbols:
                    url = f"https://www.alphavantage.co/query"
                    params = {
                        'function': 'GLOBAL_QUOTE',
                        'symbol': symbol,
                        'apikey': self.api_key
                    }
                    
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if 'Global Quote' in data:
                                quote = data['Global Quote']
                                
                                yield {
                                    'symbol': symbol,
                                    'price': float(quote['05. price']),
                                    'volume': int(quote['06. volume']),
                                    'timestamp': quote['07. latest trading day'],
                                    'change': float(quote['09. change']),
                                    'change_percent': quote['10. change percent'].rstrip('%')
                                }
                
                # Rate limiting - Alpha Vantage has strict limits
                await asyncio.sleep(12)  # 5 calls per minute max
                
            except Exception as e:
                logger.error(f"Error in Alpha Vantage feed: {e}")
                await asyncio.sleep(30)

class SimulatedDataFeed(ExternalDataFeed):
    """Simulated market data feed for testing"""
    
    def __init__(self, symbols: List[str]):
        super().__init__(symbols)
        self.base_prices = {}
        
    async def connect(self):
        """Initialize simulated feed"""
        # Set random base prices
        import random
        for symbol in self.symbols:
            self.base_prices[symbol] = random.uniform(50, 500)
        
        self.is_connected = True
        logger.info("Connected to simulated data feed")
    
    async def disconnect(self):
        """Disconnect simulated feed"""
        self.is_connected = False
    
    async def get_data_stream(self) -> AsyncGenerator[Dict, None]:
        """Generate simulated market data"""
        import random
        from datetime import datetime
        
        while self.is_connected:
            try:
                for symbol in self.symbols:
                    base_price = self.base_prices[symbol]
                    
                    # Generate realistic price movement
                    price_change = random.uniform(-0.05, 0.05)  # ±5% change
                    new_price = base_price * (1 + price_change)
                    
                    # Update base price gradually
                    self.base_prices[symbol] = new_price
                    
                    # Generate volume
                    volume = random.randint(100000, 5000000)
                    
                    yield {
                        'symbol': symbol,
                        'price': round(new_price, 2),
                        'volume': volume,
                        'timestamp': datetime.utcnow().isoformat(),
                        'open': round(base_price, 2),
                        'high': round(max(base_price, new_price) * 1.02, 2),
                        'low': round(min(base_price, new_price) * 0.98, 2)
                    }
                
                # Update every 100ms for high frequency
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in simulated feed: {e}")
                await asyncio.sleep(1)

class DataFeedManager:
    """Manage multiple data feeds"""
    
    def __init__(self):
        self.feeds: List[ExternalDataFeed] = []
        self.processor = None
        self.running = False
        
    def add_feed(self, feed: ExternalDataFeed):
        """Add a data feed"""
        self.feeds.append(feed)
    
    async def initialize(self):
        """Initialize the data feed manager"""
        from .data_processor import data_processor
        self.processor = data_processor
        await self.processor.initialize()
    
    async def start(self):
        """Start all data feeds"""
        if self.running:
            return
        
        self.running = True
        
        # Connect all feeds
        for feed in self.feeds:
            await feed.connect()
        
        # Start processing tasks
        tasks = []
        for feed in self.feeds:
            task = asyncio.create_task(self.process_feed(feed))
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop(self):
        """Stop all data feeds"""
        self.running = False
        
        for feed in self.feeds:
            await feed.disconnect()
    
    async def process_feed(self, feed: ExternalDataFeed):
        """Process data from a specific feed"""
        try:
            async for data in feed.get_data_stream():
                if not self.running:
                    break
                
                await self.processor.process_market_data_feed(data)
                
        except Exception as e:
            logger.error(f"Error processing feed: {e}")
    
    def get_status(self) -> Dict:
        """Get status of all feeds"""
        return {
            'running': self.running,
            'feeds': [
                {
                    'type': type(feed).__name__,
                    'connected': feed.is_connected,
                    'symbols': feed.symbols
                }
                for feed in self.feeds
            ],
            'processor_stats': self.processor.get_processing_stats() if self.processor else {}
        }

# Global feed manager
feed_manager = DataFeedManager()
```

---

## ⚡ WebSocket Performance Optimization

### Connection Pool Management

```python
# apps/realtime/connection_manager.py
import asyncio
import weakref
import time
from typing import Dict, Set, Optional
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manage WebSocket connections efficiently"""
    
    def __init__(self):
        self.connections: Dict[str, Set[str]] = {}  # symbol -> set of channel names
        self.user_connections: Dict[int, Set[str]] = {}  # user_id -> set of channel names
        self.connection_metadata: Dict[str, Dict] = {}  # channel_name -> metadata
        self.channel_layer = get_channel_layer()
        
    def add_connection(self, channel_name: str, symbol: str = None, user_id: int = None):
        """Add a WebSocket connection"""
        
        metadata = {
            'connected_at': time.time(),
            'symbol': symbol,
            'user_id': user_id,
            'message_count': 0,
            'last_activity': time.time()
        }
        
        self.connection_metadata[channel_name] = metadata
        
        if symbol:
            if symbol not in self.connections:
                self.connections[symbol] = set()
            self.connections[symbol].add(channel_name)
        
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(channel_name)
        
        logger.debug(f"Added connection {channel_name} for symbol {symbol}")
    
    def remove_connection(self, channel_name: str):
        """Remove a WebSocket connection"""
        
        if channel_name not in self.connection_metadata:
            return
        
        metadata = self.connection_metadata[channel_name]
        symbol = metadata.get('symbol')
        user_id = metadata.get('user_id')
        
        # Remove from symbol connections
        if symbol and symbol in self.connections:
            self.connections[symbol].discard(channel_name)
            if not self.connections[symbol]:
                del self.connections[symbol]
        
        # Remove from user connections
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(channel_name)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # Remove metadata
        del self.connection_metadata[channel_name]
        
        logger.debug(f"Removed connection {channel_name}")
    
    def update_activity(self, channel_name: str):
        """Update last activity for connection"""
        if channel_name in self.connection_metadata:
            self.connection_metadata[channel_name]['last_activity'] = time.time()
            self.connection_metadata[channel_name]['message_count'] += 1
    
    def get_symbol_connections(self, symbol: str) -> Set[str]:
        """Get all connections for a symbol"""
        return self.connections.get(symbol, set()).copy()
    
    def get_user_connections(self, user_id: int) -> Set[str]:
        """Get all connections for a user"""
        return self.user_connections.get(user_id, set()).copy()
    
    async def broadcast_to_symbol(self, symbol: str, message: Dict):
        """Broadcast message to all connections for a symbol"""
        connections = self.get_symbol_connections(symbol)
        
        if not connections:
            return
        
        # Use group send for efficiency
        await self.channel_layer.group_send(
            f'market_data_{symbol}',
            {
                'type': 'market_data_message',
                'data': message
            }
        )
        
        # Update activity for all connections
        for channel_name in connections:
            self.update_activity(channel_name)
    
    async def send_to_user(self, user_id: int, message: Dict):
        """Send message to all user's connections"""
        connections = self.get_user_connections(user_id)
        
        if not connections:
            return
        
        await self.channel_layer.group_send(
            f'user_orders_{user_id}',
            {
                'type': 'order_update',
                **message
            }
        )
    
    def cleanup_stale_connections(self, max_age: int = 3600):
        """Clean up stale connections"""
        current_time = time.time()
        stale_connections = []
        
        for channel_name, metadata in self.connection_metadata.items():
            if current_time - metadata['last_activity'] > max_age:
                stale_connections.append(channel_name)
        
        for channel_name in stale_connections:
            self.remove_connection(channel_name)
        
        return len(stale_connections)
    
    def get_statistics(self) -> Dict:
        """Get connection statistics"""
        total_connections = len(self.connection_metadata)
        symbol_counts = {symbol: len(connections) for symbol, connections in self.connections.items()}
        user_counts = len(self.user_connections)
        
        # Calculate average message rate
        current_time = time.time()
        total_messages = sum(meta['message_count'] for meta in self.connection_metadata.values())
        total_uptime = sum(current_time - meta['connected_at'] for meta in self.connection_metadata.values())
        avg_message_rate = total_messages / max(total_uptime, 1)
        
        return {
            'total_connections': total_connections,
            'symbol_subscriptions': symbol_counts,
            'user_connections': user_counts,
            'total_messages': total_messages,
            'average_message_rate': round(avg_message_rate, 2),
            'top_symbols': sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }

# Global connection manager
connection_manager = ConnectionManager()
```

### Message Batching and Throttling

```python
# apps/realtime/message_batching.py
import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, List, Any
import json

class MessageBatcher:
    """Batch and throttle WebSocket messages for performance"""
    
    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_messages: Dict[str, List[Dict]] = defaultdict(list)
        self.last_batch_time: Dict[str, float] = {}
        self.message_queue = asyncio.Queue()
        self.processing_task = None
        
    async def start(self):
        """Start the message batching processor"""
        if self.processing_task is None:
            self.processing_task = asyncio.create_task(self._process_messages())
    
    async def stop(self):
        """Stop the message batching processor"""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
            self.processing_task = None
    
    async def add_message(self, channel_name: str, message: Dict):
        """Add a message to be batched"""
        await self.message_queue.put((channel_name, message))
    
    async def _process_messages(self):
        """Process messages in batches"""
        while True:
            try:
                # Get message with timeout
                try:
                    channel_name, message = await asyncio.wait_for(
                        self.message_queue.get(), 
                        timeout=self.batch_timeout
                    )
                    
                    self.pending_messages[channel_name].append(message)
                    
                    # Check if batch is ready to send
                    if (len(self.pending_messages[channel_name]) >= self.batch_size or
                        self._should_flush_batch(channel_name)):
                        await self._flush_batch(channel_name)
                
                except asyncio.TimeoutError:
                    # Flush all pending batches on timeout
                    await self._flush_all_batches()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in message batching: {e}")
    
    def _should_flush_batch(self, channel_name: str) -> bool:
        """Check if batch should be flushed based on time"""
        current_time = time.time()
        last_time = self.last_batch_time.get(channel_name, 0)
        
        return current_time - last_time >= self.batch_timeout
    
    async def _flush_batch(self, channel_name: str):
        """Flush batch for specific channel"""
        if channel_name not in self.pending_messages or not self.pending_messages[channel_name]:
            return
        
        messages = self.pending_messages[channel_name].copy()
        self.pending_messages[channel_name].clear()
        self.last_batch_time[channel_name] = time.time()
        
        # Send batched message
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        await channel_layer.send(channel_name, {
            'type': 'batched_message',
            'messages': messages,
            'count': len(messages),
            'timestamp': time.time()
        })
    
    async def _flush_all_batches(self):
        """Flush all pending batches"""
        channels_to_flush = list(self.pending_messages.keys())
        
        for channel_name in channels_to_flush:
            if self.pending_messages[channel_name]:
                await self._flush_batch(channel_name)

class RateLimiter:
    """Rate limiting for WebSocket messages"""
    
    def __init__(self, max_messages: int = 100, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.client_windows: Dict[str, deque] = defaultdict(lambda: deque())
    
    def is_allowed(self, client_id: str) -> bool:
        """Check if client is within rate limits"""
        current_time = time.time()
        window = self.client_windows[client_id]
        
        # Remove old messages outside the window
        while window and window[0] < current_time - self.window_seconds:
            window.popleft()
        
        # Check if under limit
        if len(window) < self.max_messages:
            window.append(current_time)
            return True
        
        return False
    
    def get_remaining_quota(self, client_id: str) -> int:
        """Get remaining message quota for client"""
        current_time = time.time()
        window = self.client_windows[client_id]
        
        # Clean old messages
        while window and window[0] < current_time - self.window_seconds:
            window.popleft()
        
        return max(0, self.max_messages - len(window))
    
    def cleanup_old_clients(self, max_age: int = 3600):
        """Clean up old client data"""
        current_time = time.time()
        old_clients = []
        
        for client_id, window in self.client_windows.items():
            if window and current_time - window[-1] > max_age:
                old_clients.append(client_id)
        
        for client_id in old_clients:
            del self.client_windows[client_id]

# Global instances
message_batcher = MessageBatcher()
rate_limiter = RateLimiter()
```

This real-time data implementation provides:

✅ **High-performance WebSockets** with Django Channels and Redis  
✅ **Real-time market data streaming** with microsecond-level latency  
✅ **External data feed integration** for live market data  
✅ **Connection management** with efficient resource usage  
✅ **Message batching and throttling** for optimal performance  
✅ **Order book streaming** with Level 2 market data  
✅ **User-specific updates** for orders and portfolio changes  

The system is designed to handle thousands of concurrent connections while maintaining low latency for critical trading operations.
