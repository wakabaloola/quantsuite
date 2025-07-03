# apps/market_data/filters.py
"""Advanced filtering for market data queries"""

import django_filters
from django.db.models import Q
from django.db import models
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

from .models import Ticker, MarketData, Exchange, Sector, Industry, FundamentalData


class TickerFilter(django_filters.FilterSet):
    """Advanced filtering for tickers"""
    
    # Basic filters
    symbol = django_filters.CharFilter(lookup_expr='icontains')
    name = django_filters.CharFilter(lookup_expr='icontains')
    currency = django_filters.MultipleChoiceFilter(choices=[
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('JPY', 'Japanese Yen'),
        ('CAD', 'Canadian Dollar'),
        ('AUD', 'Australian Dollar'),
        ('CHF', 'Swiss Franc'),
        ('CNY', 'Chinese Yuan'),
        ('HKD', 'Hong Kong Dollar'),
        ('INR', 'Indian Rupee'),
    ])
    
    # Geographic filters
    country = django_filters.MultipleChoiceFilter(choices=[
        ('US', 'United States'),
        ('GB', 'United Kingdom'),
        ('CA', 'Canada'),
        ('AU', 'Australia'),
        ('DE', 'Germany'),
        ('FR', 'France'),
        ('JP', 'Japan'),
        ('CN', 'China'),
        ('HK', 'Hong Kong'),
        ('IN', 'India'),
        ('GR', 'Greece'),
        ('IT', 'Italy'),
        ('ES', 'Spain'),
        ('NL', 'Netherlands'),
        ('CH', 'Switzerland'),
        ('BR', 'Brazil'),
        ('MX', 'Mexico'),
        ('KR', 'South Korea'),
        ('SG', 'Singapore'),
    ])
    
    # Exchange filters
    exchange = django_filters.ModelMultipleChoiceFilter(queryset=Exchange.objects.all())
    exchange_code = django_filters.CharFilter(field_name='exchange__code', lookup_expr='iexact')
    
    # Sector and industry filters
    sector = django_filters.ModelMultipleChoiceFilter(queryset=Sector.objects.all())
    sector_name = django_filters.CharFilter(field_name='sector__name', lookup_expr='icontains')
    industry = django_filters.ModelMultipleChoiceFilter(queryset=Industry.objects.all())
    industry_name = django_filters.CharFilter(field_name='industry__name', lookup_expr='icontains')
    
    # Market cap filters
    market_cap_min = django_filters.NumberFilter(field_name='market_cap', lookup_expr='gte')
    market_cap_max = django_filters.NumberFilter(field_name='market_cap', lookup_expr='lte')
    market_cap_range = django_filters.RangeFilter(field_name='market_cap')
    
    # Market cap categories
    market_cap_category = django_filters.ChoiceFilter(
        choices=[
            ('nano', 'Nano Cap (< $50M)'),
            ('micro', 'Micro Cap ($50M - $300M)'),
            ('small', 'Small Cap ($300M - $2B)'),
            ('mid', 'Mid Cap ($2B - $10B)'),
            ('large', 'Large Cap ($10B - $200B)'),
            ('mega', 'Mega Cap (> $200B)'),
        ],
        method='filter_by_market_cap_category'
    )
    
    # Activity filters
    is_active = django_filters.BooleanFilter()
    has_market_data = django_filters.BooleanFilter(method='filter_has_market_data')
    has_recent_data = django_filters.BooleanFilter(method='filter_has_recent_data')
    
    # Data source filters
    data_source = django_filters.CharFilter(field_name='data_source__code', lookup_expr='iexact')
    
    # Search across multiple fields
    search = django_filters.CharFilter(method='filter_search')
    
    class Meta:
        model = Ticker
        fields = []
    
    def filter_by_market_cap_category(self, queryset, name, value):
        """Filter by market cap category"""
        if value == 'nano':
            return queryset.filter(market_cap__lt=50000000)
        elif value == 'micro':
            return queryset.filter(market_cap__gte=50000000, market_cap__lt=300000000)
        elif value == 'small':
            return queryset.filter(market_cap__gte=300000000, market_cap__lt=2000000000)
        elif value == 'mid':
            return queryset.filter(market_cap__gte=2000000000, market_cap__lt=10000000000)
        elif value == 'large':
            return queryset.filter(market_cap__gte=10000000000, market_cap__lt=200000000000)
        elif value == 'mega':
            return queryset.filter(market_cap__gte=200000000000)
        return queryset
    
    def filter_has_market_data(self, queryset, name, value):
        """Filter tickers that have market data"""
        if value:
            return queryset.filter(market_data__isnull=False).distinct()
        else:
            return queryset.filter(market_data__isnull=True)
    
    def filter_has_recent_data(self, queryset, name, value):
        """Filter tickers with recent market data (last 7 days)"""
        if value:
            recent_date = timezone.now() - timedelta(days=7)
            return queryset.filter(market_data__timestamp__gte=recent_date).distinct()
        return queryset
    
    def filter_search(self, queryset, name, value):
        """Search across symbol, name, and description"""
        return queryset.filter(
            Q(symbol__icontains=value) |
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )


class MarketDataFilter(django_filters.FilterSet):
    """Advanced filtering for market data"""
    
    # Ticker filters
    ticker = django_filters.ModelChoiceFilter(queryset=Ticker.objects.all())
    symbol = django_filters.CharFilter(field_name='ticker__symbol', lookup_expr='iexact')
    symbols = django_filters.CharFilter(method='filter_symbols')
    
    # Time filters
    timestamp = django_filters.DateTimeFilter()
    timestamp_after = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    timestamp_before = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    timestamp_range = django_filters.DateTimeFromToRangeFilter(field_name='timestamp')
    
    # Date filters (for easier querying)
    date = django_filters.DateFilter(field_name='timestamp__date')
    date_after = django_filters.DateFilter(field_name='timestamp__date', lookup_expr='gte')
    date_before = django_filters.DateFilter(field_name='timestamp__date', lookup_expr='lte')
    date_range = django_filters.DateFromToRangeFilter(field_name='timestamp__date')
    
    # Period filters (convenience)
    period = django_filters.ChoiceFilter(
        choices=[
            ('1d', 'Last 1 day'),
            ('5d', 'Last 5 days'),
            ('1w', 'Last 1 week'),
            ('1m', 'Last 1 month'),
            ('3m', 'Last 3 months'),
            ('6m', 'Last 6 months'),
            ('1y', 'Last 1 year'),
            ('2y', 'Last 2 years'),
            ('5y', 'Last 5 years'),
        ],
        method='filter_by_period'
    )
    
    # Timeframe filters
    timeframe = django_filters.MultipleChoiceFilter(choices=[
        ('1m', '1 Minute'),
        ('5m', '5 Minutes'),
        ('15m', '15 Minutes'),
        ('30m', '30 Minutes'),
        ('1h', '1 Hour'),
        ('1d', '1 Day'),
        ('1wk', '1 Week'),
        ('1mo', '1 Month'),
    ])
    
    # Price filters
    close_min = django_filters.NumberFilter(field_name='close', lookup_expr='gte')
    close_max = django_filters.NumberFilter(field_name='close', lookup_expr='lte')
    close_range = django_filters.RangeFilter(field_name='close')
    
    # Volume filters
    volume_min = django_filters.NumberFilter(field_name='volume', lookup_expr='gte')
    volume_max = django_filters.NumberFilter(field_name='volume', lookup_expr='lte')
    volume_range = django_filters.RangeFilter(field_name='volume')
    
    # High volume filter (above average)
    high_volume = django_filters.BooleanFilter(method='filter_high_volume')
    
    # Price movement filters
    price_change_min = django_filters.NumberFilter(method='filter_price_change_min')
    price_change_max = django_filters.NumberFilter(method='filter_price_change_max')
    
    # Gap filters (price gaps between sessions)
    has_gap = django_filters.BooleanFilter(method='filter_has_gap')
    gap_percentage_min = django_filters.NumberFilter(method='filter_gap_percentage_min')
    
    # Data quality filters
    data_source = django_filters.CharFilter(field_name='data_source__code', lookup_expr='iexact')
    is_adjusted = django_filters.BooleanFilter()
    
    # OHLC validation filters
    valid_ohlc = django_filters.BooleanFilter(method='filter_valid_ohlc')
    
    class Meta:
        model = MarketData
        fields = []
    
    def filter_symbols(self, queryset, name, value):
        """Filter by multiple symbols (comma-separated)"""
        symbols = [s.strip().upper() for s in value.split(',')]
        return queryset.filter(ticker__symbol__in=symbols)
    
    def filter_by_period(self, queryset, name, value):
        """Filter by predefined periods"""
        period_map = {
            '1d': 1,
            '5d': 5,
            '1w': 7,
            '1m': 30,
            '3m': 90,
            '6m': 180,
            '1y': 365,
            '2y': 730,
            '5y': 1825,
        }
        
        days = period_map.get(value)
        if days:
            start_date = timezone.now() - timedelta(days=days)
            return queryset.filter(timestamp__gte=start_date)
        return queryset
    
    def filter_high_volume(self, queryset, name, value):
        """Filter for high volume days (above ticker's average)"""
        if value:
            # This would require a complex query to calculate average volume per ticker
            # For now, use a simple heuristic
            return queryset.extra(
                where=["volume > (SELECT AVG(volume) * 1.5 FROM market_data_marketdata md2 WHERE md2.ticker_id = market_data_marketdata.ticker_id)"]
            )
        return queryset
    
    def filter_price_change_min(self, queryset, name, value):
        """Filter by minimum daily price change percentage"""
        return queryset.extra(
            where=["(close - open) / open * 100 >= %s"],
            params=[value]
        )
    
    def filter_price_change_max(self, queryset, name, value):
        """Filter by maximum daily price change percentage"""
        return queryset.extra(
            where=["(close - open) / open * 100 <= %s"],
            params=[value]
        )
    
    def filter_has_gap(self, queryset, name, value):
        """Filter for price gaps"""
        if value:
            # Gap up: open > previous close
            # Gap down: open < previous close
            return queryset.extra(
                where=["open != (SELECT close FROM market_data_marketdata md2 WHERE md2.ticker_id = market_data_marketdata.ticker_id AND md2.timestamp < market_data_marketdata.timestamp ORDER BY md2.timestamp DESC LIMIT 1)"]
            )
        return queryset
    
    def filter_gap_percentage_min(self, queryset, name, value):
        """Filter by minimum gap percentage"""
        return queryset.extra(
            where=["ABS((open - (SELECT close FROM market_data_marketdata md2 WHERE md2.ticker_id = market_data_marketdata.ticker_id AND md2.timestamp < market_data_marketdata.timestamp ORDER BY md2.timestamp DESC LIMIT 1)) / (SELECT close FROM market_data_marketdata md2 WHERE md2.ticker_id = market_data_marketdata.ticker_id AND md2.timestamp < market_data_marketdata.timestamp ORDER BY md2.timestamp DESC LIMIT 1) * 100) >= %s"],
            params=[value]
        )
    
    def filter_valid_ohlc(self, queryset, name, value):
        """Filter for valid OHLC data (high >= low, etc.)"""
        if value:
            return queryset.filter(
                high__gte=models.F('low')
            ).filter(
                high__gte=models.F('open')
            ).filter(
                high__gte=models.F('close')
            ).filter(
                low__lte=models.F('open')
            ).filter(
                low__lte=models.F('close')
            )
        return queryset


class FundamentalDataFilter(django_filters.FilterSet):
    """Filtering for fundamental data"""
    
    ticker = django_filters.ModelChoiceFilter(queryset=Ticker.objects.all())
    symbol = django_filters.CharFilter(field_name='ticker__symbol', lookup_expr='iexact')
    
    # Report filters
    period_type = django_filters.ChoiceFilter(choices=[
        ('annual', 'Annual'),
        ('quarterly', 'Quarterly'),
    ])
    
    report_date_after = django_filters.DateFilter(field_name='report_date', lookup_expr='gte')
    report_date_before = django_filters.DateFilter(field_name='report_date', lookup_expr='lte')
    
    # Valuation metric filters
    pe_ratio_min = django_filters.NumberFilter(field_name='pe_ratio', lookup_expr='gte')
    pe_ratio_max = django_filters.NumberFilter(field_name='pe_ratio', lookup_expr='lte')
    pb_ratio_min = django_filters.NumberFilter(field_name='pb_ratio', lookup_expr='gte')
    pb_ratio_max = django_filters.NumberFilter(field_name='pb_ratio', lookup_expr='lte')
    
    # Profitability filters
    roe_min = django_filters.NumberFilter(field_name='roe', lookup_expr='gte')
    roe_max = django_filters.NumberFilter(field_name='roe', lookup_expr='lte')
    roa_min = django_filters.NumberFilter(field_name='roa', lookup_expr='gte')
    roa_max = django_filters.NumberFilter(field_name='roa', lookup_expr='lte')
    
    # Financial health filters
    debt_to_equity_max = django_filters.NumberFilter(field_name='debt_to_equity', lookup_expr='lte')
    current_ratio_min = django_filters.NumberFilter(field_name='current_ratio', lookup_expr='gte')
    
    # Growth filters
    revenue_growth_min = django_filters.NumberFilter(field_name='revenue_growth', lookup_expr='gte')
    earnings_growth_min = django_filters.NumberFilter(field_name='earnings_growth', lookup_expr='gte')
    
    class Meta:
        model = FundamentalData
        fields = []


# Custom filter for screening
class ScreeningFilter(django_filters.FilterSet):
    """Advanced screening filter combining technical and fundamental criteria"""
    
    # Technical screening
    rsi_min = django_filters.NumberFilter(method='filter_rsi_min')
    rsi_max = django_filters.NumberFilter(method='filter_rsi_max')
    
    # Price vs moving average
    price_vs_sma20 = django_filters.NumberFilter(method='filter_price_vs_sma20')
    price_vs_sma50 = django_filters.NumberFilter(method='filter_price_vs_sma50')
    
    # Volume filters
    volume_ratio_min = django_filters.NumberFilter(method='filter_volume_ratio_min')
    
    # Price performance
    performance_1m_min = django_filters.NumberFilter(method='filter_performance_1m_min')
    performance_1m_max = django_filters.NumberFilter(method='filter_performance_1m_max')
    
    class Meta:
        model = Ticker
        fields = []
    
    def filter_rsi_min(self, queryset, name, value):
        """Filter by minimum RSI value"""
        # This would require calculating RSI on the fly or using pre-calculated values
        # For now, return the queryset unchanged
        return queryset
    
    def filter_rsi_max(self, queryset, name, value):
        """Filter by maximum RSI value"""
        return queryset
    
    def filter_price_vs_sma20(self, queryset, name, value):
        """Filter by price vs 20-day SMA ratio"""
        return queryset
    
    def filter_price_vs_sma50(self, queryset, name, value):
        """Filter by price vs 50-day SMA ratio"""
        return queryset
    
    def filter_volume_ratio_min(self, queryset, name, value):
        """Filter by minimum volume ratio vs average"""
        return queryset
    
    def filter_performance_1m_min(self, queryset, name, value):
        """Filter by minimum 1-month performance"""
        return queryset
    
    def filter_performance_1m_max(self, queryset, name, value):
        """Filter by maximum 1-month performance"""
        return queryset
