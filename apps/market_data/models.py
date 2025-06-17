# apps/market_data/models.py
"""Models for market data storage and processing"""
from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal
import uuid

User = get_user_model()


class BaseModel(models.Model):
    """Abstract base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True)                    # auto-filled when the record is first created
    updated_at = models.DateTimeField(auto_now=True)                        # auto-updated on every save
    is_active = models.BooleanField(default=True)                           # a soft-delete or status toggle

    class Meta:
        abstract = True                                                     # ensure no DB table is created for this model.
        ordering = ['-created_at']                                          # default sort is newest first


class Exchange(BaseModel):
    """Stock exchanges and trading venues"""
    name = models.CharField(max_length=100)                                 # "New York Stock Exchange"
    code = models.CharField(max_length=10, unique=True)                     # "NYSE"
    country = models.CharField(max_length=2)                                # "US" (ISO country code)
    currency = models.CharField(max_length=3)                               # "USD"
    timezone = models.CharField(max_length=50, default='UTC')               # default timezone 'UTC'
    trading_hours = models.JSONField(default=dict)                          # Store market hours
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class DataSource(BaseModel):
    """Source of market data (exchange, API, etc.)"""
    name = models.CharField(max_length=100)                                 # human-readable name (e.g., "Yahoo Finance")
    code = models.CharField(max_length=20, unique=True)                     # unique code (e.g., "YF") for internal use
    url = models.URLField(blank=True)                                       # optional URL for reference or API endpoint
    api_endpoint = models.URLField(blank=True)
    requires_api_key = models.BooleanField(default=False)
    rate_limit_per_minute = models.IntegerField(default=60)
    supported_markets = models.JSONField(default=list)                      # ["US", "UK", "EU"]
    supported_timeframes = models.JSONField(default=list)                   # ["1m", "1h", "1d"]
    is_active = models.BooleanField(default=True)                           # toggles usage of this source

    def __str__(self):
        return f"{self.name} ({self.code})"                                 # shown in Django Admin or print as "Yahoo Finance (YF)"


class Sector(BaseModel):
    """Industry sectors for classification"""
    name = models.CharField(max_length=100, unique=True)                    # "Technology"
    code = models.CharField(max_length=20, unique=True)                     # "TECH"
    
    def __str__(self):
        return self.name


class Industry(BaseModel):
    """Industry classification within sectors"""
    name = models.CharField(max_length=100)                                 # "Software"
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.name} ({self.sector.name})"


class Ticker(BaseModel):
    """Enhanced ticker with global market support"""
    symbol = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Market classification
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE)
    sector = models.ForeignKey(Sector, on_delete=models.SET_NULL, null=True, blank=True)
    industry = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic info
    currency = models.CharField(max_length=3, default='USD')
    country = models.CharField(max_length=2, blank=True)  # ISO country code

    # Data source management
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    yfinance_symbol = models.CharField(max_length=30, blank=True)  # Sometimes different
    alpha_vantage_symbol = models.CharField(max_length=30, blank=True)

    # Fundamental data (from Alpha Vantage or other sources)
    market_cap = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    shares_outstanding = models.DecimalField(max_digits=20, decimal_places=0, null=True, blank=True)

    # Metadata
    last_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['symbol']
        unique_together = ['symbol', 'exchange']
        indexes = [
            models.Index(fields=['symbol']),
            models.Index(fields=['exchange', 'sector']),
            models.Index(fields=['country', 'is_active']),
        ]

    def __str__(self):
        return f"{self.symbol} ({self.exchange.code})"


class MarketData(BaseModel):
    """Enhanced time-series market data"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='market_data')
    timestamp = models.DateTimeField(db_index=True)
    timeframe = models.CharField(max_length=10, default='1d')  # 1m, 5m, 1h, 1d, etc.

    # OHLCV data
    open = models.DecimalField(max_digits=20, decimal_places=6)
    high = models.DecimalField(max_digits=20, decimal_places=6)
    low = models.DecimalField(max_digits=20, decimal_places=6)
    close = models.DecimalField(max_digits=20, decimal_places=6)
    volume = models.DecimalField(max_digits=20, decimal_places=2)
    adjusted_close = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)

    # Additional fields for analysis
    vwap = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    transactions = models.IntegerField(null=True, blank=True)

    # Data quality
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    is_adjusted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ticker', 'timestamp']),
            models.Index(fields=['ticker', 'timeframe', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
        unique_together = ['ticker', 'timestamp', 'timeframe', 'data_source']

    def __str__(self):
        return f"{self.ticker.symbol} @ {self.timestamp} ({self.timeframe})"


class FundamentalData(BaseModel):
    """Fundamental financial data for stocks"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='fundamentals')
    report_date = models.DateField()
    period_type = models.CharField(max_length=20)  # 'annual', 'quarterly'

    # Valuation metrics
    pe_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pb_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ps_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    peg_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Profitability metrics
    roe = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    roa = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    roic = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    profit_margin = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Financial health
    debt_to_equity = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    current_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    quick_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Growth metrics
    revenue_growth = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    earnings_growth = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Raw financial data
    revenue = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    net_income = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    total_assets = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    total_debt = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ['ticker', 'report_date', 'period_type']
        indexes = [
            models.Index(fields=['ticker', 'report_date']),
            models.Index(fields=['period_type', 'report_date']),
        ]


class TechnicalIndicator(BaseModel):
    """Store calculated technical indicators"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='indicators')
    timestamp = models.DateTimeField()
    timeframe = models.CharField(max_length=10, default='1d')
    indicator_name = models.CharField(max_length=50)  # 'RSI', 'MACD', 'SMA_20'

    # Flexible value storage
    value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    values = models.JSONField(null=True, blank=True)  # For multi-value indicators like MACD

    # Calculation parameters
    parameters = models.JSONField(default=dict)  # Store calculation parameters

    class Meta:
        unique_together = ['ticker', 'timestamp', 'timeframe', 'indicator_name']
        indexes = [
            models.Index(fields=['ticker', 'indicator_name', 'timestamp']),
            models.Index(fields=['indicator_name', 'timestamp']),
        ]


class DataIngestionLog(BaseModel):
    """Track data ingestion operations"""
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    symbols_requested = models.JSONField(default=list)
    symbols_successful = models.JSONField(default=list)
    symbols_failed = models.JSONField(default=list)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    records_inserted = models.IntegerField(default=0)

    status = models.CharField(max_length=20, choices=[
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('PARTIAL', 'Partially Completed'),
    ], default='RUNNING')

    error_message = models.TextField(blank=True)
    execution_time_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    class Meta:
        ordering = ['-start_time']


# Portfolio Management Models (for future use)
class Portfolio(BaseModel):
    """User portfolios for analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    base_currency = models.CharField(max_length=3, default='USD')

    # Portfolio settings
    initial_cash = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('100000'))
    current_cash = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('100000'))

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Position(BaseModel):
    """Portfolio positions"""
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='positions')
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)

    quantity = models.DecimalField(max_digits=20, decimal_places=2)
    avg_cost = models.DecimalField(max_digits=20, decimal_places=6)
    current_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)

    # Metadata
    first_purchase_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['portfolio', 'ticker']
