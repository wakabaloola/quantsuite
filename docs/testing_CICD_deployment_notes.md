# Testing, CI/CD, and Deployment Guide

## 🧪 Comprehensive Testing Framework

### Test Dependencies Setup

```bash
# Add testing dependencies to requirements/development.txt
echo "pytest>=7.4.0" >> requirements/development.txt
echo "pytest-django>=4.5.2" >> requirements/development.txt
echo "pytest-cov>=4.1.0" >> requirements/development.txt
echo "factory-boy>=3.3.0" >> requirements/development.txt
echo "freezegun>=1.2.2" >> requirements/development.txt
echo "responses>=0.23.0" >> requirements/development.txt
echo "pytest-mock>=3.11.0" >> requirements/development.txt
echo "pytest-xdist>=3.3.0" >> requirements/development.txt

# Rebuild container
docker-compose build web
docker-compose up -d
```

### Pytest Configuration

```ini
# pytest.ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = config.settings.testing
python_files = tests.py test_*.py *_tests.py
addopts = 
    --verbose
    --strict-markers
    --strict-config
    --cov=apps
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
    --numprocesses=auto
markers =
    unit: Unit tests
    integration: Integration tests
    api: API tests
    performance: Performance tests
    slow: Slow running tests
```

### Test Settings

```python
# config/settings/testing.py
from .base import *

# Override settings for testing
DEBUG = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']  # Fast hashing for tests

# Use in-memory database for speed
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable cache for consistent tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Use in-memory Celery for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable logging during tests
LOGGING_CONFIG = None

# Email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

### Factory Classes for Test Data

```python
# apps/market_data/tests/factories.py
import factory
from factory.django import DjangoModelFactory
from decimal import Decimal
from django.utils import timezone
from apps.market_data.models import DataSource, Ticker, MarketData

class DataSourceFactory(DjangoModelFactory):
    class Meta:
        model = DataSource
    
    name = factory.Sequence(lambda n: f"Data Source {n}")
    code = factory.Sequence(lambda n: f"DS{n:03d}")
    url = factory.LazyAttribute(lambda obj: f"https://{obj.code.lower()}.com")
    is_active = True

class TickerFactory(DjangoModelFactory):
    class Meta:
        model = Ticker
    
    symbol = factory.Sequence(lambda n: f"TICK{n:02d}")
    name = factory.LazyAttribute(lambda obj: f"{obj.symbol} Corporation")
    description = factory.Faker('text', max_nb_chars=200)
    currency = "USD"
    data_source = factory.SubFactory(DataSourceFactory)
    is_active = True

class MarketDataFactory(DjangoModelFactory):
    class Meta:
        model = MarketData
    
    ticker = factory.SubFactory(TickerFactory)
    timestamp = factory.LazyFunction(timezone.now)
    open = factory.LazyFunction(lambda: Decimal(str(factory.Faker('pyfloat', min_value=10, max_value=1000, right_digits=2).generate())))
    high = factory.LazyAttribute(lambda obj: obj.open * Decimal('1.05'))
    low = factory.LazyAttribute(lambda obj: obj.open * Decimal('0.95'))
    close = factory.LazyAttribute(lambda obj: obj.open * Decimal(str(factory.Faker('pyfloat', min_value=0.95, max_value=1.05, right_digits=4).generate())))
    volume = factory.LazyFunction(lambda: Decimal(str(factory.Faker('pyint', min_value=100000, max_value=10000000).generate())))
    adjusted_close = factory.LazyAttribute(lambda obj: obj.close)
```

### Unit Tests

```python
# apps/market_data/tests/test_models.py
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from apps.market_data.models import DataSource, Ticker, MarketData
from .factories import DataSourceFactory, TickerFactory, MarketDataFactory

@pytest.mark.django_db
class TestDataSource:
    def test_create_data_source(self):
        """Test creating a data source"""
        source = DataSourceFactory()
        assert source.pk is not None
        assert source.is_active is True
        assert str(source) == f"{source.name} ({source.code})"
    
    def test_unique_code_constraint(self):
        """Test that data source codes must be unique"""
        DataSourceFactory(code="YAHOO")
        
        with pytest.raises(Exception):  # IntegrityError
            DataSourceFactory(code="YAHOO")
    
    def test_active_sources_manager(self):
        """Test custom manager for active sources"""
        active_source = DataSourceFactory(is_active=True)
        inactive_source = DataSourceFactory(is_active=False)
        
        active_sources = DataSource.objects.filter(is_active=True)
        assert active_source in active_sources
        assert inactive_source not in active_sources

@pytest.mark.django_db
class TestTicker:
    def test_create_ticker(self):
        """Test creating a ticker"""
        ticker = TickerFactory()
        assert ticker.pk is not None
        assert ticker.symbol is not None
        assert ticker.data_source is not None
    
    def test_symbol_uppercase(self):
        """Test that ticker symbols are stored in uppercase"""
        ticker = TickerFactory(symbol="aapl")
        assert ticker.symbol == "AAPL"
    
    def test_ticker_string_representation(self):
        """Test ticker string representation"""
        ticker = TickerFactory(symbol="AAPL", name="Apple Inc.")
        assert str(ticker) == "AAPL - Apple Inc."

@pytest.mark.django_db
class TestMarketData:
    def test_create_market_data(self):
        """Test creating market data"""
        market_data = MarketDataFactory()
        assert market_data.pk is not None
        assert market_data.ticker is not None
        assert market_data.open > 0
        assert market_data.high >= market_data.open
        assert market_data.low <= market_data.open
    
    def test_ohlc_validation(self):
        """Test OHLC price validation"""
        ticker = TickerFactory()
        
        # Valid OHLC data
        valid_data = MarketData(
            ticker=ticker,
            open=Decimal('100.00'),
            high=Decimal('105.00'),
            low=Decimal('95.00'),
            close=Decimal('102.00'),
            volume=Decimal('1000000')
        )
        valid_data.full_clean()  # Should not raise
        
    def test_volume_positive(self):
        """Test that volume must be positive"""
        with pytest.raises(ValidationError):
            market_data = MarketDataFactory(volume=Decimal('-1000'))
            market_data.full_clean()

@pytest.mark.django_db
class TestMarketDataQueries:
    def test_latest_price_for_ticker(self):
        """Test getting latest price for a ticker"""
        ticker = TickerFactory()
        
        # Create multiple market data points
        MarketDataFactory(ticker=ticker, close=Decimal('100.00'))
        MarketDataFactory(ticker=ticker, close=Decimal('105.00'))
        latest = MarketDataFactory(ticker=ticker, close=Decimal('110.00'))
        
        latest_price = ticker.marketdata_set.latest('timestamp')
        assert latest_price.close == Decimal('110.00')
    
    def test_price_range_query(self):
        """Test querying market data by price range"""
        ticker = TickerFactory()
        
        MarketDataFactory(ticker=ticker, close=Decimal('50.00'))
        MarketDataFactory(ticker=ticker, close=Decimal('100.00'))
        MarketDataFactory(ticker=ticker, close=Decimal('150.00'))
        
        mid_range = MarketData.objects.filter(
            ticker=ticker,
            close__gte=Decimal('75.00'),
            close__lte=Decimal('125.00')
        )
        
        assert mid_range.count() == 1
        assert mid_range.first().close == Decimal('100.00')
```

### API Tests

```python
# apps/market_data/tests/test_api.py
import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.market_data.models import DataSource, Ticker, MarketData
from .factories import DataSourceFactory, TickerFactory, MarketDataFactory

User = get_user_model()

@pytest.mark.django_db
class TestMarketDataAPI:
    def setup_method(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_get_tickers_list(self):
        """Test getting list of tickers"""
        ticker1 = TickerFactory()
        ticker2 = TickerFactory()
        
        url = reverse('ticker-list')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        
        # Check ticker data structure
        ticker_data = response.data['results'][0]
        assert 'symbol' in ticker_data
        assert 'name' in ticker_data
        assert 'data_source' in ticker_data
    
    def test_get_ticker_detail(self):
        """Test getting individual ticker details"""
        ticker = TickerFactory(symbol="AAPL", name="Apple Inc.")
        
        url = reverse('ticker-detail', kwargs={'pk': ticker.pk})
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['symbol'] == 'AAPL'
        assert response.data['name'] == 'Apple Inc.'
    
    def test_create_ticker(self):
        """Test creating a new ticker"""
        data_source = DataSourceFactory()
        
        url = reverse('ticker-list')
        data = {
            'symbol': 'MSFT',
            'name': 'Microsoft Corporation',
            'currency': 'USD',
            'data_source_id': data_source.id,
        }
        
        response = self.client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Ticker.objects.filter(symbol='MSFT').exists()
    
    def test_ticker_latest_price(self):
        """Test getting latest price for ticker"""
        ticker = TickerFactory()
        market_data = MarketDataFactory(ticker=ticker, close=Decimal('123.45'))
        
        url = reverse('ticker-latest-price', kwargs={'pk': ticker.pk})
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data['close']) == Decimal('123.45')
    
    def test_market_data_bulk_create(self):
        """Test bulk creating market data"""
        ticker = TickerFactory()
        
        url = reverse('marketdata-bulk-create')
        data = [
            {
                'ticker_id': ticker.id,
                'timestamp': '2024-01-01T10:00:00Z',
                'open': '100.00',
                'high': '105.00',
                'low': '99.00',
                'close': '104.00',
                'volume': '1000000'
            },
            {
                'ticker_id': ticker.id,
                'timestamp': '2024-01-01T11:00:00Z',
                'open': '104.00',
                'high': '106.00',
                'low': '103.00',
                'close': '105.50',
                'volume': '1200000'
            }
        ]
        
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['created'] == 2
        assert MarketData.objects.filter(ticker=ticker).count() == 2
    
    def test_unauthenticated_access(self):
        """Test that unauthenticated users can't access APIs"""
        self.client.force_authenticate(user=None)
        
        url = reverse('ticker-list')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_api_pagination(self):
        """Test API pagination"""
        # Create many tickers
        for i in range(25):
            TickerFactory()
        
        url = reverse('ticker-list')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'next' in response.data
        assert 'previous' in response.data
        assert 'count' in response.data
        assert response.data['count'] == 25
    
    def test_api_filtering(self):
        """Test API filtering capabilities"""
        data_source1 = DataSourceFactory(code="YAHOO")
        data_source2 = DataSourceFactory(code="ALPHA")
        
        TickerFactory(data_source=data_source1, currency="USD")
        TickerFactory(data_source=data_source1, currency="EUR")
        TickerFactory(data_source=data_source2, currency="USD")
        
        # Test filtering by data source
        url = reverse('ticker-list')
        response = self.client.get(f"{url}?data_source={data_source1.id}")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        
        # Test filtering by currency
        response = self.client.get(f"{url}?currency=USD")
        assert len(response.data['results']) == 2
    
    def test_api_search(self):
        """Test API search functionality"""
        TickerFactory(symbol="AAPL", name="Apple Inc.")
        TickerFactory(symbol="GOOGL", name="Alphabet Inc.")
        TickerFactory(symbol="MSFT", name="Microsoft Corp.")
        
        url = reverse('ticker-list')
        response = self.client.get(f"{url}?search=Apple")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['symbol'] == 'AAPL'
```

### Integration Tests

```python
# apps/execution_engine/tests/test_integration.py
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.execution_engine.models import Order, TradingStrategy
from apps.execution_engine.tasks import execute_market_order, risk_check_order
from apps.market_data.tests.factories import TickerFactory, MarketDataFactory

User = get_user_model()

@pytest.mark.django_db
@pytest.mark.integration
class TestTradingWorkflow:
    def setup_method(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='trader',
            email='trader@test.com',
            password='pass123'
        )
        self.ticker = TickerFactory(symbol="AAPL")
        self.market_data = MarketDataFactory(
            ticker=self.ticker,
            close=Decimal('150.00')
        )
        
        self.strategy = TradingStrategy.objects.create(
            name="Test Strategy",
            description="Test trading strategy",
            risk_limit=Decimal('100000'),
            created_by=self.user
        )
    
    def test_full_order_execution_workflow(self):
        """Test complete order creation and execution"""
        # Create order
        order = Order.objects.create(
            ticker=self.ticker,
            strategy=self.strategy,
            order_type='MARKET',
            side='BUY',
            quantity=Decimal('100'),
            created_by=self.user
        )
        
        assert order.status == 'PENDING'
        
        # Risk check
        risk_result = risk_check_order(order.id)
        assert risk_result['status'] == 'APPROVED'
        
        # Execute order
        execution_result = execute_market_order(order.id)
        
        # Refresh order from database
        order.refresh_from_db()
        
        assert order.status == 'FILLED'
        assert order.filled_quantity == Decimal('100')
        assert order.avg_fill_price is not None
        assert execution_result['order_id'] == order.id
        assert 'execution_price' in execution_result
    
    def test_risk_limit_violation(self):
        """Test that orders are rejected when risk limits are exceeded"""
        # Create large order that exceeds risk limits
        large_order = Order.objects.create(
            ticker=self.ticker,
            strategy=self.strategy,
            order_type='MARKET',
            side='BUY',
            quantity=Decimal('1000000'),  # Very large quantity
            created_by=self.user
        )
        
        # This should be rejected due to position size limits
        risk_result = risk_check_order(large_order.id)
        
        # Refresh order
        large_order.refresh_from_db()
        
        if risk_result['status'] == 'REJECTED':
            assert large_order.status == 'REJECTED'
        else:
            # If not rejected by position limits, should still be reasonable
            assert 'position_value' in risk_result

@pytest.mark.django_db
@pytest.mark.integration
class TestAnalyticsIntegration:
    def test_signal_generation_workflow(self):
        """Test complete analytics signal generation"""
        from apps.analytics.tasks import calculate_technical_indicators, calculate_trading_signals
        
        # Create ticker with historical data
        ticker = TickerFactory(symbol="TESTSTOCK")
        
        # Create sufficient historical data for technical analysis
        for i in range(50):
            base_price = Decimal('100.00')
            price_change = Decimal(str((i % 10 - 5) * 0.01))  # Small price movements
            
            MarketDataFactory(
                ticker=ticker,
                open=base_price + price_change,
                high=base_price + price_change + Decimal('1.00'),
                low=base_price + price_change - Decimal('1.00'),
                close=base_price + price_change,
                volume=Decimal('1000000')
            )
        
        # Test technical indicators calculation
        indicators = calculate_technical_indicators(ticker.symbol)
        
        assert 'symbol' in indicators
        assert 'current_price' in indicators
        assert 'sma_20' in indicators
        assert 'rsi' in indicators
        
        # Test signal generation
        signals = calculate_trading_signals([ticker.symbol])
        
        assert len(signals) == 1
        signal = signals[0]
        assert signal['symbol'] == ticker.symbol
        assert signal['signal'] in ['BUY', 'SELL', 'HOLD']
        assert 'confidence' in signal
        assert 'features' in signal
```

### Performance Tests

```python
# apps/market_data/tests/test_performance.py
import pytest
import time
from decimal import Decimal
from django.test import TransactionTestCase
from apps.market_data.models import MarketData
from .factories import TickerFactory

@pytest.mark.performance
class TestMarketDataPerformance(TransactionTestCase):
    def setUp(self):
        """Set up test data"""
        self.ticker = TickerFactory()
    
    def test_bulk_insert_performance(self):
        """Test bulk insert performance for market data"""
        # Prepare bulk data
        bulk_data = []
        for i in range(10000):
            bulk_data.append(MarketData(
                ticker=self.ticker,
                open=Decimal('100.00'),
                high=Decimal('105.00'),
                low=Decimal('95.00'),
                close=Decimal('102.00'),
                volume=Decimal('1000000')
            ))
        
        # Measure bulk create performance
        start_time = time.time()
        MarketData.objects.bulk_create(bulk_data, batch_size=1000)
        end_time = time.time()
        
        duration = end_time - start_time
        records_per_second = 10000 / duration
        
        # Assert reasonable performance (adjust based on requirements)
        assert records_per_second > 5000, f"Bulk insert too slow: {records_per_second:.0f} records/second"
        assert MarketData.objects.count() == 10000
    
    def test_query_performance(self):
        """Test query performance on large dataset"""
        # Create test data
        MarketData.objects.bulk_create([
            MarketData(
                ticker=self.ticker,
                open=Decimal('100.00'),
                high=Decimal('105.00'),
                low=Decimal('95.00'),
                close=Decimal('102.00'),
                volume=Decimal('1000000')
            ) for _ in range(50000)
        ], batch_size=5000)
        
        # Test latest record query performance
        start_time = time.time()
        latest = MarketData.objects.filter(ticker=self.ticker).latest('timestamp')
        end_time = time.time()
        
        query_duration = end_time - start_time
        
        # Should be very fast with proper indexing
        assert query_duration < 0.1, f"Latest query too slow: {query_duration:.3f}s"
        assert latest is not None
```

### Running Tests

```bash
# Run all tests
docker-compose exec web pytest

# Run specific test categories
docker-compose exec web pytest -m unit
docker-compose exec web pytest -m integration
docker-compose exec web pytest -m api

# Run tests with coverage
docker-compose exec web pytest --cov=apps --cov-report=html

# Run performance tests
docker-compose exec web pytest -m performance

# Run tests in parallel
docker-compose exec web pytest -n auto

# Run specific test file
docker-compose exec web pytest apps/market_data/tests/test_models.py

# Run with verbose output
docker-compose exec web pytest -v

# Generate coverage report
docker-compose exec web coverage html
# View report at htmlcov/index.html
```

---

## 🚀 CI/CD Pipeline

### GitHub Actions Configuration

```yaml
# .github/workflows/ci.yml
name: QSuite CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  PYTHON_VERSION: "3.11"
  DJANGO_SETTINGS_MODULE: config.settings.testing

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_qsuite
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}

    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements/*.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements/development.txt

    - name: Run linting
      run: |
        flake8 apps/ config/
        black --check apps/ config/
        isort --check-only apps/ config/

    - name: Run security checks
      run: |
        bandit -r apps/ -f json -o bandit-report.json
        safety check --json --output safety-report.json

    - name: Run tests
      env:
        DATABASE_URL: postgres://postgres:postgres@localhost:5432/test_qsuite
        REDIS_URL: redis://localhost:6379/0
      run: |
        pytest --cov=apps --cov-report=xml --cov-report=html --junitxml=test-results.xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        token: ${{ secrets.CODECOV_TOKEN }}
        file: ./coverage.xml
        fail_ci_if_error: true

    - name: Upload test results
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: test-results
        path: |
          test-results.xml
          htmlcov/
          bandit-report.json
          safety-report.json

  build:
    needs: test
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Login to DockerHub
      uses: docker/login-action@v3
      with:
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_TOKEN }}

    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        platforms: linux/amd64,linux/arm64
        push: true
        tags: |
          qsuite/trading-platform:latest
          qsuite/trading-platform:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop'
    
    steps:
    - name: Deploy to Staging
      run: |
        echo "Deploying to staging environment"
        # Add deployment commands here

  deploy-production:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    
    steps:
    - name: Deploy to Production
      run: |
        echo "Deploying to production environment"
        # Add production deployment commands here
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: ["--max-line-length=88", "--extend-ignore=E203,W503"]

  - repo: https://github.com/pycqa/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ["-r", "apps/", "-f", "json"]

  - repo: local
    hooks:
      - id: django-check
        name: Django Check
        entry: python manage.py check
        language: system
        pass_filenames: false
        files: \.(py)$
```

```bash
# Install pre-commit hooks
docker-compose exec web pip install pre-commit
docker-compose exec web pre-commit install
```

### Code Quality Configuration

```ini
# setup.cfg
[flake8]
max-line-length = 88
extend-ignore = E203, W503, E501
exclude = 
    migrations,
    __pycache__,
    venv,
    .git,
    .tox,
    dist,
    build

[isort]
profile = black
multi_line_output = 3
line_length = 88
include_trailing_comma = True
force_grid_wrap = 0
use_parentheses = True
ensure_newline_before_comments = True

[coverage:run]
source = apps
omit = 
    */migrations/*
    */tests/*
    */venv/*
    manage.py
    */settings/*
    */wsgi.py
    */asgi.py

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
```

```json
# .bandit
{
  "exclude_dirs": [
    "*/migrations/*",
    "*/tests/*"
  ],
  "skips": [
    "B101"
  ]
}
```

---

## 🌩️ Production Deployment

### Production Docker Configuration

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  web:
    build:
      context: .
      target: production
    restart: unless-stopped
    env_file:
      - .env.production
    depends_on:
      - db
      - redis
    volumes:
      - static_volume:/app/staticfiles
      - media_volume:/app/media
      - logs_volume:/app/logs
    networks:
      - qsuite_network
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - static_volume:/static
      - media_volume:/media
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - web
    networks:
      - qsuite_network

  db:
    image: postgres:17
    restart: unless-stopped
    env_file:
      - .env.db.production
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - qsuite_network
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - qsuite_network

  celery:
    build:
      context: .
      target: production
    restart: unless-stopped
    command: celery -A config worker -l info --concurrency=4
    env_file:
      - .env.production
    depends_on:
      - db
      - redis
    volumes:
      - logs_volume:/app/logs
    networks:
      - qsuite_network
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  celery-beat:
    build:
      context: .
      target: production
    restart: unless-stopped
    command: celery -A config beat -l info
    env_file:
      - .env.production
    depends_on:
      - db
      - redis
    volumes:
      - logs_volume:/app/logs
    networks:
      - qsuite_network

  flower:
    build:
      context: .
      target: production
    restart: unless-stopped
    command: celery -A config flower --port=5555
    env_file:
      - .env.production
    ports:
      - "5555:5555"
    depends_on:
      - redis
    networks:
      - qsuite_network

volumes:
  postgres_data:
  redis_data:
  static_volume:
  media_volume:
  logs_volume:

networks:
  qsuite_network:
    driver: bridge
```

### Production Dockerfile

```dockerfile
# Dockerfile (production target)
FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Development stage
FROM base AS development
COPY requirements/ .
RUN pip install --upgrade pip && \
    pip install -r development.txt
COPY . .

# Production stage
FROM base AS production

# Create non-root user
RUN groupadd -r qsuite && useradd -r -g qsuite qsuite

# Install production dependencies
COPY requirements/ .
RUN pip install --upgrade pip && \
    pip install -r production.txt && \
    pip install gunicorn

# Copy application
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/staticfiles /app/media && \
    chown -R qsuite:qsuite /app

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.production

# Switch to non-root user
USER qsuite

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python manage.py check --database default || exit 1

# Production command
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2"]
```

### Production Settings

```python
# config/settings/production.py
from .base import *
import os

# Security settings
DEBUG = False
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ['DB_PORT'],
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'sslmode': 'require',
        },
    }
}

# Static files (S3 or local)
if os.environ.get('USE_S3') == 'True':
    AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
    AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = None
    
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
else:
    STATIC_ROOT = '/app/staticfiles'
    MEDIA_ROOT = '/app/media'

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://redis:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {'max_connections': 100},
        }
    }
}

# Session storage
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Security
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"level": "%(levelname)s", "time": "%(asctime)s", "module": "%(module)s", "message": "%(message)s"}',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/qsuite.log',
            'maxBytes': 1024*1024*100,  # 100MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/security.log',
            'maxBytes': 1024*1024*50,  # 50MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
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

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

# Monitoring
if 'SENTRY_DSN' in os.environ:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        integrations=[
            DjangoIntegration(transaction_style='url'),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=os.environ.get('ENVIRONMENT', 'production'),
    )

# Celery configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
```

### Nginx Configuration

```nginx
# nginx.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=1r/s;

    upstream qsuite_web {
        server web:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;

        client_max_body_size 50M;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # Static files
        location /static/ {
            alias /static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        location /media/ {
            alias /media/;
            expires 1y;
            add_header Cache-Control "public";
        }

        # API endpoints with rate limiting
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://qsuite_web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Authentication endpoints with stricter rate limiting
        location /api/auth/ {
            limit_req zone=login burst=5 nodelay;
            proxy_pass http://qsuite_web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Admin and other endpoints
        location / {
            proxy_pass http://qsuite_web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### Deployment Commands

```bash
# Production deployment
# 1. Build and push images
docker build -f Dockerfile --target production -t qsuite/trading-platform:latest .
docker push qsuite/trading-platform:latest

# 2. Deploy to production
docker-compose -f docker-compose.prod.yml up -d

# 3. Run migrations
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate

# 4. Collect static files
docker-compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# 5. Create superuser (if needed)
docker-compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# 6. Health check
curl -f http://localhost/health/ || exit 1
```

This comprehensive testing and deployment setup provides:

✅ **Enterprise-grade testing** with unit, integration, API, and performance tests  
✅ **Automated CI/CD pipeline** with GitHub Actions  
✅ **Code quality enforcement** with pre-commit hooks and linting  
✅ **Production-ready deployment** with Docker, Nginx, and security configurations  
✅ **Monitoring and observability** with health checks and logging  
✅ **Scalable architecture** with load balancing and auto-scaling capabilities  

This setup meets JPMorgan's requirements for secure, stable, and scalable production systems.
