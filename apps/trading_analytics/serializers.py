# apps/trading_analytics/serializers.py
from rest_framework import serializers
from apps.trading_analytics.models import (
    TradingPerformance, StrategyPerformance, PortfolioAnalytics
)
from apps.trading_simulation.serializers import SimulatedPositionSerializer


class TradingPerformanceSerializer(serializers.ModelSerializer):
    """Serializer for trading performance metrics"""
    user = serializers.StringRelatedField(read_only=True)
    
    # Calculated fields
    win_rate_percentage = serializers.SerializerMethodField()
    avg_return_per_trade = serializers.SerializerMethodField()
    
    class Meta:
        model = TradingPerformance
        fields = [
            'id', 'user', 'period_type', 'period_start', 'period_end',
            'starting_value', 'ending_value', 'peak_value', 'trough_value',
            'total_return', 'annualized_return', 'volatility', 'sharpe_ratio',
            'max_drawdown', 'max_drawdown_duration_days', 'total_trades',
            'winning_trades', 'losing_trades', 'break_even_trades',
            'realized_pnl', 'unrealized_pnl', 'total_fees', 'gross_pnl', 'net_pnl',
            'average_win', 'average_loss', 'largest_win', 'largest_loss',
            'profit_factor', 'calmar_ratio', 'sortino_ratio',
            'win_rate_percentage', 'avg_return_per_trade', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']
    
    def get_win_rate_percentage(self, obj):
        return obj.win_rate
    
    def get_avg_return_per_trade(self, obj):
        return float(obj.average_return_per_trade)


class PortfolioAnalyticsSerializer(serializers.ModelSerializer):
    """Serializer for portfolio analytics"""
    user = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = PortfolioAnalytics
        fields = [
            'id', 'user', 'analysis_date', 'total_positions', 'long_positions',
            'short_positions', 'cash_percentage', 'sector_diversification',
            'geographic_diversification', 'market_cap_distribution',
            'portfolio_beta', 'portfolio_correlation_sp500', 'concentration_hhi',
            'security_selection_return', 'sector_allocation_return', 'interaction_return',
            'portfolio_turnover', 'average_holding_period_days', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']



class PortfolioSummarySerializer(serializers.Serializer):
    """Serializer for portfolio summary data"""
    total_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    cash_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    positions_count = serializers.IntegerField()
    unrealized_pnl = serializers.DecimalField(max_digits=15, decimal_places=2)
    daily_pnl = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_return_percentage = serializers.DecimalField(max_digits=8, decimal_places=4)
    positions = SimulatedPositionSerializer(many=True, read_only=True)


class MarketDataUpdateRequestSerializer(serializers.Serializer):
    """Request serializer for market data updates"""
    instrument_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of instrument IDs to update (empty = all)"
    )
    force_update = serializers.BooleanField(
        default=False,
        help_text="Force update even if recently updated"
    )

