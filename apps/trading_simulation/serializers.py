# apps/trading_simulation/serializers.py
"""
SIMULATED Trading Serializers
============================
Serializers for VIRTUAL trading simulation API endpoints.
All data structures are for PAPER TRADING.
"""

from rest_framework import serializers
from .models import (
    SimulatedExchange, SimulatedInstrument, SimulatedPosition, TradingSession, 
    MarketMaker, UserSimulationProfile, SimulationScenario
)
from apps.market_data.serializers import TickerListSerializer, ExchangeSerializer


class SimulatedExchangeSerializer(serializers.ModelSerializer):
    """Serializer for simulated exchanges"""
    real_exchange = ExchangeSerializer(read_only=True)
    real_exchange_id = serializers.IntegerField(write_only=True, required=False)
    
    # Calculated fields
    total_instruments = serializers.SerializerMethodField()
    active_instruments = serializers.SerializerMethodField()
    trading_volume_today = serializers.SerializerMethodField()
    
    class Meta:
        model = SimulatedExchange
        fields = [
            'id', 'name', 'code', 'description', 'real_exchange', 'real_exchange_id',
            'status', 'trading_fee_percentage', 'minimum_order_size', 'maximum_order_size',
            'simulated_latency_ms', 'enable_market_making', 'total_instruments',
            'active_instruments', 'trading_volume_today', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_total_instruments(self, obj):
        return obj.instruments.count()
    
    def get_active_instruments(self, obj):
        return obj.instruments.filter(is_tradable=True).count()
    
    def get_trading_volume_today(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        total_volume = obj.trades.filter(
            trade_timestamp__date=today
        ).aggregate(
            total=serializers.models.Sum('quantity')
        )['total'] or 0
        return total_volume


class SimulatedInstrumentSerializer(serializers.ModelSerializer):
    """Serializer for simulated instruments"""
    real_ticker = TickerListSerializer(read_only=True)
    exchange = serializers.StringRelatedField(read_only=True)
    
    # Current market data
    current_price = serializers.SerializerMethodField()
    daily_change = serializers.SerializerMethodField()
    daily_volume = serializers.SerializerMethodField()
    
    class Meta:
        model = SimulatedInstrument
        fields = [
            'id', 'real_ticker', 'exchange', 'is_tradable', 'price_multiplier',
            'min_price_increment', 'max_daily_volume', 'volatility_multiplier',
            'current_price', 'daily_change', 'daily_volume', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_current_price(self, obj):
        current_price = obj.get_current_simulated_price()
        return float(current_price) if current_price else None
    
    def get_daily_change(self, obj):
        try:
            order_book = obj.order_book
            if order_book.last_trade_price and order_book.opening_price:
                change = order_book.last_trade_price - order_book.opening_price
                return float(change)
            return 0.0
        except:
            return 0.0
    
    def get_daily_volume(self, obj):
        try:
            return obj.order_book.daily_volume
        except:
            return 0


class TradingSessionSerializer(serializers.ModelSerializer):
    """Serializer for trading sessions"""
    exchange = SimulatedExchangeSerializer(read_only=True)
    exchange_id = serializers.IntegerField(write_only=True, required=False)
    
    # Session statistics
    duration_minutes = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = TradingSession
        fields = [
            'id', 'exchange', 'exchange_id', 'session_type', 'start_time', 'end_time',
            'status', 'allow_short_selling', 'allow_margin_trading', 
            'circuit_breaker_threshold', 'duration_minutes', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_duration_minutes(self, obj):
        if obj.start_time and obj.end_time:
            delta = obj.end_time - obj.start_time
            return int(delta.total_seconds() / 60)
        return None
    
    def get_is_active(self, obj):
        from django.utils import timezone
        now = timezone.now()
        return (obj.status == 'ACTIVE' and 
                obj.start_time <= now <= obj.end_time)


class MarketMakerSerializer(serializers.ModelSerializer):
    """Serializer for market makers"""
    exchange = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = MarketMaker
        fields = [
            'id', 'exchange', 'name', 'algorithm_type', 'default_spread_bps',
            'max_position_size', 'quote_size', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class UserSimulationProfileSerializer(serializers.ModelSerializer):
    """Serializer for user simulation profiles"""
    user = serializers.StringRelatedField(read_only=True)
    
    # Calculated performance metrics
    total_return_percentage = serializers.SerializerMethodField()
    win_rate_percentage = serializers.SerializerMethodField()
    profit_loss = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSimulationProfile
        fields = [
            'id', 'user', 'virtual_cash_balance', 'initial_virtual_balance',
            'default_order_size', 'risk_tolerance', 'experience_level',
            'enable_margin_trading', 'enable_options_trading', 'enable_short_selling',
            'total_trades_executed', 'profitable_trades', 'current_portfolio_value',
            'total_return_percentage', 'win_rate_percentage', 'profit_loss',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'user', 'total_trades_executed', 'profitable_trades', 
            'current_portfolio_value', 'created_at', 'updated_at'
        ]
    
    def get_total_return_percentage(self, obj):
        return obj.calculate_total_return_percentage()
    
    def get_win_rate_percentage(self, obj):
        return obj.get_win_rate()
    
    def get_profit_loss(self, obj):
        return float(obj.current_portfolio_value - obj.initial_virtual_balance)


class SimulatedPositionSerializer(serializers.ModelSerializer):
    """Serializer for simulated positions"""
    user = serializers.StringRelatedField(read_only=True)
    instrument = SimulatedInstrumentSerializer(read_only=True)

    # Calculated fields
    current_return_percentage = serializers.SerializerMethodField()
    position_type = serializers.SerializerMethodField()

    class Meta:
        model = SimulatedPosition
        fields = [
            'id', 'user', 'instrument', 'quantity', 'average_cost', 'total_cost',
            'current_price', 'market_value', 'unrealized_pnl', 'realized_pnl',
            'total_fees_paid', 'daily_pnl', 'position_var', 'position_type',
            'current_return_percentage', 'first_trade_timestamp', 'last_trade_timestamp',
            'updated_at'
        ]
        read_only_fields = [
            'user', 'market_value', 'unrealized_pnl', 'first_trade_timestamp',
            'last_trade_timestamp', 'updated_at'
        ]

    def get_current_return_percentage(self, obj):
        if obj.total_cost > 0:
            return float((obj.unrealized_pnl / obj.total_cost) * 100)
        return 0.0

    def get_position_type(self, obj):
        if obj.quantity > 0:
            return "LONG"
        elif obj.quantity < 0:
            return "SHORT"
        else:
            return "FLAT"

class SimulationScenarioSerializer(serializers.ModelSerializer):
    """Serializer for simulation scenarios"""

    class Meta:
        model = SimulationScenario
        fields = [
            'id', 'name', 'description', 'scenario_type', 'volatility_factor',
            'volume_factor', 'liquidity_factor', 'daily_drift_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

