# apps/market_data/serializers.py
"""Serializers for market data API: these classes convert model instances to/from JSON for API use via Django REST Framework"""
from rest_framework import serializers
from .models import (
    DataSource, Exchange, Ticker, MarketData, FundamentalData,
    TechnicalIndicator, DataIngestionLog, Portfolio, Position,
    Sector, Industry
)


class ExchangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exchange
        fields = ['id', 'name', 'code', 'country', 'currency', 'timezone', 'trading_hours']


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ['id', 'name', 'code']


class IndustrySerializer(serializers.ModelSerializer):
    sector = SectorSerializer(read_only=True)

    class Meta:
        model = Industry
        fields = ['id', 'name', 'sector']


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = [
            'id', 'name', 'code', 'url', 'api_endpoint', 'requires_api_key',
            'rate_limit_per_minute', 'supported_markets', 'supported_timeframes',
            'is_active'
        ]


class TickerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for ticker lists"""
    exchange_code = serializers.CharField(source='exchange.code', read_only=True)
    sector_name = serializers.CharField(source='sector.name', read_only=True)

    class Meta:
        model = Ticker
        fields = [
            'id', 'symbol', 'name', 'exchange_code', 'sector_name',
            'currency', 'country', 'market_cap', 'is_active'
        ]


class TickerDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual ticker views"""
    exchange = ExchangeSerializer(read_only=True)
    sector = SectorSerializer(read_only=True)
    industry = IndustrySerializer(read_only=True)
    data_source = DataSourceSerializer(read_only=True)

    # Latest market data
    latest_price = serializers.SerializerMethodField()
    price_change = serializers.SerializerMethodField()
    price_change_percent = serializers.SerializerMethodField()

    class Meta:
        model = Ticker
        fields = [
            'id', 'symbol', 'name', 'description', 'exchange', 'sector', 'industry',
            'currency', 'country', 'data_source', 'market_cap', 'shares_outstanding',
            'yfinance_symbol', 'alpha_vantage_symbol', 'last_updated', 'is_active',
            'latest_price', 'price_change', 'price_change_percent'
        ]

    def get_latest_price(self, obj):
        latest = obj.market_data.first()
        return float(latest.close) if latest else None

    def get_price_change(self, obj):
        recent_data = obj.market_data.all()[:2]
        if len(recent_data) >= 2:
            return float(recent_data[0].close - recent_data[1].close)
        return None

    def get_price_change_percent(self, obj):
        recent_data = obj.market_data.all()[:2]
        if len(recent_data) >= 2:
            old_price = recent_data[1].close
            new_price = recent_data[0].close
            return float((new_price - old_price) / old_price * 100)
        return None


class TickerCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating tickers"""
    exchange_id = serializers.IntegerField(write_only=True)
    sector_id = serializers.IntegerField(write_only=True, required=False)
    industry_id = serializers.IntegerField(write_only=True, required=False)
    data_source_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Ticker
        fields = [
            'symbol', 'name', 'description', 'currency', 'country',
            'exchange_id', 'sector_id', 'industry_id', 'data_source_id',
            'market_cap', 'shares_outstanding'
        ]


class MarketDataSerializer(serializers.ModelSerializer):
    ticker_symbol = serializers.CharField(source='ticker.symbol', read_only=True)

    class Meta:
        model = MarketData
        fields = [
            'id', 'ticker_symbol', 'timestamp', 'timeframe', 'open', 'high',
            'low', 'close', 'volume', 'adjusted_close', 'vwap', 'transactions'
        ]


class MarketDataCreateSerializer(serializers.ModelSerializer):
    """Optimized serializer for bulk market data creation"""
    ticker_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = MarketData
        fields = [
            'ticker_id', 'timestamp', 'timeframe', 'open', 'high',
            'low', 'close', 'volume', 'adjusted_close'
        ]


class MarketDataBulkSerializer(serializers.Serializer):
    """Serializer for bulk market data operations"""
    data = serializers.ListField(
        child=MarketDataCreateSerializer(),
        max_length=10000
    )


class OHLCVSerializer(serializers.Serializer):
    """Simple OHLCV data serializer for performance"""
    timestamp = serializers.DateTimeField()
    open = serializers.DecimalField(max_digits=20, decimal_places=6)
    high = serializers.DecimalField(max_digits=20, decimal_places=6)
    low = serializers.DecimalField(max_digits=20, decimal_places=6)
    close = serializers.DecimalField(max_digits=20, decimal_places=6)
    volume = serializers.DecimalField(max_digits=20, decimal_places=2)


class FundamentalDataSerializer(serializers.ModelSerializer):
    ticker_symbol = serializers.CharField(source='ticker.symbol', read_only=True)

    class Meta:
        model = FundamentalData
        fields = [
            'id', 'ticker_symbol', 'report_date', 'period_type',
            'pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
            'roe', 'roa', 'roic', 'profit_margin',
            'debt_to_equity', 'current_ratio', 'quick_ratio',
            'revenue_growth', 'earnings_growth',
            'revenue', 'net_income', 'total_assets', 'total_debt'
        ]


class TechnicalIndicatorSerializer(serializers.ModelSerializer):
    ticker_symbol = serializers.CharField(source='ticker.symbol', read_only=True)

    class Meta:
        model = TechnicalIndicator
        fields = [
            'id', 'ticker_symbol', 'timestamp', 'timeframe', 'indicator_name',
            'value', 'values', 'parameters'
        ]


class DataIngestionLogSerializer(serializers.ModelSerializer):
    data_source_name = serializers.CharField(source='data_source.name', read_only=True)

    class Meta:
        model = DataIngestionLog
        fields = [
            'id', 'data_source_name', 'symbols_requested', 'symbols_successful',
            'symbols_failed', 'start_time', 'end_time', 'records_inserted',
            'status', 'error_message', 'execution_time_seconds'
        ]


class DataIngestionRequestSerializer(serializers.Serializer):
    """Serializer for data ingestion requests"""
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        max_length=100
    )
    data_source = serializers.ChoiceField(choices=['yfinance', 'alpha_vantage'], default='yfinance')
    period = serializers.CharField(default='1y')
    interval = serializers.CharField(default='1d')
    update_ticker_info = serializers.BooleanField(default=True)


class QuoteRequestSerializer(serializers.Serializer):
    """Serializer for real-time quote requests"""
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        max_length=50
    )


class QuoteResponseSerializer(serializers.Serializer):
    """Serializer for real-time quote responses"""
    symbol = serializers.CharField()
    price = serializers.DecimalField(max_digits=20, decimal_places=6)
    change = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    change_percent = serializers.DecimalField(max_digits=8, decimal_places=4, allow_null=True)
    volume = serializers.IntegerField(allow_null=True)
    market_cap = serializers.IntegerField(allow_null=True)
    pe_ratio = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    timestamp = serializers.DateTimeField()
    market_status = serializers.CharField()
    bid = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    ask = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)


class PortfolioSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    total_value = serializers.SerializerMethodField()
    positions_count = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = [
            'id', 'name', 'description', 'base_currency', 'user_username',
            'initial_cash', 'current_cash', 'total_value', 'positions_count',
            'created_at', 'updated_at'
        ]

    def get_total_value(self, obj):
        # Would calculate total portfolio value
        return 0.0

    def get_positions_count(self, obj):
        return obj.positions.count()


class PositionSerializer(serializers.ModelSerializer):
    ticker_symbol = serializers.CharField(source='ticker.symbol', read_only=True)
    ticker_name = serializers.CharField(source='ticker.name', read_only=True)
    current_value = serializers.SerializerMethodField()
    unrealized_pnl = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = [
            'id', 'ticker_symbol', 'ticker_name', 'quantity', 'avg_cost',
            'current_price', 'current_value', 'unrealized_pnl',
            'first_purchase_date', 'last_updated'
        ]

    def get_current_value(self, obj):
        if obj.current_price:
            return float(obj.quantity * obj.current_price)
        return 0.0

    def get_unrealized_pnl(self, obj):
        if obj.current_price:
            return float(obj.quantity * (obj.current_price - obj.avg_cost))
        return 0.0


class SymbolSearchSerializer(serializers.Serializer):
    """Serializer for symbol search requests"""
    query = serializers.CharField(max_length=100)
    country = serializers.CharField(max_length=2, required=False)
    exchange = serializers.CharField(max_length=20, required=False)
    limit = serializers.IntegerField(default=20, max_value=100)


class SymbolSearchResultSerializer(serializers.Serializer):
    """Serializer for symbol search results"""
    symbol = serializers.CharField()
    name = serializers.CharField()
    exchange = serializers.CharField()
    country = serializers.CharField()
    currency = serializers.CharField()
    sector = serializers.CharField(allow_null=True)
    industry = serializers.CharField(allow_null=True)


class AnalyticsRequestSerializer(serializers.Serializer):
    """Base serializer for analytics requests"""
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        max_length=50
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    period = serializers.CharField(default='1y')


class TechnicalIndicatorsRequestSerializer(AnalyticsRequestSerializer):
    """Serializer for technical indicators requests"""
    indicators = serializers.ListField(
        child=serializers.CharField(),
        default=['rsi', 'macd', 'sma_20', 'sma_50']
    )
    timeframe = serializers.CharField(default='1d')


class CorrelationMatrixRequestSerializer(serializers.Serializer):
    """Serializer for correlation matrix requests"""
    symbols = serializers.ListField(
        child=serializers.CharField(max_length=20),
        max_length=50
    )
    period = serializers.CharField(default='1y')
    method = serializers.ChoiceField(choices=['pearson', 'spearman'], default='pearson')


class ScreeningCriteriaSerializer(serializers.Serializer):
    """Serializer for screening criteria"""
    indicator = serializers.CharField()
    operator = serializers.ChoiceField(choices=['>', '<', '>=', '<=', '==', '!='])
    value = serializers.FloatField()
    period = serializers.IntegerField(required=False)
    description = serializers.CharField(required=False)


class StockScreeningRequestSerializer(serializers.Serializer):
    """Serializer for stock screening requests"""
    criteria = serializers.ListField(
        child=ScreeningCriteriaSerializer(),
        min_length=1
    )
    universe = serializers.CharField(default='ALL')
    sector = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    market_cap_min = serializers.IntegerField(required=False)
    market_cap_max = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(default=50, max_value=200)
