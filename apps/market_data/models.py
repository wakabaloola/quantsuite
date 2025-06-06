# apps/market_data/models.py
"""Models for market data storage and processing"""
from django.db import models


class BaseModel(models.Model):
    """Abstract base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True)                    # auto-filled when the record is first created
    updated_at = models.DateTimeField(auto_now=True)                        # auto-updated on every save
    is_active = models.BooleanField(default=True)                           # a soft-delete or status toggle

    class Meta:
        abstract = True                                                     # ensure no DB table is created for this model.
        ordering = ['-created_at']                                          # default sort is newest first


class DataSource(BaseModel):
    """Source of market data (exchange, API, etc.)"""
    name = models.CharField(max_length=100)                                 # human-readable name (e.g., "Yahoo Finance")
    code = models.CharField(max_length=20, unique=True)                     # unique code (e.g., "YF") for internal use
    url = models.URLField(blank=True)                                       # optional URL for reference or API endpoint
    is_active = models.BooleanField(default=True)                           # toggles usage of this source

    def __str__(self):
        return f"{self.name} ({self.code})"                                 # shown in Django Admin or print as "Yahoo Finance (YF)"


class Ticker(BaseModel):
    """Financial instrument ticker"""
    symbol = models.CharField(max_length=20, unique=True)                   # unique ticker code (e.g., "AAPL")
    name = models.CharField(max_length=100)                                 # full name (e.g., "Apple Inc.")
    description = models.TextField(blank=True)                              # optional text description
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE)   # foreign key link to a DataSource
    currency = models.CharField(max_length=3, default='USD')                # default to 'USD'; ISO currency code (e.g., 'GBP')
    is_active = models.BooleanField(default=True)                           # toggle for whether this ticker is still tracked

    class Meta:
        ordering = ['symbol']                                               # default sort is alphabetically by symbol

    def __str__(self):
        return self.symbol                                                  # returns symbol (e.g., "AAPL")


class MarketData(BaseModel):
    """Time-series market data"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)            # foreign key to a `Ticker`
    timestamp = models.DateTimeField()                                      # datetime of this data point
    open = models.DecimalField(max_digits=20, decimal_places=6)             # decimal fields with high precision
    high = models.DecimalField(max_digits=20, decimal_places=6)             #               "
    low = models.DecimalField(max_digits=20, decimal_places=6)              #               "
    close = models.DecimalField(max_digits=20, decimal_places=6)            #               "
    volume = models.DecimalField(max_digits=20, decimal_places=2)           # trade volume with 2 decimal precision
    adjusted_close = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True)             # optional adjusted close (e.g., after splits)

    class Meta:
        ordering = ['-timestamp']                                           # default ordering is newest first
        indexes = [
            models.Index(fields=['ticker', 'timestamp']),                   # DB index for faster query on (ticker, timestamp)
        ]
        unique_together = ['ticker', 'timestamp']                           # ensures no duplicate entry for a ticker at a given timestamp

    def __str__(self):
        return f"{self.ticker} @ {self.timestamp}"                          # renders as "AAPL @ 2025-06-05 16:47:54"
