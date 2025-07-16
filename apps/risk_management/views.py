# apps/risk_management/views.py
"""
SIMULATED Risk Management API Views
==================================
RESTful endpoints for VIRTUAL risk management and compliance.
All endpoints handle PAPER TRADING risk controls.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from decimal import Decimal

from .models import (
    PositionLimit, RiskAlert, ComplianceRule,
    ComplianceCheck, PortfolioRisk, MarginRequirement
)
from .serializers import (
        PositionLimitSerializer, RiskAlertSerializer, PortfolioRiskSerializer
)
from .services import RiskManagementService, ComplianceService, PositionLimitService

from apps.trading_simulation.models import SimulatedPosition
from apps.trading_simulation.serializers import SimulatedPositionSerializer
from apps.trading_analytics.serializers import PortfolioSummarySerializer


class PositionLimitViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Position Limits Management
    Manage virtual trading position limits
    """
    serializer_class = PositionLimitSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['limit_type', 'is_active', 'instrument', 'sector']
    
    def get_queryset(self):
        # Users can only manage their own limits
        return PositionLimit.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def create_defaults(self, request):
        """Create default position limits for the user"""
        try:
            service = PositionLimitService()
            limits = service.create_default_position_limits(request.user)
            
            serializer = self.get_serializer(limits, many=True)
            return Response({
                'message': f'Created {len(limits)} default position limits',
                'limits': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def check_breaches(self, request):
        """Check for current limit breaches"""
        try:
            service = PositionLimitService()
            breaches = service.check_limit_breaches(request.user)
            
            return Response({
                'user': request.user.username,
                'breach_count': len(breaches),
                'breaches': breaches,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def utilization(self, request):
        """Get current limit utilization percentages"""
        try:
            limits = self.get_queryset().filter(is_active=True)
            utilization_data = []
            
            for limit in limits:
                # Calculate current utilization based on limit type
                current_value = self._get_current_limit_value(limit)
                limit_value = self._get_limit_threshold(limit)
                
                if limit_value and limit_value > 0:
                    utilization_pct = (current_value / limit_value) * 100
                else:
                    utilization_pct = 0
                
                utilization_data.append({
                    'limit_id': limit.id,
                    'limit_type': limit.limit_type,
                    'scope': self._get_limit_scope(limit),
                    'current_value': float(current_value),
                    'limit_value': float(limit_value) if limit_value else None,
                    'utilization_percentage': min(float(utilization_pct), 100),
                    'warning_threshold': float(limit.warning_threshold_percentage),
                    'status': 'BREACH' if utilization_pct > 100 else 'WARNING' if utilization_pct > limit.warning_threshold_percentage else 'NORMAL'
                })
            
            return Response({
                'utilization': utilization_data,
                'total_limits': len(utilization_data)
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_current_limit_value(self, limit):
        """Get current value for limit calculation"""
        user = limit.user
        
        if limit.limit_type == 'POSITION_SIZE':
            if limit.instrument:
                try:
                    position = SimulatedPosition.objects.get(user=user, instrument=limit.instrument)
                    return abs(position.market_value)
                except SimulatedPosition.DoesNotExist:
                    return Decimal('0')
            else:
                # Global position limit
                total_exposure = SimulatedPosition.objects.filter(user=user).aggregate(
                    total=Sum('market_value')
                )['total'] or Decimal('0')
                return abs(total_exposure)
        
        return Decimal('0')
    
    def _get_limit_threshold(self, limit):
        """Get the limit threshold value"""
        if limit.max_position_value:
            return limit.max_position_value
        elif limit.max_position_quantity:
            return Decimal(str(limit.max_position_quantity))
        return None
    
    def _get_limit_scope(self, limit):
        """Get human-readable scope description"""
        if limit.instrument:
            return f"Instrument: {limit.instrument.real_ticker.symbol}"
        elif limit.sector:
            return f"Sector: {limit.sector.name}"
        elif limit.exchange:
            return f"Exchange: {limit.exchange.code}"
        else:
            return "Global"


class SimulatedPositionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    SIMULATED Positions View
    View virtual portfolio positions
    """
    serializer_class = SimulatedPositionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['instrument__exchange']
    
    def get_queryset(self):
        # Users can only see their own positions
        return SimulatedPosition.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get portfolio positions summary"""
        try:
            positions = self.get_queryset()
            
            # Update all positions with current market prices
            self._update_position_prices(positions)
            
            # Calculate summary metrics
            total_positions = positions.count()
            long_positions = positions.filter(quantity__gt=0)
            short_positions = positions.filter(quantity__lt=0)
            
            # Portfolio values
            total_market_value = positions.aggregate(Sum('market_value'))['market_value__sum'] or Decimal('0')
            total_unrealized_pnl = positions.aggregate(Sum('unrealized_pnl'))['unrealized_pnl__sum'] or Decimal('0')
            total_realized_pnl = positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0')
            
            # Get cash balance
            user_profile = request.user.simulation_profile
            cash_balance = user_profile.virtual_cash_balance
            total_portfolio_value = cash_balance + total_market_value
            
            # Serialize positions
            serializer = self.get_serializer(positions, many=True)
            
            portfolio_summary = PortfolioSummarySerializer({
                'total_value': total_portfolio_value,
                'cash_balance': cash_balance,
                'positions_count': total_positions,
                'unrealized_pnl': total_unrealized_pnl,
                'daily_pnl': total_unrealized_pnl,  # Simplified
                'total_return_percentage': user_profile.calculate_total_return_percentage(),
                'positions': positions
            })
            
            return Response({
                'portfolio_summary': portfolio_summary.data,
                'position_breakdown': {
                    'total_positions': total_positions,
                    'long_positions': long_positions.count(),
                    'short_positions': short_positions.count(),
                    'largest_position': self._get_largest_position(positions),
                    'sector_allocation': self._get_sector_allocation(positions)
                }
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def update_prices(self, request):
        """Update all position prices with current market data"""
        try:
            positions = self.get_queryset()
            updated_count = self._update_position_prices(positions)
            
            return Response({
                'message': f'Updated prices for {updated_count} positions',
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _update_position_prices(self, positions):
        """Update position prices with current market data"""
        updated_count = 0
        
        for position in positions:
            try:
                # Get current simulated price
                current_price = position.instrument.get_current_simulated_price()
                if current_price:
                    position.update_market_values(current_price)
                    updated_count += 1
            except Exception:
                continue
        
        return updated_count
    
    def _get_largest_position(self, positions):
        """Get the largest position by market value"""
        if not positions.exists():
            return None
        
        largest = positions.order_by('-market_value').first()
        return {
            'symbol': largest.instrument.real_ticker.symbol,
            'market_value': float(largest.market_value),
            'percentage': 0  # Would calculate vs total portfolio
        }
    
    def _get_sector_allocation(self, positions):
        """Get sector allocation breakdown"""
        sector_allocation = {}
        
        for position in positions:
            sector = position.instrument.real_ticker.sector
            sector_name = sector.name if sector else 'Unknown'
            
            if sector_name not in sector_allocation:
                sector_allocation[sector_name] = {
                    'market_value': 0,
                    'position_count': 0
                }
            
            sector_allocation[sector_name]['market_value'] += float(position.market_value)
            sector_allocation[sector_name]['position_count'] += 1
        
        return sector_allocation


class RiskAlertViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Risk Alerts Management
    Manage virtual risk monitoring alerts
    """
    serializer_class = RiskAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['severity', 'is_acknowledged', 'is_resolved', 'alert_type']
    ordering = ['-created_at']
    
    def get_queryset(self):
        # Users can only see their own alerts
        return RiskAlert.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge a risk alert"""
        try:
            alert = self.get_object()
            alert.is_acknowledged = True
            alert.acknowledged_at = timezone.now()
            alert.save()
            
            serializer = self.get_serializer(alert)
            return Response({
                'message': 'Alert acknowledged',
                'alert': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve a risk alert"""
        try:
            alert = self.get_object()
            alert.is_resolved = True
            alert.resolved_at = timezone.now()
            if not alert.is_acknowledged:
                alert.is_acknowledged = True
                alert.acknowledged_at = timezone.now()
            alert.save()
            
            serializer = self.get_serializer(alert)
            return Response({
                'message': 'Alert resolved',
                'alert': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def active_alerts(self, request):
        """Get active (unresolved) alerts"""
        try:
            active_alerts = self.get_queryset().filter(is_resolved=False)
            
            # Group by severity
            alerts_by_severity = {
                'CRITICAL': active_alerts.filter(severity='CRITICAL').count(),
                'WARNING': active_alerts.filter(severity='WARNING').count(),
                'NORMAL': active_alerts.filter(severity='NORMAL').count()
            }
            
            serializer = self.get_serializer(active_alerts, many=True)
            
            return Response({
                'active_alerts': serializer.data,
                'alerts_by_severity': alerts_by_severity,
                'total_active': active_alerts.count()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ComplianceViewSet(viewsets.ViewSet):
    """
    SIMULATED Compliance Management
    Manage virtual trading compliance
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get compliance summary for user"""
        try:
            service = ComplianceService()
            summary = service.get_compliance_summary(request.user)
            
            return Response({
                'user': request.user.username,
                'compliance_summary': summary,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def create_default_rules(self, request):
        """Create default compliance rules for user"""
        try:
            service = ComplianceService()
            rules = service.create_default_compliance_rules(request.user)
            
            return Response({
                'message': f'Created {len(rules)} default compliance rules',
                'rules': [{'name': rule.name, 'type': rule.rule_type} for rule in rules]
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def recent_checks(self, request):
        """Get recent compliance checks"""
        try:
            days = int(request.query_params.get('days', 7))
            start_date = timezone.now() - timezone.timedelta(days=days)
            
            checks = ComplianceCheck.objects.filter(
                user=request.user,
                check_timestamp__gte=start_date
            ).order_by('-check_timestamp')
            
            # Summary statistics
            total_checks = checks.count()
            passed_checks = checks.filter(passed=True).count()
            failed_checks = total_checks - passed_checks
            
            # Group by rule type
            checks_by_type = {}
            for check in checks:
                rule_type = check.rule.rule_type
                if rule_type not in checks_by_type:
                    checks_by_type[rule_type] = {'total': 0, 'passed': 0, 'failed': 0}
                
                checks_by_type[rule_type]['total'] += 1
                if check.passed:
                    checks_by_type[rule_type]['passed'] += 1
                else:
                    checks_by_type[rule_type]['failed'] += 1
            
            # Recent violations
            recent_violations = checks.filter(passed=False)[:10]
            violation_data = []
            
            for violation in recent_violations:
                violation_data.append({
                    'rule_name': violation.rule.name,
                    'rule_type': violation.rule.rule_type,
                    'violation_message': violation.violation_message,
                    'check_timestamp': violation.check_timestamp,
                    'order_id': violation.order_id
                })
            
            return Response({
                'period_days': days,
                'summary': {
                    'total_checks': total_checks,
                    'passed_checks': passed_checks,
                    'failed_checks': failed_checks,
                    'compliance_rate': (passed_checks / total_checks * 100) if total_checks > 0 else 100
                },
                'checks_by_type': checks_by_type,
                'recent_violations': violation_data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PortfolioRiskViewSet(viewsets.ReadOnlyModelViewSet):
    """
    SIMULATED Portfolio Risk Analysis
    View virtual portfolio risk metrics
    """
    serializer_class = PortfolioRiskSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own risk metrics
        return PortfolioRisk.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def calculate_current_risk(self, request):
        """Calculate current portfolio risk metrics"""
        try:
            service = RiskManagementService()
            risk_record = service.update_portfolio_risk_metrics(request.user)
            
            serializer = self.get_serializer(risk_record)
            return Response({
                'message': 'Portfolio risk metrics updated',
                'risk_metrics': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def current_metrics(self, request):
        """Get current risk metrics"""
        try:
            # Get most recent risk calculation
            latest_risk = self.get_queryset().first()
            
            if not latest_risk:
                # No risk data available, calculate it
                service = RiskManagementService()
                latest_risk = service.update_portfolio_risk_metrics(request.user)
            
            serializer = self.get_serializer(latest_risk)
            
            # Add additional calculated metrics
            response_data = serializer.data
            
            # Calculate additional risk ratios
            if latest_risk.total_portfolio_value > 0:
                response_data['cash_percentage'] = float(
                    (latest_risk.cash_balance / latest_risk.total_portfolio_value) * 100
                )
                response_data['equity_percentage'] = float(
                    ((latest_risk.long_market_value - latest_risk.short_market_value) / 
                     latest_risk.total_portfolio_value) * 100
                )
            else:
                response_data['cash_percentage'] = 100.0
                response_data['equity_percentage'] = 0.0
            
            return Response(response_data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def risk_trend(self, request):
        """Get risk metrics trend over time"""
        try:
            days = int(request.query_params.get('days', 30))
            start_date = timezone.now().date() - timezone.timedelta(days=days)
            
            risk_records = self.get_queryset().filter(
                calculation_date__gte=start_date
            ).order_by('calculation_date')
            
            trend_data = []
            for record in risk_records:
                trend_data.append({
                    'date': record.calculation_date.isoformat(),
                    'total_portfolio_value': float(record.total_portfolio_value),
                    'daily_pnl': float(record.daily_pnl),
                    'gross_leverage': float(record.gross_leverage),
                    'net_leverage': float(record.net_leverage),
                    'risk_status': record.risk_status,
                    'active_alerts': record.active_alerts_count
                })
            
            return Response({
                'period_days': days,
                'trend_data': trend_data,
                'data_points': len(trend_data)
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RiskMonitoringViewSet(viewsets.ViewSet):
    """
    SIMULATED Risk Monitoring Dashboard
    Real-time risk monitoring for virtual trading
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get comprehensive risk dashboard data"""
        try:
            user = request.user
            
            # Get current portfolio risk
            latest_risk = PortfolioRisk.objects.filter(user=user).first()
            
            # Get active alerts
            active_alerts = RiskAlert.objects.filter(
                user=user, is_resolved=False
            )
            
            # Get position summary
            positions = SimulatedPosition.objects.filter(user=user)
            
            # Get limit utilization
            limits = PositionLimit.objects.filter(user=user, is_active=True)
            
            # Calculate dashboard metrics
            dashboard_data = {
                'portfolio_value': float(latest_risk.total_portfolio_value) if latest_risk else 0,
                'daily_pnl': float(latest_risk.daily_pnl) if latest_risk else 0,
                'cash_balance': float(user.simulation_profile.virtual_cash_balance),
                'positions_count': positions.count(),
                'active_alerts': {
                    'total': active_alerts.count(),
                    'critical': active_alerts.filter(severity='CRITICAL').count(),
                    'warning': active_alerts.filter(severity='WARNING').count()
                },
                'risk_status': latest_risk.risk_status if latest_risk else 'NORMAL',
                'leverage': {
                    'gross': float(latest_risk.gross_leverage) if latest_risk else 1.0,
                    'net': float(latest_risk.net_leverage) if latest_risk else 1.0
                },
                'limits_status': {
                    'total_limits': limits.count(),
                    'breached_limits': 0  # Would calculate actual breaches
                }
            }
            
            return Response({
                'dashboard': dashboard_data,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def run_risk_checks(self, request):
        """Manually run all risk checks for user"""
        try:
            service = RiskManagementService()
            
            # Update portfolio risk metrics
            risk_record = service.update_portfolio_risk_metrics(request.user)
            
            # Check for limit breaches
            position_service = PositionLimitService()
            breaches = position_service.check_limit_breaches(request.user)
            
            # Create alerts for new breaches
            new_alerts = []
            for breach in breaches:
                alert = service.create_risk_alert(
                    user=request.user,
                    alert_type='LIMIT_BREACH',
                    severity='WARNING',
                    message=f"Limit breach detected: {breach['limit_type']}",
                    current_value=breach.get('current_value'),
                    limit_value=breach.get('limit_value')
                )
                new_alerts.append(alert)
            
            return Response({
                'message': 'Risk checks completed',
                'portfolio_risk_updated': True,
                'breaches_found': len(breaches),
                'new_alerts_created': len(new_alerts),
                'risk_status': risk_record.risk_status
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
