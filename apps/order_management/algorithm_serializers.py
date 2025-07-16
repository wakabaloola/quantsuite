from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta

from .models import AlgorithmicOrder, AlgorithmExecution, CustomStrategy, StrategyBacktest
from apps.trading_simulation.serializers import SimulatedInstrumentSerializer, SimulatedExchangeSerializer


class AlgorithmicOrderSerializer(serializers.ModelSerializer):
    """Serializer for AlgorithmicOrder model"""
    
    instrument_display = SimulatedInstrumentSerializer(source='instrument', read_only=True)
    exchange_display = SimulatedExchangeSerializer(source='exchange', read_only=True)
    user_display = serializers.CharField(source='user.username', read_only=True)
    
    # Calculated fields
    fill_ratio = serializers.ReadOnlyField()
    remaining_quantity = serializers.ReadOnlyField()
    duration_minutes = serializers.ReadOnlyField()
    total_slippage = serializers.ReadOnlyField()
    
    # Status information
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    side_display = serializers.CharField(source='get_side_display', read_only=True)
    
    class Meta:
        model = AlgorithmicOrder
        fields = [
            'algo_order_id', 'user_display', 'exchange', 'exchange_display',
            'instrument', 'instrument_display', 'algorithm_type', 'side', 'side_display',
            'total_quantity', 'executed_quantity', 'remaining_quantity',
            'start_time', 'end_time', 'duration_minutes', 'status', 'status_display',
            'algorithm_parameters', 'limit_price', 'min_slice_size', 'max_slice_size',
            'participation_rate', 'fill_ratio', 'average_execution_price',
            'implementation_shortfall', 'total_slippage', 'started_timestamp',
            'completed_timestamp', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'algo_order_id', 'executed_quantity', 'status', 'fill_ratio',
            'remaining_quantity', 'duration_minutes', 'average_execution_price',
            'implementation_shortfall', 'total_slippage', 'started_timestamp',
            'completed_timestamp', 'created_at', 'updated_at'
        ]
    
    def validate(self, data):
        """Validate algorithm order data"""
        # Validate time range
        if data['end_time'] <= data['start_time']:
            raise serializers.ValidationError("End time must be after start time")
        
        # Validate algorithm duration
        duration = data['end_time'] - data['start_time']
        if duration.total_seconds() / 3600 > 24:
            raise serializers.ValidationError("Algorithm duration cannot exceed 24 hours")
        
        if duration.total_seconds() < 60:
            raise serializers.ValidationError("Algorithm duration must be at least 1 minute")
        
        # Validate quantity
        if data['total_quantity'] <= 0:
            raise serializers.ValidationError("Total quantity must be positive")
        
        if data['total_quantity'] > 100000:
            raise serializers.ValidationError("Total quantity cannot exceed 100,000 shares")
        
        # Validate algorithm parameters based on type
        algo_type = data.get('algorithm_type')
        params = data.get('algorithm_parameters', {})
        
        if algo_type == 'TWAP':
            slice_count = params.get('slice_count', 1)
            if slice_count < 1 or slice_count > 100:
                raise serializers.ValidationError("TWAP slice count must be between 1 and 100")
        
        elif algo_type == 'VWAP':
            volume_profile = params.get('volume_profile', 'STANDARD')
            if volume_profile not in ['STANDARD', 'AGGRESSIVE', 'PASSIVE']:
                raise serializers.ValidationError("Invalid VWAP volume profile")
        
        elif algo_type == 'ICEBERG':
            display_size = params.get('display_size', 100)
            if display_size <= 0 or display_size >= data['total_quantity']:
                raise serializers.ValidationError("Iceberg display size must be positive and less than total quantity")
        
        elif algo_type == 'SNIPER':
            patience_seconds = params.get('patience_seconds', 300)
            if patience_seconds < 10 or patience_seconds > 3600:
                raise serializers.ValidationError("Sniper patience must be between 10 seconds and 1 hour")
        
        return data
    
    def create(self, validated_data):
        """Create new algorithmic order"""
        # Set default start time if not provided
        if 'start_time' not in validated_data:
            validated_data['start_time'] = timezone.now()
        
        # Set default end time if not provided
        if 'end_time' not in validated_data:
            validated_data['end_time'] = validated_data['start_time'] + timedelta(hours=1)
        
        # Set default algorithm parameters if not provided
        if 'algorithm_parameters' not in validated_data:
            algo_type = validated_data['algorithm_type']
            if algo_type == 'TWAP':
                validated_data['algorithm_parameters'] = {'slice_count': 10}
            elif algo_type == 'VWAP':
                validated_data['algorithm_parameters'] = {'volume_profile': 'STANDARD'}
            elif algo_type == 'ICEBERG':
                validated_data['algorithm_parameters'] = {'display_size': 100}
            elif algo_type == 'SNIPER':
                validated_data['algorithm_parameters'] = {'max_spread_bps': 20, 'min_volume': 1000}
        
        return super().create(validated_data)


class AlgorithmExecutionSerializer(serializers.ModelSerializer):
    """Serializer for AlgorithmExecution model"""
    
    algo_order_display = serializers.CharField(source='algo_order.algo_order_id', read_only=True)
    algorithm_type = serializers.CharField(source='algo_order.algorithm_type', read_only=True)
    instrument_symbol = serializers.CharField(source='algo_order.instrument.real_ticker.symbol', read_only=True)
    
    # Calculated fields
    slippage_bps = serializers.ReadOnlyField()
    execution_delay = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    
    class Meta:
        model = AlgorithmExecution
        fields = [
            'id', 'algo_order', 'algo_order_display', 'algorithm_type', 'instrument_symbol',
            'execution_step', 'scheduled_time', 'execution_time', 'execution_delay',
            'market_price', 'market_volume', 'spread_bps', 'executed_quantity',
            'execution_price', 'slippage_bps', 'child_order', 'is_completed',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'execution_time', 'market_price', 'market_volume',
            'spread_bps', 'executed_quantity', 'execution_price',
            'slippage_bps', 'child_order', 'created_at', 'updated_at'
        ]
    
    def get_execution_delay(self, obj):
        """Calculate delay between scheduled and actual execution"""
        if obj.execution_time and obj.scheduled_time:
            delay = obj.execution_time - obj.scheduled_time
            return delay.total_seconds()
        return None
    
    def get_is_completed(self, obj):
        """Check if execution is completed"""
        return obj.execution_time is not None and obj.executed_quantity > 0


class CustomStrategySerializer(serializers.ModelSerializer):
    """Serializer for CustomStrategy model"""
    
    user_display = serializers.CharField(source='user.username', read_only=True)
    backtest_count = serializers.SerializerMethodField()
    latest_backtest = serializers.SerializerMethodField()
    
    # Performance metrics
    total_pnl = serializers.ReadOnlyField()
    win_rate = serializers.ReadOnlyField()
    total_executions = serializers.ReadOnlyField()
    
    class Meta:
        model = CustomStrategy
        fields = [
            'id', 'user_display', 'name', 'description', 'strategy_code',
            'strategy_parameters', 'is_active', 'is_validated', 'validation_error',
            'max_position_size', 'max_daily_loss', 'total_executions',
            'total_pnl', 'win_rate', 'backtest_count', 'latest_backtest',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_validated', 'validation_error', 'total_executions',
            'total_pnl', 'win_rate', 'created_at', 'updated_at'
        ]
    
    def get_backtest_count(self, obj):
        """Get number of backtests for this strategy"""
        return obj.backtests.count()
    
    def get_latest_backtest(self, obj):
        """Get latest backtest summary"""
        latest = obj.backtests.order_by('-created_at').first()
        if latest:
            return {
                'id': latest.id,
                'end_date': latest.end_date,
                'total_return': float(latest.total_return) if latest.total_return else 0,
                'sharpe_ratio': float(latest.sharpe_ratio) if latest.sharpe_ratio else 0,
                'max_drawdown': float(latest.max_drawdown) if latest.max_drawdown else 0,
                'total_trades': latest.total_trades
            }
        return None
    
    def validate_strategy_code(self, value):
        """Validate strategy code syntax"""
        try:
            compile(value, '<strategy>', 'exec')
        except SyntaxError as e:
            raise serializers.ValidationError(f"Syntax error: {str(e)}")
        except Exception as e:
            raise serializers.ValidationError(f"Code validation error: {str(e)}")
        
        # Check for required function
        if 'def execute_strategy(' not in value:
            raise serializers.ValidationError("Strategy must contain an 'execute_strategy' function")
        
        return value
    
    def validate_strategy_parameters(self, value):
        """Validate strategy parameters"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Strategy parameters must be a dictionary")
        
        # Check for dangerous operations
        dangerous_imports = ['os', 'sys', 'subprocess', 'eval', 'exec']
        code = self.initial_data.get('strategy_code', '')
        
        for dangerous in dangerous_imports:
            if dangerous in code:
                raise serializers.ValidationError(f"Dangerous operation '{dangerous}' not allowed in strategy code")
        
        return value


class StrategyBacktestSerializer(serializers.ModelSerializer):
    """Serializer for StrategyBacktest model"""
    
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    duration_days = serializers.SerializerMethodField()
    win_rate_percentage = serializers.SerializerMethodField()
    profit_factor = serializers.SerializerMethodField()
    
    class Meta:
        model = StrategyBacktest
        fields = [
            'id', 'strategy', 'strategy_name', 'start_date', 'end_date',
            'duration_days', 'initial_capital', 'final_capital', 'total_return',
            'annual_return', 'sharpe_ratio', 'max_drawdown', 'volatility',
            'total_trades', 'winning_trades', 'losing_trades', 'win_rate_percentage',
            'average_trade_pnl', 'profit_factor', 'instruments_tested',
            'backtest_results', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'duration_days', 'win_rate_percentage', 'profit_factor',
            'created_at', 'updated_at'
        ]
    
    def get_duration_days(self, obj):
        """Calculate backtest duration in days"""
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days
        return None
    
    def get_win_rate_percentage(self, obj):
        """Calculate win rate as percentage"""
        if obj.total_trades > 0:
            return round((obj.winning_trades / obj.total_trades) * 100, 2)
        return 0
    
    def get_profit_factor(self, obj):
        """Calculate profit factor"""
        if obj.losing_trades > 0 and obj.winning_trades > 0:
            # Simplified calculation - in practice would need actual P&L data
            avg_win = float(obj.average_trade_pnl) if obj.average_trade_pnl and obj.average_trade_pnl > 0 else 0
            avg_loss = float(obj.average_trade_pnl) if obj.average_trade_pnl and obj.average_trade_pnl < 0 else -100
            
            if avg_loss != 0:
                return round(abs(avg_win / avg_loss), 2)
        return 0


class AlgorithmDashboardSerializer(serializers.Serializer):
    """Serializer for algorithm dashboard data"""
    
    recent_algorithms = AlgorithmicOrderSerializer(many=True, read_only=True)
    running_algorithms = AlgorithmicOrderSerializer(many=True, read_only=True)
    statistics = serializers.DictField(read_only=True)


class AlgorithmPerformanceSerializer(serializers.Serializer):
    """Serializer for algorithm performance metrics"""
    
    algo_order_id = serializers.UUIDField(read_only=True)
    algorithm_type = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    fill_ratio = serializers.FloatField(read_only=True)
    average_execution_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    implementation_shortfall = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)
    total_slippage = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)
    execution_count = serializers.IntegerField(read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)
    started_timestamp = serializers.DateTimeField(read_only=True)
    completed_timestamp = serializers.DateTimeField(read_only=True)
    instrument = serializers.DictField(read_only=True)
    side = serializers.CharField(read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)
    executed_quantity = serializers.IntegerField(read_only=True)
    remaining_quantity = serializers.IntegerField(read_only=True)
    limit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
