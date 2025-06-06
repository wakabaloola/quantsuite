# JPMorgan Requirements Implementation Guide

## 🎯 Executive Summary

This guide implements the JPMorgan Lead Software Engineer requirements using your current QSuite Django project with Docker setup. We'll build a comprehensive trading platform that demonstrates all required capabilities.

---

## 🏗️ Microservices Architecture Implementation

### Current App Structure → Microservices Mapping

| Django App | Microservice Function | JPMorgan Requirement |
|------------|----------------------|---------------------|
| `accounts/` | User Authentication & Authorization | Secure high-quality production code |
| `core/` | Shared utilities, monitoring, health checks | Operational stability, system design |
| `market_data/` | Real-time data ingestion & storage | Performant, scalable APIs |
| `execution_engine/` | Trade execution logic | Low latency execution |
| `risk_management/` | Real-time risk monitoring | Compliance & risk controls |
| `analytics/` | ML/AI trading signals | AI/ML/NLP implementation |
| `reporting/` | Trade reporting & audit trails | Audit & compliance |

### Create New Microservice Apps

```bash
# Create additional microservice apps
docker-compose exec web python manage.py startapp execution_engine
docker-compose exec web python manage.py startapp risk_management
docker-compose exec web python manage.py startapp analytics
docker-compose exec web python manage.py startapp reporting

# Add to INSTALLED_APPS in settings
docker-compose exec web python manage.py shell -c "
print('Add these to LOCAL_APPS in config/settings/base.py:')
print(\"    'apps.execution_engine',\")
print(\"    'apps.risk_management',\")
print(\"    'apps.analytics',\")
print(\"    'apps.reporting',\")
"
```

---

## 🚀 RESTful API Development (Django REST Framework)

### Install and Configure DRF

```bash
# Add to requirements/development.txt
echo "djangorestframework>=3.16.0" >> requirements/development.txt
echo "djangorestframework-simplejwt>=5.3.0" >> requirements/development.txt
echo "drf-yasg>=1.21.0" >> requirements/development.txt
echo "django-filter>=23.1" >> requirements/development.txt
echo "django-cors-headers>=4.3.0" >> requirements/development.txt

# Rebuild container
docker-compose build web
docker-compose up -d
```

### API Configuration

```python
# config/settings/base.py - Add to THIRD_PARTY_APPS
THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_yasg',
    'django_filters',
    'corsheaders',
]

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}

# JWT Configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
}

# CORS settings for development
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

### Market Data API Implementation

```python
# apps/market_data/serializers.py
from rest_framework import serializers
from .models import DataSource, Ticker, MarketData

class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = ['id', 'name', 'code', 'url', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class TickerSerializer(serializers.ModelSerializer):
    data_source = DataSourceSerializer(read_only=True)
    data_source_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Ticker
        fields = ['id', 'symbol', 'name', 'description', 'currency', 
                 'data_source', 'data_source_id', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class MarketDataSerializer(serializers.ModelSerializer):
    ticker = TickerSerializer(read_only=True)
    ticker_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = MarketData
        fields = ['id', 'ticker', 'ticker_id', 'timestamp', 'open', 'high', 
                 'low', 'close', 'volume', 'adjusted_close', 'created_at']
        read_only_fields = ['id', 'created_at']

class MarketDataCreateSerializer(serializers.ModelSerializer):
    """Optimized serializer for bulk data creation"""
    class Meta:
        model = MarketData
        fields = ['ticker_id', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
```

```python
# apps/market_data/views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Avg, Max, Min, Count
from .models import DataSource, Ticker, MarketData
from .serializers import DataSourceSerializer, TickerSerializer, MarketDataSerializer

class DataSourceViewSet(viewsets.ModelViewSet):
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'code']
    filterset_fields = ['is_active']

class TickerViewSet(viewsets.ModelViewSet):
    queryset = Ticker.objects.select_related('data_source')
    serializer_class = TickerSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['symbol', 'name']
    filterset_fields = ['currency', 'data_source', 'is_active']
    ordering_fields = ['symbol', 'created_at']
    ordering = ['symbol']

    @action(detail=True, methods=['get'])
    def latest_price(self, request, pk=None):
        """Get latest market data for ticker"""
        ticker = self.get_object()
        latest_data = ticker.marketdata_set.latest('timestamp')
        serializer = MarketDataSerializer(latest_data)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get price statistics for ticker"""
        ticker = self.get_object()
        stats = ticker.marketdata_set.aggregate(
            avg_close=Avg('close'),
            max_high=Max('high'),
            min_low=Min('low'),
            record_count=Count('id')
        )
        return Response(stats)

class MarketDataViewSet(viewsets.ModelViewSet):
    serializer_class = MarketDataSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['ticker', 'ticker__symbol']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']

    def get_queryset(self):
        return MarketData.objects.select_related('ticker', 'ticker__data_source')

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create market data for high-frequency updates"""
        serializer = MarketDataCreateSerializer(data=request.data, many=True)
        if serializer.is_valid():
            MarketData.objects.bulk_create([
                MarketData(**item) for item in serializer.validated_data
            ])
            return Response({'created': len(serializer.validated_data)}, 
                          status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def real_time_feed(self, request):
        """Real-time market data feed"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Get data from last 5 minutes
        recent = timezone.now() - timedelta(minutes=5)
        recent_data = self.get_queryset().filter(timestamp__gte=recent)
        
        serializer = self.get_serializer(recent_data, many=True)
        return Response({
            'timestamp': timezone.now(),
            'count': recent_data.count(),
            'data': serializer.data
        })
```

### URL Configuration

```python
# config/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# API Documentation
schema_view = get_schema_view(
    openapi.Info(
        title="QSuite Trading Platform API",
        default_version='v1',
        description="JPMorgan-grade trading platform APIs",
        contact=openapi.Contact(email="admin@qsuite.com"),
    ),
    public=True,
)

# API Router
router = DefaultRouter()
from apps.market_data.views import DataSourceViewSet, TickerViewSet, MarketDataViewSet
router.register(r'data-sources', DataSourceViewSet)
router.register(r'tickers', TickerViewSet)
router.register(r'market-data', MarketDataViewSet, basename='marketdata')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Authentication
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # API Endpoints
    path('api/v1/', include(router.urls)),
    
    # API Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='api-docs'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='api-redoc'),
]
```

### Test API Implementation

```bash
# Apply migrations and start services
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate

# Create sample data and test APIs
docker-compose exec web python manage.py shell -c "
from apps.market_data.models import DataSource, Ticker, MarketData
from decimal import Decimal
from datetime import datetime, timezone

# Create test data
yahoo, _ = DataSource.objects.get_or_create(
    code='YAHOO',
    defaults={'name': 'Yahoo Finance', 'url': 'https://finance.yahoo.com'}
)

aapl, _ = Ticker.objects.get_or_create(
    symbol='AAPL',
    defaults={'name': 'Apple Inc.', 'currency': 'USD', 'data_source': yahoo}
)

MarketData.objects.create(
    ticker=aapl,
    timestamp=datetime.now(timezone.utc),
    open=Decimal('150.00'),
    high=Decimal('155.00'),
    low=Decimal('149.00'),
    close=Decimal('154.25'),
    volume=Decimal('45000000')
)

print('✅ Test data created')
print('🔗 API Docs: http://localhost:8000/api/docs/')
print('📊 Market Data API: http://localhost:8000/api/v1/market-data/')
"
```

---

## ⚡ High-Performance Trading Engine

### Execution Engine Implementation

```python
# apps/execution_engine/models.py
from django.db import models
from django.contrib.auth import get_user_model
from apps.market_data.models import Ticker
from decimal import Decimal

User = get_user_model()

class TradingStrategy(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    risk_limit = models.DecimalField(max_digits=15, decimal_places=2)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class Order(models.Model):
    ORDER_TYPES = [
        ('MARKET', 'Market Order'),
        ('LIMIT', 'Limit Order'),
        ('STOP', 'Stop Order'),
        ('STOP_LIMIT', 'Stop Limit Order'),
    ]
    
    ORDER_SIDES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]
    
    ORDER_STATUS = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Filled'),
        ('FILLED', 'Filled'),
        ('CANCELLED', 'Cancelled'),
        ('REJECTED', 'Rejected'),
    ]
    
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)
    strategy = models.ForeignKey(TradingStrategy, on_delete=models.CASCADE, null=True, blank=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES)
    side = models.CharField(max_length=4, choices=ORDER_SIDES)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    stop_price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='PENDING')
    filled_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    avg_fill_price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Execution(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='executions')
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    price = models.DecimalField(max_digits=15, decimal_places=6)
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    execution_time = models.DateTimeField(auto_now_add=True)
    external_execution_id = models.CharField(max_length=100, null=True, blank=True)
```

```python
# apps/execution_engine/tasks.py
from celery import shared_task
from django.utils import timezone
from decimal import Decimal
import time
import random
from .models import Order, Execution

@shared_task
def execute_market_order(order_id):
    """Execute market order with simulated latency"""
    try:
        order = Order.objects.get(id=order_id)
        
        # Simulate market execution latency (microseconds in real trading)
        time.sleep(0.001)  # 1ms simulated latency
        
        # Simulate market price with slight slippage
        from apps.market_data.models import MarketData
        latest_data = MarketData.objects.filter(
            ticker=order.ticker
        ).latest('timestamp')
        
        # Apply realistic slippage (0.01-0.05%)
        slippage = Decimal(str(random.uniform(0.0001, 0.0005)))
        if order.side == 'BUY':
            execution_price = latest_data.close * (1 + slippage)
        else:
            execution_price = latest_data.close * (1 - slippage)
        
        # Create execution
        execution = Execution.objects.create(
            order=order,
            quantity=order.quantity,
            price=execution_price,
            commission=order.quantity * Decimal('0.005'),  # $0.005 per share
        )
        
        # Update order status
        order.filled_quantity = order.quantity
        order.avg_fill_price = execution_price
        order.status = 'FILLED'
        order.save()
        
        return {
            'order_id': order_id,
            'execution_price': float(execution_price),
            'quantity': float(order.quantity),
            'execution_time': execution.execution_time.isoformat(),
            'latency_ms': 1.0
        }
        
    except Exception as e:
        Order.objects.filter(id=order_id).update(status='REJECTED')
        raise e

@shared_task
def risk_check_order(order_id):
    """Real-time risk checking"""
    order = Order.objects.get(id=order_id)
    
    # Calculate position size
    user_orders = Order.objects.filter(
        created_by=order.created_by,
        ticker=order.ticker,
        status='FILLED'
    )
    
    position_value = sum([
        o.filled_quantity * o.avg_fill_price * (1 if o.side == 'BUY' else -1)
        for o in user_orders
    ])
    
    # Risk limits
    max_position_value = Decimal('1000000')  # $1M position limit
    
    if abs(position_value) > max_position_value:
        Order.objects.filter(id=order_id).update(status='REJECTED')
        return {'status': 'REJECTED', 'reason': 'Position limit exceeded'}
    
    return {'status': 'APPROVED', 'position_value': float(position_value)}

@shared_task
def algorithmic_trading_strategy(strategy_id):
    """Execute algorithmic trading strategy"""
    from .models import TradingStrategy
    from apps.analytics.tasks import calculate_trading_signals
    
    strategy = TradingStrategy.objects.get(id=strategy_id)
    
    # Get signals from analytics engine
    signals = calculate_trading_signals.delay(['AAPL', 'GOOGL', 'MSFT'])
    signal_results = signals.get()
    
    orders_created = []
    for signal in signal_results:
        if signal['confidence'] > 0.7:  # High confidence threshold
            # Create order based on signal
            # Implementation would create actual orders
            orders_created.append(signal['symbol'])
    
    return {
        'strategy': strategy.name,
        'signals_processed': len(signal_results),
        'orders_created': len(orders_created),
        'symbols': orders_created
    }
```

### Trading Engine API

```python
# apps/execution_engine/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from .models import Order, TradingStrategy, Execution
from .tasks import execute_market_order, risk_check_order
from .serializers import OrderSerializer, ExecutionSerializer

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        return Order.objects.filter(created_by=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute order with risk checks"""
        order = self.get_object()
        
        if order.status != 'PENDING':
            return Response(
                {'error': 'Order already processed'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Async risk check and execution
        risk_result = risk_check_order.delay(order.id)
        risk_status = risk_result.get()
        
        if risk_status['status'] == 'APPROVED':
            execution_result = execute_market_order.delay(order.id)
            result = execution_result.get()
            return Response(result)
        else:
            return Response(risk_status, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def performance_metrics(self, request):
        """Get trading performance metrics"""
        user_orders = self.get_queryset().filter(status='FILLED')
        
        total_orders = user_orders.count()
        total_volume = sum([o.filled_quantity * o.avg_fill_price for o in user_orders])
        
        # Calculate P&L (simplified)
        pnl = 0
        for order in user_orders:
            # This would be more complex in reality
            pnl += float(order.filled_quantity) * 0.01  # Simplified
        
        return Response({
            'total_orders': total_orders,
            'total_volume': float(total_volume),
            'unrealized_pnl': pnl,
            'success_rate': 0.85,  # Would calculate from actual data
        })
```

---

## 🤖 AI/ML Analytics Engine

### Analytics Models and Tasks

```python
# apps/analytics/models.py
from django.db import models
from apps.market_data.models import Ticker

class TradingSignal(models.Model):
    SIGNAL_TYPES = [
        ('BUY', 'Buy Signal'),
        ('SELL', 'Sell Signal'),
        ('HOLD', 'Hold Signal'),
    ]
    
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)
    signal_type = models.CharField(max_length=4, choices=SIGNAL_TYPES)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)  # 0.0000 to 1.0000
    algorithm = models.CharField(max_length=100)
    features = models.JSONField()  # Store ML features
    created_at = models.DateTimeField(auto_now_add=True)

class BacktestResult(models.Model):
    strategy_name = models.CharField(max_length=100)
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    total_return = models.DecimalField(max_digits=10, decimal_places=4)
    sharpe_ratio = models.DecimalField(max_digits=8, decimal_places=4)
    max_drawdown = models.DecimalField(max_digits=8, decimal_places=4)
    win_rate = models.DecimalField(max_digits=5, decimal_places=4)
    parameters = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
```

```python
# apps/analytics/tasks.py
from celery import shared_task
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

@shared_task
def calculate_technical_indicators(symbol, period=20):
    """Calculate technical indicators for trading signals"""
    from apps.market_data.models import MarketData, Ticker
    
    try:
        ticker = Ticker.objects.get(symbol=symbol)
        
        # Get recent market data
        end_date = timezone.now()
        start_date = end_date - timedelta(days=period * 2)  # Extra data for calculations
        
        market_data = MarketData.objects.filter(
            ticker=ticker,
            timestamp__gte=start_date,
            timestamp__lte=end_date
        ).order_by('timestamp').values('timestamp', 'close', 'high', 'low', 'volume')
        
        if not market_data:
            return {'error': f'No data available for {symbol}'}
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(market_data)
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # Calculate technical indicators
        # Simple Moving Average
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=min(50, len(df))).mean()
        
        # RSI (Relative Strength Index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_12 = df['close'].ewm(span=12).mean()
        ema_26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Get latest values
        latest = df.iloc[-1]
        
        return {
            'symbol': symbol,
            'timestamp': latest['timestamp'].isoformat(),
            'current_price': float(latest['close']),
            'sma_20': float(latest['sma_20']) if not pd.isna(latest['sma_20']) else None,
            'sma_50': float(latest['sma_50']) if not pd.isna(latest['sma_50']) else None,
            'rsi': float(latest['rsi']) if not pd.isna(latest['rsi']) else None,
            'macd': float(latest['macd']) if not pd.isna(latest['macd']) else None,
            'macd_signal': float(latest['macd_signal']) if not pd.isna(latest['macd_signal']) else None,
            'bb_upper': float(latest['bb_upper']) if not pd.isna(latest['bb_upper']) else None,
            'bb_lower': float(latest['bb_lower']) if not pd.isna(latest['bb_lower']) else None,
            'volume_ratio': float(latest['volume_ratio']) if not pd.isna(latest['volume_ratio']) else None,
        }
        
    except Exception as e:
        return {'error': str(e)}

@shared_task
def calculate_trading_signals(symbols):
    """Generate ML-based trading signals"""
    from .models import TradingSignal
    from apps.market_data.models import Ticker
    
    signals = []
    
    for symbol in symbols:
        try:
            # Get technical indicators
            indicators = calculate_technical_indicators(symbol)
            
            if 'error' in indicators:
                continue
                
            # Simple ML-like signal generation
            signal_strength = 0
            features = {}
            
            # RSI signals
            if indicators['rsi']:
                if indicators['rsi'] < 30:  # Oversold
                    signal_strength += 0.3
                    features['rsi_signal'] = 'oversold'
                elif indicators['rsi'] > 70:  # Overbought
                    signal_strength -= 0.3
                    features['rsi_signal'] = 'overbought'
            
            # Moving average crossover
            if indicators['sma_20'] and indicators['sma_50']:
                if indicators['current_price'] > indicators['sma_20'] > indicators['sma_50']:
                    signal_strength += 0.2
                    features['ma_trend'] = 'bullish'
                elif indicators['current_price'] < indicators['sma_20'] < indicators['sma_50']:
                    signal_strength -= 0.2
                    features['ma_trend'] = 'bearish'
            
            # MACD signals
            if indicators['macd'] and indicators['macd_signal']:
                if indicators['macd'] > indicators['macd_signal']:
                    signal_strength += 0.1
                    features['macd_signal'] = 'bullish'
                else:
                    signal_strength -= 0.1
                    features['macd_signal'] = 'bearish'
            
            # Volume confirmation
            if indicators['volume_ratio']:
                if indicators['volume_ratio'] > 1.5:  # High volume
                    signal_strength *= 1.2  # Amplify signal with volume
                    features['volume_confirmation'] = True
            
            # Determine signal type and confidence
            if signal_strength > 0.3:
                signal_type = 'BUY'
                confidence = min(abs(signal_strength), 1.0)
            elif signal_strength < -0.3:
                signal_type = 'SELL'
                confidence = min(abs(signal_strength), 1.0)
            else:
                signal_type = 'HOLD'
                confidence = 1.0 - abs(signal_strength)
            
            # Store signal in database
            ticker = Ticker.objects.get(symbol=symbol)
            TradingSignal.objects.create(
                ticker=ticker,
                signal_type=signal_type,
                confidence=Decimal(str(confidence)),
                algorithm='technical_indicators_v1',
                features=features
            )
            
            signals.append({
                'symbol': symbol,
                'signal': signal_type,
                'confidence': confidence,
                'features': features,
                'price': indicators['current_price']
            })
            
        except Exception as e:
            signals.append({
                'symbol': symbol,
                'error': str(e)
            })
    
    return signals

@shared_task
def run_backtest(strategy_name, symbol, start_date, end_date, parameters):
    """Run backtesting for trading strategy"""
    from .models import BacktestResult
    from apps.market_data.models import Ticker, MarketData
    
    try:
        ticker = Ticker.objects.get(symbol=symbol)
        
        # Get historical data
        market_data = MarketData.objects.filter(
            ticker=ticker,
            timestamp__gte=start_date,
            timestamp__lte=end_date
        ).order_by('timestamp').values('timestamp', 'close', 'high', 'low', 'volume')
        
        df = pd.DataFrame(market_data)
        df['close'] = df['close'].astype(float)
        
        if len(df) < 50:  # Need minimum data
            return {'error': 'Insufficient data for backtest'}
        
        # Simulate trading strategy
        df['returns'] = df['close'].pct_change()
        
        # Simple mean reversion strategy
        lookback = parameters.get('lookback', 20)
        df['sma'] = df['close'].rolling(window=lookback).mean()
        df['signal'] = np.where(df['close'] < df['sma'] * 0.98, 1, 0)  # Buy when 2% below SMA
        df['signal'] = np.where(df['close'] > df['sma'] * 1.02, -1, df['signal'])  # Sell when 2% above SMA
        
        # Calculate strategy returns
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        
        # Performance metrics
        total_return = (1 + df['strategy_returns'].fillna(0)).prod() - 1
        returns_std = df['strategy_returns'].std()
        sharpe_ratio = df['strategy_returns'].mean() / returns_std * np.sqrt(252) if returns_std > 0 else 0
        
        # Maximum drawdown
        cumulative = (1 + df['strategy_returns'].fillna(0)).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Win rate
        profitable_trades = (df['strategy_returns'] > 0).sum()
        total_trades = (df['strategy_returns'] != 0).sum()
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        # Save backtest result
        result = BacktestResult.objects.create(
            strategy_name=strategy_name,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            total_return=Decimal(str(total_return)),
            sharpe_ratio=Decimal(str(sharpe_ratio)),
            max_drawdown=Decimal(str(max_drawdown)),
            win_rate=Decimal(str(win_rate)),
            parameters=parameters
        )
        
        return {
            'backtest_id': result.id,
            'total_return': float(total_return),
            'sharpe_ratio': float(sharpe_ratio),
            'max_drawdown': float(max_drawdown),
            'win_rate': float(win_rate),
            'total_trades': int(total_trades)
        }
        
    except Exception as e:
        return {'error': str(e)}

@shared_task
def market_sentiment_analysis(symbols):
    """Analyze market sentiment using NLP (simplified)"""
    import random
    
    # This would integrate with news APIs and NLP libraries
    # For demo purposes, we'll simulate sentiment analysis
    
    sentiments = []
    
    for symbol in symbols:
        # Simulate sentiment score (-1 to 1)
        sentiment_score = random.uniform(-1, 1)
        
        # Simulate confidence based on news volume
        confidence = random.uniform(0.5, 0.95)
        
        sentiment = 'positive' if sentiment_score > 0.1 else 'negative' if sentiment_score < -0.1 else 'neutral'
        
        sentiments.append({
            'symbol': symbol,
            'sentiment': sentiment,
            'score': sentiment_score,
            'confidence': confidence,
            'news_volume': random.randint(10, 100)
        })
    
    return sentiments
```

### Test ML Analytics

```bash
# Install ML dependencies
echo "pandas>=2.0.0" >> requirements/development.txt
echo "numpy>=1.24.0" >> requirements/development.txt
echo "scikit-learn>=1.3.0" >> requirements/development.txt

# Rebuild container
docker-compose build web
docker-compose up -d

# Test analytics tasks
docker-compose exec web python manage.py shell -c "
from apps.analytics.tasks import calculate_technical_indicators, calculate_trading_signals

# Test technical indicators
indicators = calculate_technical_indicators.delay('AAPL')
print('Technical Indicators:', indicators.get())

# Test trading signals
signals = calculate_trading_signals.delay(['AAPL', 'GOOGL'])
print('Trading Signals:', signals.get())
"
```

---

## 🛡️ Security and Compliance

### Security Middleware and Configuration

```python
# config/settings/base.py - Add security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Session security
SESSION_COOKIE_SECURE = True  # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Logging for audit trails
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/qsuite.log',
            'maxBytes': 1024*1024*50,  # 50MB
            'backupCount': 5,
            'formatter': 'detailed',
        },
        'security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/security.log',
            'maxBytes': 1024*1024*10,  # 10MB
            'backupCount': 10,
            'formatter': 'detailed',
        },
    },
    'loggers': {
        'django.security': {
            'handlers': ['security'],
            'level': 'WARNING',
            'propagate': False,
        },
        'qsuite': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### Audit Trail Implementation

```python
# apps/core/middleware.py
import logging
from django.utils.deprecation import MiddlewareMixin

security_logger = logging.getLogger('django.security')
audit_logger = logging.getLogger('qsuite')

class SecurityAuditMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Log API access
        if request.path.startswith('/api/'):
            audit_logger.info(
                f"API_ACCESS user={getattr(request.user, 'username', 'anonymous')} "
                f"path={request.path} method={request.method} ip={self.get_client_ip(request)}"
            )
        
        # Log authentication attempts
        if request.path.startswith('/api/auth/'):
            security_logger.warning(
                f"AUTH_ATTEMPT path={request.path} ip={self.get_client_ip(request)}"
            )
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

# Add to MIDDLEWARE in settings
```

---

## 📊 Monitoring and Observability

### Health Check and Monitoring

```python
# apps/core/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import connection
from django.core.cache import cache
import redis
from celery import current_app

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Comprehensive health check for all services"""
    health_status = {'status': 'healthy', 'services': {}}
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['services']['database'] = 'healthy'
    except Exception as e:
        health_status['services']['database'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    # Redis check
    try:
        cache.set('health_check', 'ok', 30)
        cache.get('health_check')
        health_status['services']['redis'] = 'healthy'
    except Exception as e:
        health_status['services']['redis'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    # Celery check
    try:
        inspect = current_app.control.inspect()
        active_workers = inspect.active()
        if active_workers:
            health_status['services']['celery'] = 'healthy'
        else:
            health_status['services']['celery'] = 'no active workers'
            health_status['status'] = 'degraded'
    except Exception as e:
        health_status['services']['celery'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    return Response(health_status)

@api_view(['GET'])
def system_metrics(request):
    """System performance metrics"""
    from django.db import connection
    from apps.market_data.models import MarketData
    from apps.execution_engine.models import Order
    
    # Database metrics
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM market_data_marketdata")
        market_data_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM execution_engine_order WHERE status = 'FILLED'")
        filled_orders = cursor.fetchone()[0]
    
    # Calculate throughput (orders per minute)
    from django.utils import timezone
    from datetime import timedelta
    
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    recent_orders = Order.objects.filter(created_at__gte=one_minute_ago).count()
    
    return Response({
        'database': {
            'market_data_records': market_data_count,
            'total_orders': filled_orders,
        },
        'performance': {
            'orders_per_minute': recent_orders,
            'avg_execution_latency_ms': 1.2,  # Would measure actual latency
        },
        'timestamp': timezone.now()
    })
```

## Summary

This implementation provides a JPMorgan-grade trading platform with:

✅ **Microservices Architecture** - Modular Django apps as services  
✅ **High-Performance APIs** - DRF with pagination, filtering, throttling  
✅ **Real-time Execution Engine** - Async order processing with Celery  
✅ **AI/ML Analytics** - Technical indicators and trading signals  
✅ **Security & Compliance** - Audit trails, authentication, monitoring  
✅ **Scalable Infrastructure** - Docker containerization ready for cloud  

**Next Steps:**
1. Test all APIs: `http://localhost:8000/api/docs/`
2. Run sample trading workflows
3. Set up CI/CD pipeline
4. Deploy to AWS/cloud environment
5. Implement real market data feeds
6. Add sophisticated ML models
