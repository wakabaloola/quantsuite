# apps/risk_management/serializers.py
from rest_framework import serializers
from apps.risk_management.models import (
    PositionLimit, RiskAlert, PortfolioRisk
)
from apps.trading_simulation.serializers import SimulatedInstrumentSerializer


class PositionLimitSerializer(serializers.ModelSerializer):
    """Serializer for position limits"""
    user = serializers.StringRelatedField(read_only=True)
    instrument = SimulatedInstrumentSerializer(read_only=True)
    
    class Meta:
        model = PositionLimit
        fields = [
            'id', 'user', 'limit_type', 'instrument', 'sector', 'exchange',
            'max_position_value', 'max_position_quantity', 'max_percentage_of_portfolio',
            'max_daily_loss', 'is_active', 'warning_threshold_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class RiskAlertSerializer(serializers.ModelSerializer):
    """Serializer for risk alerts"""
    user = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = RiskAlert
        fields = [
            'id', 'user', 'alert_type', 'severity', 'message', 'is_acknowledged',
            'acknowledged_at', 'is_resolved', 'resolved_at', 'current_value',
            'limit_value', 'breach_percentage', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']


class PortfolioRiskSerializer(serializers.ModelSerializer):
    """Serializer for portfolio risk metrics"""
    user = serializers.StringRelatedField(read_only=True)
    
    # Calculated fields
    net_exposure = serializers.SerializerMethodField()
    total_exposure = serializers.SerializerMethodField()
    
    class Meta:
        model = PortfolioRisk
        fields = [
            'id', 'user', 'calculation_date', 'total_portfolio_value',
            'cash_balance', 'long_market_value', 'short_market_value',
            'portfolio_var_1d', 'portfolio_beta', 'portfolio_volatility',
            'max_position_weight', 'top_5_concentration', 'sector_concentration',
            'gross_leverage', 'net_leverage', 'daily_pnl', 'mtd_pnl', 'ytd_pnl',
            'risk_status', 'active_alerts_count', 'net_exposure', 'total_exposure',
            'created_at'
        ]
        read_only_fields = ['user', 'created_at']
    
    def get_net_exposure(self, obj):
        return float(obj.net_exposure)
    
    def get_total_exposure(self, obj):
        return float(obj.total_exposure)
