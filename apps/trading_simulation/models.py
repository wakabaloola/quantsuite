# apps/trading_simulation/models.py
"""
SIMULATED Trading Exchange Models
=================================
This handles VIRTUAL trading environments using REAL market data for pricing.
All trading here is PAPER TRADING - no real money involved.
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.market_data.models import BaseModel, Ticker, Exchange
from decimal import Decimal
import uuid
from enum import Enum

User = get_user_model()


class SimulationStatus(models.TextChoices):
    """Status choices for simulation components"""
    ACTIVE = 'ACTIVE', 'Active'
    PAUSED = 'PAUSED', 'Paused'  
    STOPPED = 'STOPPED', 'Stopped'
    MAINTENANCE = 'MAINTENANCE', 'Maintenance'


class TradingSessionType(models.TextChoices):
    """Types of simulated trading sessions"""
    CONTINUOUS = 'CONTINUOUS', 'Continuous Trading'
    AUCTION = 'AUCTION', 'Auction Based'
    CALL_MARKET = 'CALL_MARKET', 'Call Market'


class SimulatedExchange(BaseModel):
    """
    SIMULATED Trading Exchange - Virtual exchange environment
    Uses REAL market data but all trading is SIMULATED
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    
    # Links to real exchange for market data
    real_exchange = models.ForeignKey(
        Exchange, 
        on_delete=models.CASCADE,
        help_text="Real exchange to source market data from"
    )
    
    # Simulation parameters
    status = models.CharField(
        max_length=20, 
        choices=SimulationStatus.choices, 
        default=SimulationStatus.ACTIVE
    )
    
    # Trading parameters  
    trading_fee_percentage = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('0.0010'),
        help_text="Simulated trading fee as percentage (0.0010 = 0.1%)"
    )
    minimum_order_size = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('1.00')
    )
    maximum_order_size = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('1000000.00')
    )
    
    # Latency simulation
    simulated_latency_ms = models.IntegerField(
        default=50,
        help_text="Simulated order processing latency in milliseconds"
    )
    
    # Market maker simulation
    enable_market_making = models.BooleanField(
        default=True,
        help_text="Enable simulated market makers for liquidity"
    )
    
    class Meta:
        db_table = 'simulation_exchanges'
        
    def __str__(self):
        return f"SIM-{self.name} ({self.code})"


class SimulatedInstrument(BaseModel):
    """
    SIMULATED Tradable Instrument - Virtual instruments based on real tickers
    Uses REAL market data for pricing, but trading is SIMULATED
    """
    # Link to real ticker for market data
    real_ticker = models.ForeignKey(
        Ticker,
        on_delete=models.CASCADE,
        help_text="Real ticker to source market data from"
    )

    # Simulation exchange
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE,
        related_name='instruments'
    )

    # Simulation-specific attributes
    is_tradable = models.BooleanField(default=True)

    # Price manipulation for simulation scenarios
    price_multiplier = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('1.0000'),
        help_text="Multiply real price by this factor for simulation scenarios"
    )

    # Trading constraints
    min_price_increment = models.DecimalField(
        max_digits=10, decimal_places=6, default=Decimal('0.01'),
        help_text="Minimum price increment (tick size)"
    )
    max_daily_volume = models.BigIntegerField(
        null=True, blank=True,
        help_text="Maximum shares that can be traded per day"
    )

    # Volatility simulation
    volatility_multiplier = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('1.0000'),
        help_text="Multiply real volatility for simulation scenarios"
    )

    class Meta:
        db_table = 'simulation_instruments'
        unique_together = ['real_ticker', 'exchange']

    def __str__(self):
        return f"SIM-{self.real_ticker.symbol} on {self.exchange.code}"

    def get_current_simulated_price(self):
        """Get current price with simulation adjustments"""
        # This would fetch latest real market data and apply simulation adjustments
        latest_data = self.real_ticker.market_data.first()
        if latest_data:
            return latest_data.close * self.price_multiplier
        return None


class SimulatedPosition(BaseModel):
    """
    SIMULATED Position - Virtual portfolio positions
    Tracks user's virtual holdings in the simulation
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='simulated_positions'
    )
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='positions'
    )

    # Position details
    quantity = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Current position size (positive=long, negative=short)"
    )
    average_cost = models.DecimalField(
        max_digits=15, decimal_places=6,
        help_text="Average cost per share/unit"
    )
    total_cost = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total cost basis of position"
    )

    # Current market values
    current_price = models.DecimalField(
        max_digits=15, decimal_places=6, null=True, blank=True
    )
    market_value = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    unrealized_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )

    # Realized P&L tracking
    realized_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    total_fees_paid = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00')
    )

    # Position timestamps
    first_trade_timestamp = models.DateTimeField(auto_now_add=True)
    last_trade_timestamp = models.DateTimeField(auto_now=True)

    # Risk metrics
    daily_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    position_var = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Position Value at Risk (1-day, 95%)"
    )

    class Meta:
        db_table = 'simulation_positions'
        unique_together = ['user', 'instrument']
        indexes = [
            models.Index(fields=['user', 'quantity']),
            models.Index(fields=['instrument', 'market_value']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.quantity} {self.instrument.real_ticker.symbol}"

    @property
    def is_long(self):
        return self.quantity > 0

    @property
    def is_short(self):
        return self.quantity < 0

    @property
    def abs_quantity(self):
        return abs(self.quantity)

    def calculate_unrealized_pnl(self):
        """Calculate current unrealized P&L"""
        if self.current_price and self.quantity != 0:
            current_value = self.quantity * self.current_price
            return current_value - self.total_cost
        return Decimal('0.00')

    def update_market_values(self, current_price):
        """Update position with current market price"""
        self.current_price = current_price
        self.market_value = self.quantity * current_price
        self.unrealized_pnl = self.calculate_unrealized_pnl()
        self.save()


class TradingSession(BaseModel):
    """
    SIMULATED Trading Session - Virtual trading periods
    """
    exchange = models.ForeignKey(
        SimulatedExchange, 
        on_delete=models.CASCADE,
        related_name='trading_sessions'
    )
    
    session_type = models.CharField(
        max_length=20,
        choices=TradingSessionType.choices,
        default=TradingSessionType.CONTINUOUS
    )
    
    # Session timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    # Session parameters
    status = models.CharField(
        max_length=20,
        choices=SimulationStatus.choices,
        default=SimulationStatus.ACTIVE
    )
    
    # Trading rules for this session
    allow_short_selling = models.BooleanField(default=True)
    allow_margin_trading = models.BooleanField(default=False)
    circuit_breaker_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('10.00'),
        help_text="Price movement % that triggers circuit breaker"
    )
    
    class Meta:
        db_table = 'simulation_trading_sessions'
        ordering = ['-start_time']
        
    def __str__(self):
        return f"{self.exchange.code} - {self.session_type} - {self.start_time.date()}"


class MarketMaker(BaseModel):
    """
    SIMULATED Market Maker - Provides artificial liquidity
    """
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE, 
        related_name='market_makers'
    )
    
    name = models.CharField(max_length=100)
    algorithm_type = models.CharField(
        max_length=50,
        choices=[
            ('BASIC', 'Basic Spread'),
            ('ADAPTIVE', 'Adaptive Spread'),
            ('RANDOM_WALK', 'Random Walk'),
            ('TREND_FOLLOWING', 'Trend Following'),
        ],
        default='BASIC'
    )
    
    # Market making parameters
    default_spread_bps = models.IntegerField(
        default=10,
        help_text="Default bid-ask spread in basis points"
    )
    max_position_size = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('100000.00')
    )
    quote_size = models.IntegerField(
        default=100,
        help_text="Default quantity for quotes"
    )
    
    # Activity controls
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'simulation_market_makers'
        
    def __str__(self):
        return f"MM-{self.name} on {self.exchange.code}"


class SimulationScenario(BaseModel):
    """
    SIMULATED Market Scenario - Predefined market conditions for testing
    """
    name = models.CharField(max_length=100)
    description = models.TextField()
    
    # Scenario parameters
    scenario_type = models.CharField(
        max_length=50,
        choices=[
            ('NORMAL', 'Normal Market'),
            ('VOLATILE', 'High Volatility'),
            ('TRENDING_UP', 'Bull Market'),
            ('TRENDING_DOWN', 'Bear Market'),
            ('CRASH', 'Market Crash'),
            ('RECOVERY', 'Market Recovery'),
            ('LOW_LIQUIDITY', 'Low Liquidity'),
            ('CUSTOM', 'Custom Scenario'),
        ],
        default='NORMAL'
    )
    
    # Global parameters that affect all instruments
    volatility_factor = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('1.0000')
    )
    volume_factor = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('1.0000')
    )
    liquidity_factor = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('1.0000')
    )
    
    # Trend parameters
    daily_drift_percentage = models.DecimalField(
        max_digits=8, decimal_places=6, default=Decimal('0.000000'),
        help_text="Daily price drift as percentage"
    )
    
    class Meta:
        db_table = 'simulation_scenarios'
        
    def __str__(self):
        return f"Scenario: {self.name}"


class UserSimulationProfile(BaseModel):
    """
    User profile for SIMULATED trading
    Tracks virtual cash, positions, and preferences
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='simulation_profile'
    )
    
    # Virtual account balance
    virtual_cash_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('100000.00'),
        help_text="Virtual cash for paper trading"
    )
    initial_virtual_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('100000.00')
    )
    
    # Trading preferences
    default_order_size = models.IntegerField(default=100)
    risk_tolerance = models.CharField(
        max_length=20,
        choices=[
            ('CONSERVATIVE', 'Conservative'),
            ('MODERATE', 'Moderate'),
            ('AGGRESSIVE', 'Aggressive'),
        ],
        default='MODERATE'
    )
    
    # Experience level affects available features
    experience_level = models.CharField(
        max_length=20,
        choices=[
            ('BEGINNER', 'Beginner'),
            ('INTERMEDIATE', 'Intermediate'),
            ('ADVANCED', 'Advanced'),
            ('PROFESSIONAL', 'Professional'),
        ],
        default='BEGINNER'
    )
    
    # Simulation settings
    enable_margin_trading = models.BooleanField(default=False)
    enable_options_trading = models.BooleanField(default=False)
    enable_short_selling = models.BooleanField(default=False)
    
    # Performance tracking
    total_trades_executed = models.IntegerField(default=0)
    profitable_trades = models.IntegerField(default=0)
    current_portfolio_value = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('100000.00')
    )
    
    class Meta:
        db_table = 'simulation_user_profiles'
        
    def __str__(self):
        return f"SimProfile-{self.user.username}"
    
    def calculate_total_return_percentage(self):
        """Calculate total return since start"""
        if self.initial_virtual_balance > 0:
            return float(
                (self.current_portfolio_value - self.initial_virtual_balance) 
                / self.initial_virtual_balance * 100
            )
        return 0.0
    
    def get_win_rate(self):
        """Calculate win rate percentage"""
        if self.total_trades_executed > 0:
            return float(self.profitable_trades / self.total_trades_executed * 100)
        return 0.0

