# apps/trading_analytics/models.py
"""
SIMULATED Trading Analytics System
=================================
Tracks performance metrics and analytics for VIRTUAL trading.
All metrics are for PAPER TRADING simulation analysis.
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.market_data.models import BaseModel, Ticker, Sector
from apps.trading_simulation.models import SimulatedExchange, SimulatedInstrument
from apps.order_management.models import SimulatedOrder, SimulatedTrade
from decimal import Decimal
import uuid

User = get_user_model()


class PerformancePeriod(models.TextChoices):
    """Performance measurement periods"""
    DAILY = 'DAILY', 'Daily'
    WEEKLY = 'WEEKLY', 'Weekly'
    MONTHLY = 'MONTHLY', 'Monthly'
    QUARTERLY = 'QUARTERLY', 'Quarterly'
    YEARLY = 'YEARLY', 'Yearly'
    INCEPTION = 'INCEPTION', 'Since Inception'


class BenchmarkType(models.TextChoices):
    """Benchmark types for comparison"""
    SP500 = 'SP500', 'S&P 500'
    NASDAQ = 'NASDAQ', 'NASDAQ Composite'
    DOW = 'DOW', 'Dow Jones Industrial Average'
    RUSSELL2000 = 'RUSSELL2000', 'Russell 2000'
    CUSTOM = 'CUSTOM', 'Custom Benchmark'


class TradingPerformance(BaseModel):
    """
    SIMULATED Trading Performance - Virtual performance tracking
    Comprehensive performance metrics for paper trading
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trading_performance'
    )
    
    # Performance period
    period_type = models.CharField(
        max_length=20, choices=PerformancePeriod.choices
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Portfolio values
    starting_value = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Portfolio value at period start"
    )
    ending_value = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Portfolio value at period end"
    )
    peak_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Highest portfolio value during period"
    )
    trough_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Lowest portfolio value during period"
    )
    
    # Return metrics
    total_return = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Total return as decimal (0.10 = 10%)"
    )
    annualized_return = models.DecimalField(
        max_digits=12, decimal_places=8, null=True, blank=True,
        help_text="Annualized return"
    )
    
    # Risk metrics
    volatility = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Annualized volatility"
    )
    sharpe_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Sharpe ratio (excess return / volatility)"
    )
    max_drawdown = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Maximum drawdown during period"
    )
    max_drawdown_duration_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Duration of maximum drawdown in days"
    )
    
    # Trading activity
    total_trades = models.PositiveIntegerField(default=0)
    winning_trades = models.PositiveIntegerField(default=0)
    losing_trades = models.PositiveIntegerField(default=0)
    break_even_trades = models.PositiveIntegerField(default=0)
    
    # P&L breakdown
    realized_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    unrealized_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    total_fees = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00')
    )
    gross_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    net_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    
    # Win/Loss statistics
    average_win = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    average_loss = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    largest_win = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    largest_loss = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    
    # Additional metrics
    profit_factor = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Gross profit / gross loss"
    )
    calmar_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Annualized return / max drawdown"
    )
    sortino_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Return / downside deviation"
    )
    
    class Meta:
        db_table = 'simulation_trading_performance'
        unique_together = ['user', 'period_type', 'period_start']
        ordering = ['-period_end']
    
    def __str__(self):
        return f"Performance-{self.user.username}-{self.period_type}-{self.period_start.date()}"
    
    @property
    def win_rate(self):
        """Calculate win rate percentage"""
        if self.total_trades > 0:
            return float(self.winning_trades / self.total_trades * 100)
        return 0.0
    
    @property
    def average_return_per_trade(self):
        """Calculate average return per trade"""
        if self.total_trades > 0:
            return self.net_pnl / self.total_trades
        return Decimal('0.00')


class BenchmarkComparison(BaseModel):
    """
    SIMULATED Benchmark Comparison - Compare virtual performance vs benchmarks
    """
    performance = models.ForeignKey(
        TradingPerformance,
        on_delete=models.CASCADE,
        related_name='benchmark_comparisons'
    )
    
    benchmark_type = models.CharField(
        max_length=20, choices=BenchmarkType.choices
    )
    benchmark_ticker = models.ForeignKey(
        Ticker, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Ticker for custom benchmark"
    )
    
    # Benchmark performance
    benchmark_return = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Benchmark return for the same period"
    )
    benchmark_volatility = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True
    )
    
    # Relative performance
    excess_return = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Portfolio return - benchmark return"
    )
    tracking_error = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Standard deviation of excess returns"
    )
    information_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Excess return / tracking error"
    )
    
    # Risk-adjusted metrics
    beta = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Portfolio beta vs benchmark"
    )
    alpha = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Jensen's alpha"
    )
    correlation = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        help_text="Correlation with benchmark"
    )
    
    class Meta:
        db_table = 'simulation_benchmark_comparisons'
        unique_together = ['performance', 'benchmark_type']
    
    def __str__(self):
        return f"Benchmark-{self.performance.user.username}-{self.benchmark_type}"


class TradeAnalysis(BaseModel):
    """
    SIMULATED Trade Analysis - Individual trade performance analysis
    """
    trade = models.OneToOneField(
        SimulatedTrade,
        on_delete=models.CASCADE,
        related_name='analysis'
    )
    
    # Trade classification
    trade_type = models.CharField(
        max_length=20,
        choices=[
            ('SCALP', 'Scalping'),
            ('DAY_TRADE', 'Day Trade'),
            ('SWING', 'Swing Trade'),
            ('POSITION', 'Position Trade'),
            ('LONG_TERM', 'Long Term Hold'),
        ],
        null=True, blank=True
    )
    
    # Market conditions during trade
    market_trend = models.CharField(
        max_length=20,
        choices=[
            ('BULLISH', 'Bullish'),
            ('BEARISH', 'Bearish'),
            ('SIDEWAYS', 'Sideways'),
            ('VOLATILE', 'Volatile'),
        ],
        null=True, blank=True
    )
    
    # Price analysis
    entry_price = models.DecimalField(max_digits=15, decimal_places=6)
    exit_price = models.DecimalField(max_digits=15, decimal_places=6)
    price_change_percentage = models.DecimalField(
        max_digits=8, decimal_places=4,
        help_text="Price change during trade"
    )
    
    # Market context
    volume_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Trade volume vs average volume"
    )
    volatility_percentile = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Volatility percentile during trade"
    )
    
    # Performance metrics
    gross_pnl = models.DecimalField(max_digits=15, decimal_places=2)
    net_pnl = models.DecimalField(max_digits=15, decimal_places=2)
    pnl_percentage = models.DecimalField(
        max_digits=8, decimal_places=4,
        help_text="P&L as percentage of trade value"
    )
    
    # Timing analysis
    hold_duration_minutes = models.PositiveIntegerField(
        help_text="How long the position was held"
    )
    time_to_first_profit_minutes = models.PositiveIntegerField(
        null=True, blank=True
    )
    time_in_profit_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentage of time trade was profitable"
    )
    
    # Risk metrics
    max_adverse_excursion = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Maximum loss during trade"
    )
    max_favorable_excursion = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Maximum profit during trade"
    )
    
    class Meta:
        db_table = 'simulation_trade_analysis'
    
    def __str__(self):
        return f"Analysis-{self.trade.trade_id}"


class PortfolioAnalytics(BaseModel):
    """
    SIMULATED Portfolio Analytics - Advanced portfolio analysis
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='portfolio_analytics'
    )
    analysis_date = models.DateField()
    
    # Portfolio composition
    total_positions = models.PositiveIntegerField(default=0)
    long_positions = models.PositiveIntegerField(default=0)
    short_positions = models.PositiveIntegerField(default=0)
    cash_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    
    # Diversification metrics
    sector_diversification = models.JSONField(
        default=dict,
        help_text="Sector allocation percentages"
    )
    geographic_diversification = models.JSONField(
        default=dict,
        help_text="Geographic allocation percentages"
    )
    market_cap_distribution = models.JSONField(
        default=dict,
        help_text="Market cap distribution"
    )
    
    # Risk metrics
    portfolio_beta = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    portfolio_correlation_sp500 = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True
    )
    concentration_hhi = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Herfindahl-Hirschman Index for concentration"
    )
    
    # Performance attribution
    security_selection_return = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Return from security selection"
    )
    sector_allocation_return = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Return from sector allocation"
    )
    interaction_return = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True,
        help_text="Interaction effect"
    )
    
    # Turnover metrics
    portfolio_turnover = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Portfolio turnover rate"
    )
    average_holding_period_days = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    
    class Meta:
        db_table = 'simulation_portfolio_analytics'
        unique_together = ['user', 'analysis_date']
        ordering = ['-analysis_date']
    
    def __str__(self):
        return f"Analytics-{self.user.username}-{self.analysis_date}"


class StrategyPerformance(BaseModel):
    """
    SIMULATED Strategy Performance - Track performance by trading strategy
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='strategy_performance'
    )
    
    strategy_name = models.CharField(max_length=100)
    strategy_description = models.TextField(blank=True)
    
    # Strategy classification
    strategy_type = models.CharField(
        max_length=50,
        choices=[
            ('MOMENTUM', 'Momentum'),
            ('MEAN_REVERSION', 'Mean Reversion'),
            ('TREND_FOLLOWING', 'Trend Following'),
            ('ARBITRAGE', 'Arbitrage'),
            ('FUNDAMENTAL', 'Fundamental Analysis'),
            ('TECHNICAL', 'Technical Analysis'),
            ('QUANTITATIVE', 'Quantitative'),
            ('DISCRETIONARY', 'Discretionary'),
            ('CUSTOM', 'Custom Strategy'),
        ]
    )
    
    # Performance period
    inception_date = models.DateField()
    last_updated = models.DateField()
    
    # Performance metrics
    total_return = models.DecimalField(
        max_digits=12, decimal_places=8
    )
    annualized_return = models.DecimalField(
        max_digits=12, decimal_places=8, null=True, blank=True
    )
    volatility = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True
    )
    sharpe_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    max_drawdown = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True
    )
    
    # Trading statistics
    total_trades = models.PositiveIntegerField(default=0)
    winning_trades = models.PositiveIntegerField(default=0)
    average_trade_duration_hours = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    
    # Capital allocation
    allocated_capital = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Capital allocated to this strategy"
    )
    current_allocation_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Current percentage of total portfolio"
    )
    
    # Strategy status
    is_active = models.BooleanField(default=True)
    is_paper_only = models.BooleanField(
        default=True,
        help_text="Strategy is simulation-only"
    )
    
    class Meta:
        db_table = 'simulation_strategy_performance'
        unique_together = ['user', 'strategy_name']
        ordering = ['-total_return']
    
    def __str__(self):
        return f"Strategy-{self.user.username}-{self.strategy_name}"
    
    @property
    def win_rate(self):
        """Calculate strategy win rate"""
        if self.total_trades > 0:
            return float(self.winning_trades / self.total_trades * 100)
        return 0.0


class RiskReport(BaseModel):
    """
    SIMULATED Risk Report - Comprehensive risk analysis
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='risk_reports'
    )
    report_date = models.DateField()
    report_type = models.CharField(
        max_length=20,
        choices=[
            ('DAILY', 'Daily Risk Report'),
            ('WEEKLY', 'Weekly Risk Report'),
            ('MONTHLY', 'Monthly Risk Report'),
            ('AD_HOC', 'Ad Hoc Report'),
        ]
    )
    
    # Portfolio summary
    total_portfolio_value = models.DecimalField(
        max_digits=20, decimal_places=2
    )
    number_of_positions = models.PositiveIntegerField()
    
    # Risk limits status
    position_limit_breaches = models.PositiveIntegerField(default=0)
    concentration_limit_breaches = models.PositiveIntegerField(default=0)
    daily_loss_limit_breaches = models.PositiveIntegerField(default=0)
    
    # VaR calculations
    portfolio_var_1d_95 = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    portfolio_var_1d_99 = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    component_var = models.JSONField(
        default=dict,
        help_text="Component VaR by position"
    )
    
    # Stress test results
    stress_test_results = models.JSONField(
        default=dict,
        help_text="Results from various stress scenarios"
    )
    
    # Recommendations
    risk_recommendations = models.TextField(blank=True)
    action_items = models.JSONField(
        default=list,
        help_text="Specific action items to address risks"
    )
    
    # Report metadata
    calculation_time_seconds = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    data_quality_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Data quality score (0-100)"
    )
    
    class Meta:
        db_table = 'simulation_risk_reports'
        unique_together = ['user', 'report_date', 'report_type']
        ordering = ['-report_date']
    
    def __str__(self):
        return f"RiskReport-{self.user.username}-{self.report_date}-{self.report_type}"


class PerformanceAttribution(BaseModel):
    """
    SIMULATED Performance Attribution - Detailed return attribution analysis
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='performance_attribution'
    )
    
    attribution_date = models.DateField()
    attribution_period = models.CharField(
        max_length=20, choices=PerformancePeriod.choices
    )
    
    # Total portfolio return
    total_portfolio_return = models.DecimalField(
        max_digits=12, decimal_places=8
    )
    benchmark_return = models.DecimalField(
        max_digits=12, decimal_places=8
    )
    active_return = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Portfolio return - benchmark return"
    )
    
    # Attribution components
    asset_allocation_effect = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Return from asset allocation decisions"
    )
    security_selection_effect = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Return from security selection"
    )
    interaction_effect = models.DecimalField(
        max_digits=12, decimal_places=8,
        help_text="Interaction between allocation and selection"
    )
    
    # Sector attribution
    sector_attribution = models.JSONField(
        default=dict,
        help_text="Attribution by sector"
    )
    
    # Security-level attribution
    top_contributors = models.JSONField(
        default=list,
        help_text="Top contributing positions"
    )
    top_detractors = models.JSONField(
        default=list,
        help_text="Top detracting positions"
    )
    
    class Meta:
        db_table = 'simulation_performance_attribution'
        unique_together = ['user', 'attribution_date', 'attribution_period']
        ordering = ['-attribution_date']
    
    def __str__(self):
        return f"Attribution-{self.user.username}-{self.attribution_date}"
