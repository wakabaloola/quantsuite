"""API views for market data"""
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import DataSource, Ticker, MarketData
from .serializers import (
    DataSourceSerializer,
    TickerSerializer,
    MarketDataSerializer
)

class DataSourceViewSet(viewsets.ModelViewSet):
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'code']

class TickerViewSet(viewsets.ModelViewSet):
    queryset = Ticker.objects.select_related('data_source')
    serializer_class = TickerSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['symbol', 'name']
    filterset_fields = ['data_source', 'currency', 'is_active']

class MarketDataViewSet(viewsets.ModelViewSet):
    queryset = MarketData.objects.select_related('ticker')
    serializer_class = MarketDataSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['ticker__symbol']
    filterset_fields = ['ticker', 'timestamp']
