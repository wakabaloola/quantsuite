# apps/risk_management/services.py
"""
SIMULATED Risk Management System
===============================
Manages VIRTUAL risk limits, compliance, and position monitoring.
All risk calculations are for PAPER TRADING simulation.
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q

from .models import (
    PositionLimit, SimulatedPosition, RiskAlert, ComplianceRule, 
    ComplianceCheck, PortfolioRisk, MarginRequirement, RiskStatus
)
from apps.order_management.models import SimulatedOrder
from apps.trading_simulation.models import UserSimulationProfile

logger = logging.getLogger(__name__)


class RiskManagementService:
    """
    SIMULATED Risk Management Service
    Validates virtual orders and monitors paper trading risk
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def validate_order(self, order: SimulatedOrder) -> Dict:
        """
        Validate order against all risk limits and compliance rules
        Returns: {'approved': bool, 'violations': List[str]}
        """
        try:
            violations = []
            
            # Basic order validation
            basic_violations = self._validate_basic_order_requirements(order)
            violations.extend(basic_violations)
            
            # Position limit checks
            position_violations = self._check_position_limits(order)
            violations.extend(position_violations)
            
            # Cash availability check
            cash_violations = self._check_cash_availability(order)
            violations.extend(cash_violations)
            
            # Compliance rule checks
            compliance_violations = self._check_compliance_rules(order)
            violations.extend(compliance_violations)
            
            # Concentration limit checks
            concentration_violations = self._check_concentration_limits(order)
            violations.extend(concentration_violations)
            
            # Log the validation result
            if violations:
                self.logger.warning(f"Order {order.order_id} failed validation: {violations}")
            else:
                self.logger.info(f"Order {order.order_id} passed all risk checks")
            
            return {
                'approved': len(violations) == 0,
                'violations': violations
            }
            
        except Exception as e:
            self.logger.error(f"Error validating order {order.order_id}: {e}")
            return {
                'approved': False,
                'violations': [f"Risk validation error: {str(e)}"]
            }
    
    def _validate_basic_order_requirements(self, order: SimulatedOrder) -> List[str]:
        """Validate basic order requirements"""
        violations = []
        
        try:
            # Check quantity
            if order.quantity <= 0:
                violations.append("Order quantity must be positive")
            
            # Check minimum order size
            min_size = order.exchange.minimum_order_size
            if order.quantity < min_size:
                violations.append(f"Order quantity below minimum: {min_size}")
            
            # Check maximum order size
            max_size = order.exchange.maximum_order_size
            if order.quantity > max_size:
                violations.append(f"Order quantity exceeds maximum: {max_size}")
            
            # Check price for limit orders
            if order.order_type == 'LIMIT' and not order.price:
                violations.append("Limit orders must have a price")
            
            if order.price and order.price <= 0:
                violations.append("Order price must be positive")
            
            # Check instrument is tradable
            if not order.instrument.is_tradable:
                violations.append("Instrument is not tradable")
            
            # Check exchange status
            if order.exchange.status != 'ACTIVE':
                violations.append("Exchange is not active")
                
        except Exception as e:
            violations.append(f"Basic validation error: {str(e)}")
        
        return violations
    
    def _check_position_limits(self, order: SimulatedOrder) -> List[str]:
        """Check order against position limits"""
        violations = []
        
        try:
            user = order.user
            instrument = order.instrument
            
            # Get current position
            try:
                current_position = SimulatedPosition.objects.get(
                    user=user, instrument=instrument
                )
                current_quantity = current_position.quantity
            except SimulatedPosition.DoesNotExist:
                current_quantity = Decimal('0')
            
            # Calculate new position after order
            order_quantity = Decimal(str(order.quantity))
            if order.side == 'SELL':
                order_quantity = -order_quantity
            
            new_position_quantity = current_quantity + order_quantity
            
            # Check instrument-specific position limits
            instrument_limits = PositionLimit.objects.filter(
                user=user,
                instrument=instrument,
                is_active=True
            )
            
            for limit in instrument_limits:
                if limit.max_position_quantity:
                    if abs(new_position_quantity) > limit.max_position_quantity:
                        violations.append(
                            f"Position quantity limit exceeded: {limit.max_position_quantity}"
                        )
                
                if limit.max_position_value and order.price:
                    new_position_value = abs(new_position_quantity * order.price)
                    if new_position_value > limit.max_position_value:
                        violations.append(
                            f"Position value limit exceeded: {limit.max_position_value}"
                        )
            
            # Check global position limits
            global_limits = PositionLimit.objects.filter(
                user=user,
                instrument__isnull=True,
                sector__isnull=True,
                exchange__isnull=True,
                is_active=True
            )
            
            for limit in global_limits:
                if limit.limit_type == 'POSITION_SIZE':
                    total_exposure = self._calculate_total_exposure(user)
                    order_value = order.quantity * (order.price or Decimal('100'))
                    
                    if limit.max_position_value:
                        if total_exposure + order_value > limit.max_position_value:
                            violations.append(
                                f"Global position limit exceeded: {limit.max_position_value}"
                            )
                            
        except Exception as e:
            violations.append(f"Position limit check error: {str(e)}")
        
        return violations
    
    def _check_cash_availability(self, order: SimulatedOrder) -> List[str]:
        """Check if user has sufficient virtual cash for the order"""
        violations = []
        
        try:
            if order.side == 'BUY':
                # Calculate required cash
                if order.price:
                    required_cash = order.quantity * order.price
                else:
                    # For market orders, estimate with current market price
                    current_price = order.instrument.get_current_simulated_price()
                    if current_price:
                        required_cash = order.quantity * current_price
                    else:
                        required_cash = order.quantity * Decimal('100')  # Default estimate
                
                # Add estimated fees
                fee_rate = order.exchange.trading_fee_percentage
                estimated_fees = required_cash * fee_rate
                total_required = required_cash + estimated_fees
                
                # Check available cash
                available_cash = order.user.simulation_profile.virtual_cash_balance
                
                if total_required > available_cash:
                    violations.append(
                        f"Insufficient cash: need {total_required}, have {available_cash}"
                    )
                    
        except Exception as e:
            violations.append(f"Cash availability check error: {str(e)}")
        
        return violations
    
    def _check_compliance_rules(self, order: SimulatedOrder) -> List[str]:
        """Check order against compliance rules"""
        violations = []
        
        try:
            user = order.user
            
            # Get applicable compliance rules
            rules = ComplianceRule.objects.filter(
                Q(applies_to_all_users=True) | Q(specific_users=user),
                is_active=True
            )
            
            for rule in rules:
                violation = self._check_individual_compliance_rule(order, rule)
                if violation:
                    violations.append(violation)
                    
                    # Record compliance check
                    ComplianceCheck.objects.create(
                        user=user,
                        rule=rule,
                        order_id=order.order_id,
                        passed=False,
                        violation_message=violation
                    )
                else:
                    # Record successful check
                    ComplianceCheck.objects.create(
                        user=user,
                        rule=rule,
                        order_id=order.order_id,
                        passed=True
                    )
                    
        except Exception as e:
            violations.append(f"Compliance check error: {str(e)}")
        
        return violations
    
    def _check_individual_compliance_rule(self, order: SimulatedOrder, 
                                        rule: ComplianceRule) -> Optional[str]:
        """Check a specific compliance rule"""
        try:
            if rule.rule_type == 'ORDER_SIZE':
                max_order_size = rule.parameters.get('max_order_size', 10000)
                if order.quantity > max_order_size:
                    return f"Order size exceeds limit: {max_order_size}"
            
            elif rule.rule_type == 'PATTERN_DAY_TRADER':
                # Check day trading limits
                if self._is_day_trade(order):
                    day_trades_count = self._count_day_trades(order.user)
                    max_day_trades = rule.parameters.get('max_day_trades', 3)
                    
                    if day_trades_count >= max_day_trades:
                        return f"Day trading limit exceeded: {max_day_trades}"
            
            elif rule.rule_type == 'WASH_SALE':
                # Check for wash sale violations
                if self._is_wash_sale(order):
                    return "Potential wash sale detected"
            
            return None
            
        except Exception as e:
            return f"Rule check error: {str(e)}"
    
    def _check_concentration_limits(self, order: SimulatedOrder) -> List[str]:
        """Check order against concentration limits"""
        violations = []
        
        try:
            user = order.user
            
            # Get sector concentration limits
            if order.instrument.real_ticker.sector:
                sector_limits = PositionLimit.objects.filter(
                    user=user,
                    sector=order.instrument.real_ticker.sector,
                    is_active=True
                )
                
                for limit in sector_limits:
                    if limit.max_percentage_of_portfolio:
                        current_sector_exposure = self._calculate_sector_exposure(
                            user, order.instrument.real_ticker.sector
                        )
                        total_portfolio_value = self._calculate_total_portfolio_value(user)
                        
                        if total_portfolio_value > 0:
                            current_percentage = (current_sector_exposure / total_portfolio_value) * 100
                            
                            if current_percentage > limit.max_percentage_of_portfolio:
                                violations.append(
                                    f"Sector concentration limit exceeded: {limit.max_percentage_of_portfolio}%"
                                )
                                
        except Exception as e:
            violations.append(f"Concentration check error: {str(e)}")
        
        return violations
    
    def _calculate_total_exposure(self, user) -> Decimal:
        """Calculate total position exposure for user"""
        try:
            positions = SimulatedPosition.objects.filter(user=user)
            total_exposure = Decimal('0')
            
            for position in positions:
                if position.current_price:
                    position_value = abs(position.quantity * position.current_price)
                    total_exposure += position_value
            
            return total_exposure
            
        except Exception as e:
            self.logger.error(f"Error calculating total exposure: {e}")
            return Decimal('0')
    
    def _calculate_sector_exposure(self, user, sector) -> Decimal:
        """Calculate exposure to a specific sector"""
        try:
            positions = SimulatedPosition.objects.filter(
                user=user,
                instrument__real_ticker__sector=sector
            )
            
            sector_exposure = Decimal('0')
            for position in positions:
                if position.current_price:
                    position_value = abs(position.quantity * position.current_price)
                    sector_exposure += position_value
            
            return sector_exposure
            
        except Exception as e:
            self.logger.error(f"Error calculating sector exposure: {e}")
            return Decimal('0')
    
    def _calculate_total_portfolio_value(self, user) -> Decimal:
        """Calculate total portfolio value"""
        try:
            profile = user.simulation_profile
            total_value = profile.virtual_cash_balance
            
            positions = SimulatedPosition.objects.filter(user=user)
            for position in positions:
                if position.current_price:
                    position_value = position.quantity * position.current_price
                    total_value += position_value
            
            return total_value
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio value: {e}")
            return Decimal('0')
    
    def _is_day_trade(self, order: SimulatedOrder) -> bool:
        """Check if order constitutes a day trade"""
        # Simplified day trade detection
        # In practice, this would be more sophisticated
        return True  # For simulation purposes
    
    def _count_day_trades(self, user) -> int:
        """Count day trades in the current period"""
        try:
            # Count trades in the last 5 business days
            start_date = timezone.now() - timedelta(days=7)
            
            from apps.order_management.models import SimulatedOrder
            day_trades = SimulatedOrder.objects.filter(
                user=user,
                order_timestamp__gte=start_date,
                status='FILLED'
            ).count()
            
            return day_trades // 2  # Rough approximation
            
        except Exception as e:
            self.logger.error(f"Error counting day trades: {e}")
            return 0
    
    def _is_wash_sale(self, order: SimulatedOrder) -> bool:
        """Check for wash sale violations"""
        # Simplified wash sale detection
        # In practice, this would check for sales and purchases of substantially identical securities
        return False
    
    def create_risk_alert(self, user, alert_type: str, severity: str, 
                         message: str, **kwargs) -> RiskAlert:
        """Create a risk alert for the user"""
        try:
            alert = RiskAlert.objects.create(
                user=user,
                alert_type=alert_type,
                severity=severity,
                message=message,
                **kwargs
            )
            
            self.logger.info(f"Created risk alert for {user.username}: {alert_type}")
            return alert
            
        except Exception as e:
            self.logger.error(f"Error creating risk alert: {e}")
            raise
    
    def update_portfolio_risk_metrics(self, user):
        """Update portfolio risk metrics for a user"""
        try:
            with transaction.atomic():
                # Calculate current portfolio metrics
                total_value = self._calculate_total_portfolio_value(user)
                cash_balance = user.simulation_profile.virtual_cash_balance
                
                # Calculate position metrics
                positions = SimulatedPosition.objects.filter(user=user)
                long_value = Decimal('0')
                short_value = Decimal('0')
                
                for position in positions:
                    if position.current_price:
                        position_value = abs(position.quantity * position.current_price)
                        if position.quantity > 0:
                            long_value += position_value
                        else:
                            short_value += position_value
                
                # Create or update portfolio risk record
                risk_record, created = PortfolioRisk.objects.update_or_create(
                    user=user,
                    calculation_date=timezone.now().date(),
                    defaults={
                        'total_portfolio_value': total_value,
                        'cash_balance': cash_balance,
                        'long_market_value': long_value,
                        'short_market_value': short_value,
                        'risk_status': self._determine_risk_status(user),
                    }
                )
                
                self.logger.info(f"Updated portfolio risk metrics for {user.username}")
                return risk_record
                
        except Exception as e:
            self.logger.error(f"Error updating portfolio risk metrics: {e}")
            raise
    
    def _determine_risk_status(self, user) -> str:
        """Determine overall risk status for user"""
        try:
            # Check for active alerts
            active_alerts = RiskAlert.objects.filter(
                user=user,
                is_resolved=False
            ).count()
            
            if active_alerts == 0:
                return RiskStatus.NORMAL
            elif active_alerts <= 2:
                return RiskStatus.WARNING
            else:
                return RiskStatus.CRITICAL
                
        except Exception as e:
            self.logger.error(f"Error determining risk status: {e}")
            return RiskStatus.NORMAL


    def validate_algorithmic_order(self, algo_order) -> Dict:
        """Validate an algorithmic order before execution"""
        try:
            violations = []
            
            # Check order size limits
            if algo_order.total_quantity > 10000:
                violations.append(f"Order size {algo_order.total_quantity} exceeds maximum 10,000")
            
            # Check algorithm duration
            duration_hours = (algo_order.end_time - algo_order.start_time).total_seconds() / 3600
            if duration_hours > 24:
                violations.append(f"Algorithm duration {duration_hours:.1f}h exceeds maximum 24h")
            
            # Check user cash balance for buy orders
            if algo_order.side == 'BUY':
                estimated_value = algo_order.total_quantity * (algo_order.limit_price or 100)
                if estimated_value > algo_order.user.simulation_profile.virtual_cash_balance:
                    violations.append("Insufficient cash balance for algorithmic order")
            
            return {
                'approved': len(violations) == 0,
                'violations': violations
            }
            
        except Exception as e:
            logger.error(f"Error validating algorithmic order: {e}")
            return {
                'approved': False,
                'violations': [f"Validation error: {str(e)}"]
            }


class ComplianceService:
    """
    Service for managing compliance rules and checks
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_default_compliance_rules(self, user) -> List[ComplianceRule]:
        """Create default compliance rules for a new user"""
        try:
            rules = []
            
            # Basic order size rule
            rule1 = ComplianceRule.objects.create(
                name="Basic Order Size Limit",
                description="Limit individual order size",
                rule_type="ORDER_SIZE",
                parameters={
                    "max_order_size": 10000,
                    "max_order_value": 100000
                },
                enforcement_action="BLOCK"
            )
            rule1.specific_users.add(user)
            rules.append(rule1)
            
            # Day trading rule
            rule2 = ComplianceRule.objects.create(
                name="Pattern Day Trading Rule",
                description="Enforce pattern day trading limits",
                rule_type="PATTERN_DAY_TRADER",
                parameters={
                    "max_day_trades": 3,
                    "period_days": 5
                },
                enforcement_action="WARN"
            )
            rule2.specific_users.add(user)
            rules.append(rule2)
            
            self.logger.info(f"Created default compliance rules for {user.username}")
            return rules
            
        except Exception as e:
            self.logger.error(f"Error creating default compliance rules: {e}")
            return []
    
    def get_compliance_summary(self, user) -> Dict:
        """Get compliance summary for user"""
        try:
            # Get recent compliance checks
            recent_checks = ComplianceCheck.objects.filter(
                user=user,
                check_timestamp__gte=timezone.now() - timedelta(days=30)
            )
            
            total_checks = recent_checks.count()
            passed_checks = recent_checks.filter(passed=True).count()
            failed_checks = total_checks - passed_checks
            
            # Get active rules
            active_rules = ComplianceRule.objects.filter(
                Q(applies_to_all_users=True) | Q(specific_users=user),
                is_active=True
            ).count()
            
            return {
                'active_rules': active_rules,
                'total_checks_30d': total_checks,
                'passed_checks_30d': passed_checks,
                'failed_checks_30d': failed_checks,
                'compliance_rate': (passed_checks / total_checks * 100) if total_checks > 0 else 100
            }
            
        except Exception as e:
            self.logger.error(f"Error getting compliance summary: {e}")
            return {}


class PositionLimitService:
    """
    Service for managing position limits
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_default_position_limits(self, user) -> List[PositionLimit]:
        """Create default position limits for a new user"""
        try:
            limits = []
            
            # Global position limit
            limit1 = PositionLimit.objects.create(
                user=user,
                limit_type="POSITION_SIZE",
                max_position_value=Decimal('50000'),
                max_percentage_of_portfolio=Decimal('20.00'),
                warning_threshold_percentage=Decimal('80.00')
            )
            limits.append(limit1)
            
            # Daily loss limit
            limit2 = PositionLimit.objects.create(
                user=user,
                limit_type="DAILY_LOSS",
                max_daily_loss=Decimal('5000'),
                warning_threshold_percentage=Decimal('80.00')
            )
            limits.append(limit2)
            
            self.logger.info(f"Created default position limits for {user.username}")
            return limits
            
        except Exception as e:
            self.logger.error(f"Error creating default position limits: {e}")
            return []
    
    def check_limit_breaches(self, user) -> List[Dict]:
        """Check for any limit breaches"""
        try:
            breaches = []
            limits = PositionLimit.objects.filter(user=user, is_active=True)
            
            for limit in limits:
                breach = self._check_individual_limit(limit)
                if breach:
                    breaches.append(breach)
            
            return breaches
            
        except Exception as e:
            self.logger.error(f"Error checking limit breaches: {e}")
            return []
    
    def _check_individual_limit(self, limit: PositionLimit) -> Optional[Dict]:
        """Check an individual position limit"""
        try:
            user = limit.user
            
            if limit.limit_type == "POSITION_SIZE":
                if limit.instrument:
                    # Instrument-specific limit
                    try:
                        position = SimulatedPosition.objects.get(
                            user=user, instrument=limit.instrument
                        )
                        current_value = abs(position.market_value)
                    except SimulatedPosition.DoesNotExist:
                        return None
                    
                    if limit.max_position_value and current_value > limit.max_position_value:
                        return {
                            'limit_type': limit.limit_type,
                            'limit_value': limit.max_position_value,
                            'current_value': current_value,
                            'breach_percentage': (current_value / limit.max_position_value - 1) * 100
                        }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking individual limit: {e}")
            return None


