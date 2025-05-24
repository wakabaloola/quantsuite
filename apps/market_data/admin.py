"""Admin interface for market data models"""
from django.contrib import admin
from .models import DataSource, Ticker, MarketData

@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')

@admin.register(Ticker)
class TickerAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'data_source', 'currency', 'is_active')
    list_filter = ('data_source', 'currency', 'is_active')
    search_fields = ('symbol', 'name')
    raw_id_fields = ('data_source',)

@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display = ('ticker', 'timestamp', 'close', 'volume')
    list_filter = ('ticker', 'timestamp')
    search_fields = ('ticker__symbol',)
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
