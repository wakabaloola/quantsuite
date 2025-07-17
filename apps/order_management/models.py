# apps/order_management/models.py
"""
SIMULATED Order Management System
================================
Handles VIRTUAL orders, order matching, and trade execution.
All orders and trades are SIMULATED - no real money involved.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.market_data.models import BaseModel
from apps.trading_simulation.models import (
    SimulatedExchange, SimulatedInstrument, UserSimulationProfile
)
from decimal import Decimal
import uuid

User = get_user_model()


class OrderType(models.TextChoices):
    """Types of orders supported in simulation"""
    MARKET = 'MARKET', 'Market Order'
    LIMIT = 'LIMIT', 'Limit Order'  
    STOP = 'STOP', 'Stop Order'
    STOP_LIMIT = 'STOP_LIMIT', 'Stop Limit Order'
    IOC = 'IOC', 'Immediate or Cancel'
    FOK = 'FOK', 'Fill or Kill'
    ICEBERG = 'ICEBERG', 'Iceberg Order'


class OrderSide(models.TextChoices):
    """Order side - buy or sell"""
    BUY = 'BUY', 'Buy'
    SELL = 'SELL', 'Sell'


class OrderStatus(models.TextChoices):
    """Order status during lifecycle"""
    PENDING = 'PENDING', 'Pending'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged'
    PARTIALLY_FILLED = 'PARTIALLY_FILLED', 'Partially Filled'
    FILLED = 'FILLED', 'Filled'
    CANCELLED = 'CANCELLED', 'Cancelled'
    REJECTED = 'REJECTED', 'Rejected'
    EXPIRED = 'EXPIRED', 'Expired'


class TimeInForce(models.TextChoices):
    """Time in force options"""
    GTC = 'GTC', 'Good Till Cancelled'
    DAY = 'DAY', 'Day Order'
    IOC = 'IOC', 'Immediate or Cancel'
    FOK = 'FOK', 'Fill or Kill'


class SimulatedOrder(BaseModel):
    """
    SIMULATED Order - Virtual trading orders
    All orders are paper trades using real market data for pricing
    """
    # Order identification
    order_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client_order_id = models.CharField(max_length=50, blank=True)
    
    # User and trading context
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='simulated_orders'
    )
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    
    # Order details
    side = models.CharField(max_length=10, choices=OrderSide.choices)
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    quantity = models.PositiveIntegerField(help_text="Number of shares/units")
    
    # Pricing
    price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True,
        help_text="Limit price (null for market orders)"
    )
    stop_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True,
        help_text="Stop price for stop orders"
    )
    
    # Order behavior
    time_in_force = models.CharField(
        max_length=10, choices=TimeInForce.choices, default=TimeInForce.GTC
    )
    display_quantity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Quantity to display publicly (for iceberg orders)"
    )
    minimum_quantity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Minimum fill quantity"
    )
    
    # Order status and execution
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    filled_quantity = models.PositiveIntegerField(default=0)
    remaining_quantity = models.PositiveIntegerField(default=0)
    average_fill_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    
    # Timestamps
    order_timestamp = models.DateTimeField(auto_now_add=True)
    submission_timestamp = models.DateTimeField(null=True, blank=True)
    acknowledgment_timestamp = models.DateTimeField(null=True, blank=True)
    first_fill_timestamp = models.DateTimeField(null=True, blank=True)
    last_fill_timestamp = models.DateTimeField(null=True, blank=True)
    completion_timestamp = models.DateTimeField(null=True, blank=True)
    
    # Financial tracking
    total_fees = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00')
    )
    total_commission = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00')
    )
    
    # Risk and compliance
    risk_checked = models.BooleanField(default=False)
    compliance_checked = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    
    # Parent-child relationships for algorithmic orders
    parent_order = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE,
        related_name='child_orders'
    )
    
    class Meta:
        db_table = 'simulation_orders'
        ordering = ['-order_timestamp']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['instrument', 'side', 'status']),
            models.Index(fields=['order_timestamp']),
        ]
    
    def __str__(self):
        return f"SIM-Order {self.order_id} - {self.side} {self.quantity} {self.instrument.real_ticker.symbol}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate remaining quantity"""
        self.remaining_quantity = self.quantity - self.filled_quantity
        super().save(*args, **kwargs)
    
    @property
    def is_buy_order(self):
        return self.side == OrderSide.BUY
    
    @property
    def is_sell_order(self):
        return self.side == OrderSide.SELL
    
    @property
    def is_filled(self):
        return self.filled_quantity >= self.quantity
    
    @property
    def is_partially_filled(self):
        return 0 < self.filled_quantity < self.quantity
    
    @property
    def fill_ratio(self):
        """Return fill ratio as percentage"""
        if self.quantity > 0:
            return (self.filled_quantity / self.quantity) * 100
        return 0
    
    def calculate_notional_value(self):
        """Calculate total order value"""
        if self.price:
            return self.quantity * self.price
        return None


class SimulatedTrade(BaseModel):
    """
    SIMULATED Trade - Virtual trade executions
    Records when SIMULATED orders are matched and executed
    """
    # Trade identification  
    trade_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # Trading context
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='trades'
    )
    
    # Orders involved in trade
    buy_order = models.ForeignKey(
        SimulatedOrder,
        on_delete=models.CASCADE,
        related_name='buy_trades'
    )
    sell_order = models.ForeignKey(
        SimulatedOrder,
        on_delete=models.CASCADE,
        related_name='sell_trades'
    )
    
    # Trade details
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=6)
    trade_timestamp = models.DateTimeField(auto_now_add=True)
    
    # Financial details
    notional_value = models.DecimalField(max_digits=20, decimal_places=2)
    buyer_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    seller_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Trade characteristics
    is_aggressive = models.BooleanField(
        default=False,
        help_text="True if this trade removed liquidity (market order)"
    )
    
    class Meta:
        db_table = 'simulation_trades'
        ordering = ['-trade_timestamp']
        indexes = [
            models.Index(fields=['instrument', 'trade_timestamp']),
            models.Index(fields=['trade_timestamp']),
        ]
    
    def __str__(self):
        return f"SIM-Trade {self.trade_id} - {self.quantity}@{self.price}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate notional value"""
        self.notional_value = self.quantity * self.price
        super().save(*args, **kwargs)


class OrderBook(BaseModel):
    """
    SIMULATED Order Book - Virtual order book state
    Tracks current bid/ask levels for each instrument
    """
    instrument = models.OneToOneField(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='order_book'
    )
    
    # Best bid/offer
    best_bid_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    best_bid_quantity = models.PositiveIntegerField(default=0)
    best_ask_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    best_ask_quantity = models.PositiveIntegerField(default=0)
    
    # Market statistics
    last_trade_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    last_trade_quantity = models.PositiveIntegerField(default=0)
    last_trade_timestamp = models.DateTimeField(null=True, blank=True)
    
    # Session statistics
    daily_volume = models.BigIntegerField(default=0)
    daily_turnover = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal('0.00')
    )
    trade_count = models.PositiveIntegerField(default=0)
    
    # Price boundaries
    daily_high = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    daily_low = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    opening_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    
    class Meta:
        db_table = 'simulation_order_books'
    
    def __str__(self):
        return f"OrderBook-{self.instrument.real_ticker.symbol}"
    
    @property
    def spread(self):
        """Calculate bid-ask spread"""
        if self.best_bid_price and self.best_ask_price:
            return self.best_ask_price - self.best_bid_price
        return None
    
    @property
    def spread_bps(self):
        """Calculate spread in basis points"""
        if self.spread and self.last_trade_price:
            return float(self.spread / self.last_trade_price * 10000)
        return None
    
    @property
    def mid_price(self):
        """Calculate mid price"""
        if self.best_bid_price and self.best_ask_price:
            return (self.best_bid_price + self.best_ask_price) / 2
        return None


class OrderBookLevel(BaseModel):
    """
    SIMULATED Order Book Level - Individual price levels in order book
    """
    order_book = models.ForeignKey(
        OrderBook,
        on_delete=models.CASCADE,
        related_name='levels'
    )
    
    side = models.CharField(max_length=10, choices=OrderSide.choices)
    price = models.DecimalField(max_digits=15, decimal_places=6)
    quantity = models.PositiveIntegerField()
    order_count = models.PositiveIntegerField(default=1)
    
    class Meta:
        db_table = 'simulation_order_book_levels'
        unique_together = ['order_book', 'side', 'price']
        ordering = ['side', '-price']  # Bids descending, asks ascending
    
    def __str__(self):
        return f"{self.side} {self.quantity}@{self.price}"


class Fill(BaseModel):
    """
    SIMULATED Fill - Individual fill/execution record
    Records partial executions of orders
    """
    # Fill identification
    fill_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # Related order and trade
    order = models.ForeignKey(
        SimulatedOrder,
        on_delete=models.CASCADE,
        related_name='fills'
    )
    trade = models.ForeignKey(
        SimulatedTrade,
        on_delete=models.CASCADE,
        related_name='fills'
    )
    
    # Fill details
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=6)
    fill_timestamp = models.DateTimeField(auto_now_add=True)
    
    # Financial impact
    gross_amount = models.DecimalField(max_digits=20, decimal_places=2)
    fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Fill characteristics
    is_aggressive = models.BooleanField(default=False)
    liquidity_flag = models.CharField(
        max_length=10,
        choices=[
            ('MAKER', 'Liquidity Maker'),
            ('TAKER', 'Liquidity Taker'),
        ],
        default='TAKER'
    )
    
    class Meta:
        db_table = 'simulation_fills'
        ordering = ['-fill_timestamp']
    
    def __str__(self):
        return f"Fill {self.fill_id} - {self.quantity}@{self.price}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate amounts"""
        self.gross_amount = self.quantity * self.price
        self.net_amount = self.gross_amount - self.fees
        super().save(*args, **kwargs)


class MatchingEngine(BaseModel):
    """
    SIMULATED Matching Engine - Controls order matching logic
    """
    exchange = models.OneToOneField(
        SimulatedExchange,
        on_delete=models.CASCADE,
        related_name='matching_engine'
    )
    
    # Matching algorithm
    matching_algorithm = models.CharField(
        max_length=50,
        choices=[
            ('FIFO', 'First In First Out'),
            ('PRO_RATA', 'Pro Rata'),
            ('PRICE_TIME', 'Price Time Priority'),
            ('SIZE_PRIORITY', 'Size Priority'),
        ],
        default='PRICE_TIME'
    )
    
    # Engine status
    is_active = models.BooleanField(default=True)
    last_match_timestamp = models.DateTimeField(null=True, blank=True)
    
    # Performance metrics
    orders_processed = models.BigIntegerField(default=0)
    trades_executed = models.BigIntegerField(default=0)
    average_latency_ms = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000')
    )
    
    class Meta:
        db_table = 'simulation_matching_engines'
    
    def __str__(self):
        return f"MatchingEngine-{self.exchange.code}"


# Add these imports at the top
from django.contrib.postgres.fields import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator

# Add these new models to your existing models.py file

class AlgorithmType(models.TextChoices):
    """Types of algorithmic trading strategies"""
    TWAP = 'TWAP', 'Time-Weighted Average Price'
    VWAP = 'VWAP', 'Volume-Weighted Average Price'
    IMPLEMENTATION_SHORTFALL = 'IS', 'Implementation Shortfall'
    ICEBERG = 'ICEBERG', 'Iceberg Order'
    SNIPER = 'SNIPER', 'Sniper Algorithm'
    PARTICIPATION_RATE = 'POV', 'Percentage of Volume'
    CUSTOM = 'CUSTOM', 'Custom Strategy'


class AlgorithmStatus(models.TextChoices):
    """Algorithm execution status"""
    PENDING = 'PENDING', 'Pending'
    RUNNING = 'RUNNING', 'Running'
    PAUSED = 'PAUSED', 'Paused'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    FAILED = 'FAILED', 'Failed'


class AlgorithmicOrder(BaseModel):
    """
    SIMULATED Algorithmic Order - Complex trading strategies
    Parent order that spawns multiple child orders over time
    """
    # Order identification
    algo_order_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client_algo_id = models.CharField(max_length=50, blank=True)
    
    # User and trading context
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='algorithmic_orders'
    )
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE,
        related_name='algo_orders'
    )
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='algo_orders'
    )
    
    # Algorithm details
    algorithm_type = models.CharField(max_length=20, choices=AlgorithmType.choices)
    side = models.CharField(max_length=10, choices=OrderSide.choices)
    total_quantity = models.PositiveIntegerField(help_text="Total shares to trade")
    
    # Execution parameters
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    # Algorithm-specific parameters stored as JSON
    algorithm_parameters = models.JSONField(
        default=dict,
        help_text="Algorithm-specific configuration parameters"
    )
    
    # Execution constraints
    min_slice_size = models.PositiveIntegerField(
        default=100,
        help_text="Minimum size for child orders"
    )
    max_slice_size = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum size for child orders"
    )
    participation_rate = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(0.0001), MaxValueValidator(1.0)],
        help_text="Maximum participation rate (0.0001-1.0)"
    )
    
    # Price constraints
    limit_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True,
        help_text="Hard limit price"
    )
    price_tolerance = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Price tolerance as percentage"
    )
    
    # Execution status
    status = models.CharField(
        max_length=20, choices=AlgorithmStatus.choices, default=AlgorithmStatus.PENDING
    )
    executed_quantity = models.PositiveIntegerField(default=0)
    remaining_quantity = models.PositiveIntegerField(default=0)
    average_execution_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    
    # Performance metrics
    total_slippage = models.DecimalField(
        max_digits=15, decimal_places=6, default=Decimal('0.000000')
    )
    implementation_shortfall = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    
    # Timestamps
    created_timestamp = models.DateTimeField(auto_now_add=True)
    started_timestamp = models.DateTimeField(null=True, blank=True)
    completed_timestamp = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'simulation_algorithmic_orders'
        ordering = ['-created_timestamp']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['algorithm_type', 'status']),
            models.Index(fields=['start_time', 'end_time']),
        ]
    
    def __str__(self):
        return f"AlgoOrder {self.algo_order_id} - {self.algorithm_type} {self.total_quantity} {self.instrument.real_ticker.symbol}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate remaining quantity"""
        self.remaining_quantity = self.total_quantity - self.executed_quantity
        super().save(*args, **kwargs)
    
    @property
    def fill_ratio(self):
        """Return fill ratio as percentage"""
        if self.total_quantity > 0:
            return (self.executed_quantity / self.total_quantity) * 100
        return 0
    
    @property
    def duration_minutes(self):
        """Calculate algorithm duration in minutes"""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return 0

    def get_market_data_config(self):
        """Get market data configuration for this algorithm"""
        return {
            'real_time_pricing': True,
            'technical_indicators': self.algorithm_parameters.get('technical_indicators', ['rsi', 'macd']),
            'market_data_frequency': self.algorithm_parameters.get('market_data_frequency', '1min'),
            'price_precision': self.algorithm_parameters.get('price_precision', 6),
            'volume_analysis': self.algorithm_parameters.get('volume_analysis', True),
            'volatility_monitoring': self.algorithm_parameters.get('volatility_monitoring', True)
        }

    def should_use_enhanced_pricing(self):
        """Determine if algorithm should use enhanced market data pricing"""
        return self.algorithm_type in ['SNIPER', 'VWAP', 'PARTICIPATION_RATE']


class AlgorithmExecution(BaseModel):
    """
    Track individual execution steps of algorithmic orders
    """
    algo_order = models.ForeignKey(
        AlgorithmicOrder,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    
    # Execution details
    execution_step = models.PositiveIntegerField(help_text="Step number in algorithm")
    child_order = models.ForeignKey(
        SimulatedOrder,
        on_delete=models.CASCADE,
        related_name='algorithm_executions',
        null=True, blank=True
    )
    
    # Market conditions at execution
    market_price = models.DecimalField(max_digits=15, decimal_places=6)
    market_volume = models.PositiveIntegerField(default=0)
    spread_bps = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    
    # Execution results
    executed_quantity = models.PositiveIntegerField(default=0)
    execution_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    slippage_bps = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0.00')
    )
    
    # Timing
    scheduled_time = models.DateTimeField()
    execution_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'simulation_algorithm_executions'
        ordering = ['execution_step']
    
    def __str__(self):
        return f"Execution {self.execution_step} - {self.algo_order.algo_order_id}"


class CustomStrategy(BaseModel):
    """
    User-defined custom trading strategies
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='custom_strategies'
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Strategy definition
    strategy_code = models.TextField(
        help_text="Python code defining the strategy logic"
    )
    strategy_parameters = models.JSONField(
        default=dict,
        help_text="Configurable strategy parameters"
    )
    
    # Risk controls
    max_position_size = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('10000.00')
    )
    max_daily_loss = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('1000.00')
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_validated = models.BooleanField(default=False)
    
    # Performance tracking
    total_executions = models.PositiveIntegerField(default=0)
    total_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    win_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text="Win rate as percentage"
    )
    
    class Meta:
        db_table = 'simulation_custom_strategies'
        unique_together = ['user', 'name']
    
    def __str__(self):
        return f"Strategy: {self.name} by {self.user.username}"


class StrategyBacktest(BaseModel):
    """
    Backtesting results for trading strategies
    """
    strategy = models.ForeignKey(
        CustomStrategy,
        on_delete=models.CASCADE,
        related_name='backtests'
    )
    
    # Backtest parameters
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('100000.00')
    )
    instruments_tested = models.JSONField(
        default=list,
        help_text="List of instruments included in backtest"
    )
    
    # Results
    final_capital = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    total_return = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0.0000'),
        help_text="Total return as percentage"
    )
    annual_return = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0.0000')
    )
    sharpe_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    max_drawdown = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('0.0000')
    )
    
    # Trade statistics
    total_trades = models.PositiveIntegerField(default=0)
    winning_trades = models.PositiveIntegerField(default=0)
    losing_trades = models.PositiveIntegerField(default=0)
    average_trade_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    
    # Execution details
    backtest_results = models.JSONField(
        default=dict,
        help_text="Detailed backtest results and trade log"
    )
    
    class Meta:
        db_table = 'simulation_strategy_backtests'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"Backtest: {self.strategy.name} ({self.start_date} to {self.end_date})"
