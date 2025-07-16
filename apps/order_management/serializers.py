# apps/order_management/serializers.py
from rest_framework import serializers
from apps.order_management.models import (
    SimulatedOrder, SimulatedTrade, OrderBook, Fill
)
from apps.trading_simulation.serializers import SimulatedInstrumentSerializer

class SimulatedOrderSerializer(serializers.ModelSerializer):
    """Serializer for simulated orders"""
    user = serializers.StringRelatedField(read_only=True)
    instrument = SimulatedInstrumentSerializer(read_only=True)
    exchange = serializers.StringRelatedField(read_only=True)
    
    # Calculated fields
    fill_ratio_percentage = serializers.SerializerMethodField()
    order_value = serializers.SerializerMethodField()
    
    class Meta:
        model = SimulatedOrder
        fields = [
            'id', 'order_id', 'client_order_id', 'user', 'exchange', 'instrument',
            'side', 'order_type', 'quantity', 'price', 'stop_price', 'time_in_force',
            'display_quantity', 'minimum_quantity', 'status', 'filled_quantity',
            'remaining_quantity', 'average_fill_price', 'total_fees', 'total_commission',
            'order_timestamp', 'submission_timestamp', 'acknowledgment_timestamp',
            'first_fill_timestamp', 'last_fill_timestamp', 'completion_timestamp',
            'risk_checked', 'compliance_checked', 'rejection_reason',
            'fill_ratio_percentage', 'order_value', 'created_at'
        ]
        read_only_fields = [
            'order_id', 'user', 'filled_quantity', 'remaining_quantity',
            'average_fill_price', 'total_fees', 'total_commission',
            'order_timestamp', 'submission_timestamp', 'acknowledgment_timestamp',
            'first_fill_timestamp', 'last_fill_timestamp', 'completion_timestamp',
            'risk_checked', 'compliance_checked', 'created_at'
        ]
    
    def get_fill_ratio_percentage(self, obj):
        return obj.fill_ratio
    
    def get_order_value(self, obj):
        order_value = obj.calculate_notional_value()
        return float(order_value) if order_value else None


class OrderCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new orders"""
    instrument_id = serializers.IntegerField(write_only=True)
    exchange_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = SimulatedOrder
        fields = [
            'instrument_id', 'exchange_id', 'side', 'order_type', 'quantity',
            'price', 'stop_price', 'time_in_force', 'display_quantity',
            'minimum_quantity', 'client_order_id'
        ]
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value
    
    def validate_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Price must be positive")
        return value
    
    def validate(self, data):
        if data['order_type'] == 'LIMIT' and not data.get('price'):
            raise serializers.ValidationError(
                "Limit orders must have a price"
            )
        return data


class SimulatedTradeSerializer(serializers.ModelSerializer):
    """Serializer for simulated trades"""
    instrument = SimulatedInstrumentSerializer(read_only=True)
    exchange = serializers.StringRelatedField(read_only=True)
    
    # Order details (simplified)
    buy_order_id = serializers.UUIDField(source='buy_order.order_id', read_only=True)
    sell_order_id = serializers.UUIDField(source='sell_order.order_id', read_only=True)
    
    class Meta:
        model = SimulatedTrade
        fields = [
            'id', 'trade_id', 'exchange', 'instrument', 'buy_order_id', 'sell_order_id',
            'quantity', 'price', 'trade_timestamp', 'notional_value',
            'buyer_fees', 'seller_fees', 'is_aggressive', 'created_at'
        ]
        read_only_fields = ['trade_id', 'notional_value', 'created_at']


class OrderBookSerializer(serializers.ModelSerializer):
    """Serializer for order book data"""
    instrument = SimulatedInstrumentSerializer(read_only=True)
    
    # Calculated fields
    spread_absolute = serializers.SerializerMethodField()
    spread_bps = serializers.SerializerMethodField()
    mid_price = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderBook
        fields = [
            'id', 'instrument', 'best_bid_price', 'best_bid_quantity',
            'best_ask_price', 'best_ask_quantity', 'last_trade_price',
            'last_trade_quantity', 'last_trade_timestamp', 'daily_volume',
            'daily_turnover', 'trade_count', 'daily_high', 'daily_low',
            'opening_price', 'spread_absolute', 'spread_bps', 'mid_price',
            'updated_at'
        ]
        read_only_fields = ['updated_at']
    
    def get_spread_absolute(self, obj):
        spread = obj.spread
        return float(spread) if spread else None
    
    def get_spread_bps(self, obj):
        return obj.spread_bps
    
    def get_mid_price(self, obj):
        mid = obj.mid_price
        return float(mid) if mid else None


class OrderBookSnapshotRequestSerializer(serializers.Serializer):
    """Request serializer for order book snapshots"""
    instrument_id = serializers.IntegerField()
    depth = serializers.IntegerField(default=5, min_value=1, max_value=20)


class BulkOrderCreateSerializer(serializers.Serializer):
    """Serializer for creating multiple orders at once"""
    orders = serializers.ListField(
        child=OrderCreateSerializer(),
        max_length=50,
        min_length=1
    )


class FillSerializer(serializers.ModelSerializer):
    """Serializer for order fills"""
    order_id = serializers.UUIDField(source='order.order_id', read_only=True)
    trade_id = serializers.UUIDField(source='trade.trade_id', read_only=True)
    
    class Meta:
        model = Fill
        fields = [
            'id', 'fill_id', 'order_id', 'trade_id', 'quantity', 'price',
            'fill_timestamp', 'gross_amount', 'fees', 'net_amount',
            'is_aggressive', 'liquidity_flag', 'created_at'
        ]
        read_only_fields = ['fill_id', 'gross_amount', 'net_amount', 'created_at']
