# apps/market_data/admin.py
"""Django admin configuration for market data models"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    DataSource, Exchange, Sector, Industry, Ticker, MarketData,
    FundamentalData, TechnicalIndicator, DataIngestionLog,
    Portfolio, Position
)


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'requires_api_key', 'rate_limit_per_minute', 'is_active', 'created_at']
    list_filter = ['requires_api_key', 'is_active', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'url', 'api_endpoint')
        }),
        ('Configuration', {
            'fields': ('requires_api_key', 'rate_limit_per_minute', 'supported_markets', 'supported_timeframes')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'country', 'currency', 'timezone', 'is_active']
    list_filter = ['country', 'currency', 'is_active']
    search_fields = ['name', 'code', 'country']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'ticker_count', 'is_active']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']
    
    def ticker_count(self, obj):
        return obj.ticker_set.count()
    ticker_count.short_description = 'Tickers'


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ['name', 'sector', 'ticker_count', 'is_active']
    list_filter = ['sector', 'is_active']
    search_fields = ['name', 'sector__name']
    readonly_fields = ['created_at', 'updated_at']
    
    def ticker_count(self, obj):
        return obj.ticker_set.count()
    ticker_count.short_description = 'Tickers'


@admin.register(Ticker)
class TickerAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'exchange', 'sector', 'currency', 'market_cap_formatted', 'data_count', 'last_updated', 'is_active']
    list_filter = ['exchange', 'sector', 'currency', 'country', 'is_active', 'data_source']
    search_fields = ['symbol', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'last_updated']
    raw_id_fields = ['data_source', 'exchange', 'sector', 'industry']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('symbol', 'name', 'description')
        }),
        ('Classification', {
            'fields': ('exchange', 'sector', 'industry', 'currency', 'country')
        }),
        ('Financial Data', {
            'fields': ('market_cap', 'shares_outstanding')
        }),
        ('Data Sources', {
            'fields': ('data_source', 'yfinance_symbol', 'alpha_vantage_symbol')
        }),
        ('Status', {
            'fields': ('is_active', 'last_updated')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def market_cap_formatted(self, obj):
        if obj.market_cap:
            if obj.market_cap >= 1_000_000_000_000:  # Trillion
                return f"${obj.market_cap / 1_000_000_000_000:.2f}T"
            elif obj.market_cap >= 1_000_000_000:  # Billion
                return f"${obj.market_cap / 1_000_000_000:.2f}B"
            elif obj.market_cap >= 1_000_000:  # Million
                return f"${obj.market_cap / 1_000_000:.2f}M"
            else:
                return f"${obj.market_cap:,.0f}"
        return "-"
    market_cap_formatted.short_description = 'Market Cap'
    market_cap_formatted.admin_order_field = 'market_cap'
    
    def data_count(self, obj):
        count = obj.market_data.count()
        url = reverse('admin:market_data_marketdata_changelist') + f'?ticker__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)
    data_count.short_description = 'Data Points'


@admin.register(MarketData)
class MarketDataAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'timestamp', 'timeframe', 'close', 'volume', 'data_source']
    list_filter = ['timeframe', 'data_source', 'timestamp', 'ticker__exchange']
    search_fields = ['ticker__symbol', 'ticker__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['ticker', 'data_source']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'timestamp', 'timeframe', 'data_source')
        }),
        ('OHLC Data', {
            'fields': ('open', 'high', 'low', 'close', 'adjusted_close')
        }),
        ('Volume and Additional', {
            'fields': ('volume', 'vwap', 'transactions')
        }),
        ('Quality', {
            'fields': ('is_adjusted',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('ticker', 'data_source')


@admin.register(FundamentalData)
class FundamentalDataAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'report_date', 'period_type', 'pe_ratio', 'roe', 'revenue']
    list_filter = ['period_type', 'report_date', 'ticker__sector']
    search_fields = ['ticker__symbol', 'ticker__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['ticker']
    date_hierarchy = 'report_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'report_date', 'period_type')
        }),
        ('Valuation Metrics', {
            'fields': ('pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio')
        }),
        ('Profitability Metrics', {
            'fields': ('roe', 'roa', 'roic', 'profit_margin')
        }),
        ('Financial Health', {
            'fields': ('debt_to_equity', 'current_ratio', 'quick_ratio')
        }),
        ('Growth Metrics', {
            'fields': ('revenue_growth', 'earnings_growth')
        }),
        ('Financial Data', {
            'fields': ('revenue', 'net_income', 'total_assets', 'total_debt')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TechnicalIndicator)
class TechnicalIndicatorAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'indicator_name', 'timestamp', 'timeframe', 'value', 'created_at']
    list_filter = ['indicator_name', 'timeframe', 'timestamp']
    search_fields = ['ticker__symbol', 'indicator_name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['ticker']
    date_hierarchy = 'timestamp'


@admin.register(DataIngestionLog)
class DataIngestionLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'data_source', 'start_time', 'status', 'symbols_count', 'records_inserted', 'execution_time_seconds']
    list_filter = ['status', 'data_source', 'start_time']
    readonly_fields = ['created_at', 'updated_at', 'execution_time_seconds']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('data_source', 'start_time', 'end_time', 'status')
        }),
        ('Symbols', {
            'fields': ('symbols_requested', 'symbols_successful', 'symbols_failed')
        }),
        ('Results', {
            'fields': ('records_inserted', 'execution_time_seconds', 'error_message')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def symbols_count(self, obj):
        return len(obj.symbols_requested) if obj.symbols_requested else 0
    symbols_count.short_description = 'Symbols'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('data_source')


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'base_currency', 'positions_count', 'total_value', 'created_at']
    list_filter = ['base_currency', 'created_at', 'is_active']
    search_fields = ['name', 'user__username', 'description']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user']
    
    def positions_count(self, obj):
        return obj.positions.count()
    positions_count.short_description = 'Positions'
    
    def total_value(self, obj):
        # This would calculate the actual portfolio value
        return "N/A"  # Placeholder
    total_value.short_description = 'Total Value'


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['portfolio', 'ticker', 'quantity', 'avg_cost', 'current_price', 'unrealized_pnl', 'last_updated']
    list_filter = ['portfolio', 'ticker__sector', 'first_purchase_date']
    search_fields = ['portfolio__name', 'ticker__symbol']
    readonly_fields = ['first_purchase_date', 'last_updated']
    raw_id_fields = ['portfolio', 'ticker']
    
    def unrealized_pnl(self, obj):
        if obj.current_price and obj.avg_cost:
            pnl = obj.quantity * (obj.current_price - obj.avg_cost)
            color = 'green' if pnl >= 0 else 'red'
            return format_html('<span style="color: {};">${:,.2f}</span>', color, pnl)
        return "-"
    unrealized_pnl.short_description = 'Unrealized P&L'


# Custom admin site configuration
admin.site.site_header = "QSuite Quantitative Research Platform"
admin.site.site_title = "QSuite Admin"
admin.site.index_title = "Market Data Administration"

# Add custom CSS for better admin interface
admin.site.enable_nav_sidebar = True
