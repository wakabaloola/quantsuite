# apps/risk_management/models.py
"""
SIMULATED Risk Management System
===============================
Manages VIRTUAL position limits, compliance, and risk monitoring.
All risk calculations are for PAPER TRADING simulation.
"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.market_data.models import BaseModel, Ticker, Sector
from apps.trading_simulation.models import (
    SimulatedExchange, SimulatedInstrument, SimulatedPosition, UserSimulationProfile
)
from decimal import Decimal

User = get_user_model()


class RiskLimitType(models.TextChoices):
    """Types of risk limits"""
    POSITION_SIZE = 'POSITION_SIZE', 'Position Size Limit'
    CONCENTRATION = 'CONCENTRATION', 'Concentration Limit'
    SECTOR_EXPOSURE = 'SECTOR_EXPOSURE', 'Sector Exposure Limit'
    DAILY_LOSS = 'DAILY_LOSS', 'Daily Loss Limit'
    PORTFOLIO_VAR = 'PORTFOLIO_VAR', 'Portfolio VaR Limit'
    LEVERAGE = 'LEVERAGE', 'Leverage Limit'
    ORDER_SIZE = 'ORDER_SIZE', 'Order Size Limit'


class RiskStatus(models.TextChoices):
    """Risk status levels"""
    NORMAL = 'NORMAL', 'Normal'
    WARNING = 'WARNING', 'Warning'
    BREACH = 'BREACH', 'Breach'
    CRITICAL = 'CRITICAL', 'Critical'


class PositionLimit(BaseModel):
    """
    SIMULATED Position Limits - Virtual trading limits
    Controls maximum positions users can hold in simulation
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='position_limits'
    )
    
    # Limit scope
    limit_type = models.CharField(
        max_length=20, choices=RiskLimitType.choices
    )
    
    # Instrument-specific limits
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Specific instrument (null for global limits)"
    )
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Sector-level limit"
    )
    exchange = models.ForeignKey(
        SimulatedExchange,
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Exchange-level limit"
    )
    
    # Limit values
    max_position_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Maximum position value in base currency"
    )
    max_position_quantity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum position quantity (shares/units)"
    )
    max_percentage_of_portfolio = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Maximum percentage of total portfolio value"
    )
    max_daily_loss = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Maximum daily loss allowed"
    )
    
    # Limit enforcement
    is_active = models.BooleanField(default=True)
    warning_threshold_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('80.00'),
        help_text="Percentage of limit at which to warn"
    )
    
    class Meta:
        db_table = 'simulation_position_limits'
        unique_together = [
            ['user', 'limit_type', 'instrument'],
            ['user', 'limit_type', 'sector'],
            ['user', 'limit_type', 'exchange'],
        ]
    
    def __str__(self):
        scope = (
            self.instrument.real_ticker.symbol if self.instrument
            else self.sector.name if self.sector
            else self.exchange.code if self.exchange
            else "GLOBAL"
        )
        return f"{self.user.username} - {self.limit_type} - {scope}"


class RiskAlert(BaseModel):
    """
    SIMULATED Risk Alerts - Virtual risk monitoring alerts
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='risk_alerts'
    )
    
    # Alert details
    alert_type = models.CharField(max_length=50)
    severity = models.CharField(
        max_length=20, choices=RiskStatus.choices
    )
    message = models.TextField()
    
    # Related objects
    position_limit = models.ForeignKey(
        PositionLimit,
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    position = models.ForeignKey(
        SimulatedPosition,
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    
    # Alert status
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Alert values
    current_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    limit_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    breach_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    
    class Meta:
        db_table = 'simulation_risk_alerts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Alert-{self.user.username}-{self.alert_type}-{self.severity}"


class ComplianceRule(BaseModel):
    """
    SIMULATED Compliance Rules - Virtual trading compliance
    """
    name = models.CharField(max_length=100)
    description = models.TextField()
    
    # Rule scope
    applies_to_all_users = models.BooleanField(default=True)
    specific_users = models.ManyToManyField(
        User, blank=True, related_name='compliance_rules'
    )
    
    # Rule parameters
    rule_type = models.CharField(
        max_length=50,
        choices=[
            ('ORDER_SIZE', 'Order Size Check'),
            ('POSITION_LIMIT', 'Position Limit Check'),
            ('WASH_SALE', 'Wash Sale Prevention'),
            ('PATTERN_DAY_TRADER', 'Pattern Day Trader Check'),
            ('CONCENTRATION', 'Concentration Check'),
            ('CUSTOM', 'Custom Rule'),
        ]
    )
    
    # Rule configuration
    parameters = models.JSONField(
        default=dict,
        help_text="Rule-specific parameters as JSON"
    )
    
    # Rule enforcement
    is_active = models.BooleanField(default=True)
    enforcement_action = models.CharField(
        max_length=20,
        choices=[
            ('WARN', 'Warning Only'),
            ('BLOCK', 'Block Order'),
            ('REQUIRE_APPROVAL', 'Require Approval'),
        ],
        default='WARN'
    )
    
    class Meta:
        db_table = 'simulation_compliance_rules'
    
    def __str__(self):
        return f"Rule: {self.name}"


class ComplianceCheck(BaseModel):
    """
    SIMULATED Compliance Check - Records compliance validations
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='compliance_checks'
    )
    rule = models.ForeignKey(
        ComplianceRule,
        on_delete=models.CASCADE,
        related_name='checks'
    )
    
    # Check context
    order_id = models.UUIDField(null=True, blank=True)
    check_timestamp = models.DateTimeField(auto_now_add=True)
    
    # Check result
    passed = models.BooleanField()
    violation_message = models.TextField(blank=True)
    
    # Check details
    checked_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    limit_value = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    
    class Meta:
        db_table = 'simulation_compliance_checks'
        ordering = ['-check_timestamp']
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"Check-{self.rule.name}-{status}"


class PortfolioRisk(BaseModel):
    """
    SIMULATED Portfolio Risk Metrics - Virtual portfolio risk analysis
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='portfolio_risks'
    )
    
    # Risk calculation date
    calculation_date = models.DateField()
    
    # Portfolio values
    total_portfolio_value = models.DecimalField(
        max_digits=20, decimal_places=2
    )
    cash_balance = models.DecimalField(
        max_digits=15, decimal_places=2
    )
    long_market_value = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    short_market_value = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    
    # Risk metrics
    portfolio_var_1d = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text="Portfolio VaR (1-day, 95% confidence)"
    )
    portfolio_beta = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Portfolio beta vs market"
    )
    portfolio_volatility = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        help_text="Portfolio volatility (annualized)"
    )
    
    # Concentration measures
    max_position_weight = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Largest position as % of portfolio"
    )
    top_5_concentration = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Top 5 positions as % of portfolio"
    )
    sector_concentration = models.JSONField(
        default=dict,
        help_text="Sector concentration percentages"
    )
    
    # Leverage metrics
    gross_leverage = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('1.0000'),
        help_text="Gross leverage ratio"
    )
    net_leverage = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal('1.0000'),
        help_text="Net leverage ratio"
    )
    
    # P&L metrics
    daily_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    mtd_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    ytd_pnl = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    
    # Risk status
    risk_status = models.CharField(
        max_length=20, choices=RiskStatus.choices, default=RiskStatus.NORMAL
    )
    active_alerts_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'simulation_portfolio_risks'
        unique_together = ['user', 'calculation_date']
        ordering = ['-calculation_date']
    
    def __str__(self):
        return f"Risk-{self.user.username}-{self.calculation_date}"
    
    @property
    def total_exposure(self):
        """Calculate total exposure (long + short absolute value)"""
        return self.long_market_value + abs(self.short_market_value)
    
    @property
    def net_exposure(self):
        """Calculate net exposure (long - short)"""
        return self.long_market_value - abs(self.short_market_value)


class MarginRequirement(BaseModel):
    """
    SIMULATED Margin Requirements - Virtual margin calculations
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='margin_requirements'
    )
    instrument = models.ForeignKey(
        SimulatedInstrument,
        on_delete=models.CASCADE,
        related_name='margin_requirements'
    )
    
    # Margin rates
    initial_margin_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal('0.5000'),
        help_text="Initial margin requirement as decimal (0.50 = 50%)"
    )
    maintenance_margin_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal('0.2500'),
        help_text="Maintenance margin requirement as decimal"
    )
    
    # Position-specific requirements
    current_position_value = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    required_initial_margin = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    required_maintenance_margin = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0.00')
    )
    
    # Special margin conditions
    is_hard_to_borrow = models.BooleanField(default=False)
    borrow_fee_rate = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('0.0000'),
        help_text="Annual borrow fee rate for short positions"
    )
    
    class Meta:
        db_table = 'simulation_margin_requirements'
        unique_together = ['user', 'instrument']
    
    def __str__(self):
        return f"Margin-{self.user.username}-{self.instrument.real_ticker.symbol}"
