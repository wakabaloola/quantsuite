"""Models for market data storage and processing"""
from django.db import models

class BaseModel(models.Model):
    """Abstract base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

class DataSource(BaseModel):
    """Source of market data (exchange, API, etc.)"""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class Ticker(BaseModel):
    """Financial instrument ticker"""
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['symbol']

    def __str__(self):
        return self.symbol

class MarketData(BaseModel):
    """Time-series market data"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=20, decimal_places=6)
    high = models.DecimalField(max_digits=20, decimal_places=6)
    low = models.DecimalField(max_digits=20, decimal_places=6)
    close = models.DecimalField(max_digits=20, decimal_places=6)
    volume = models.DecimalField(max_digits=20, decimal_places=2)
    adjusted_close = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ticker', 'timestamp']),
        ]
        unique_together = ['ticker', 'timestamp']

    def __str__(self):
        return f"{self.ticker} @ {self.timestamp}"
