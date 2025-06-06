# apps/market_data/serializers.py
"""Serializers for market data API: these classes convert model instances to/from JSON for API use via Django REST Framework"""
from rest_framework import serializers
from .models import DataSource, Ticker, MarketData

class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = ['id', 'name', 'code', 'url', 'is_active']

class TickerSerializer(serializers.ModelSerializer):
    data_source = DataSourceSerializer(read_only=True)
    
    class Meta:
        model = Ticker
        fields = ['id', 'symbol', 'name', 'data_source', 'currency', 'description', 'is_active']

class MarketDataSerializer(serializers.ModelSerializer):
    ticker = TickerSerializer(read_only=True)
    
    class Meta:
        model = MarketData
        fields = ['id', 'ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'adjusted_close']
