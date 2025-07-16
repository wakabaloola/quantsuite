# apps/trading_analytics/views.py
"""
SIMULATED Trading Analytics API Views
====================================
RESTful endpoints for VIRTUAL trading performance analytics.
All endpoints analyze PAPER TRADING performance.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg, Max, Min
from decimal import Decimal
import pandas as pd
import numpy as np
from datetime import timedelta

from .models import (
    TradingPerformance, BenchmarkComparison, TradeAnalysis,
    PortfolioAnalytics, StrategyPerformance, RiskReport, PerformanceAttribution
)
from apps.trading_analytics.serializers import PortfolioAnalyticsSerializer
from .serializers import TradingPerformanceSerializer
from apps.order_management.models import SimulatedOrder, SimulatedTrade
from apps.trading_simulation.models import SimulatedPosition


class TradingPerformanceViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Trading Performance Analytics
    Analyze virtual trading performance metrics
    """
    serializer_class = TradingPerformanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['period_type']
    ordering = ['-period_end']
    
    def get_queryset(self):
        # Users can only see their own performance
        return TradingPerformance.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def calculate_performance(self, request):
        """Calculate performance metrics for a specific period"""
        try:
            period_type = request.data.get('period_type', 'MONTHLY')
            start_date = request.data.get('start_date')
            end_date = request.data.get('end_date')
            
            if not start_date or not end_date:
                return Response(
                    {'error': 'start_date and end_date are required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            start_date = timezone.datetime.fromisoformat(start_date).date()
            end_date = timezone.datetime.fromisoformat(end_date).date()
            
            # Calculate performance metrics
            performance_data = self._calculate_period_performance(
                request.user, start_date, end_date, period_type
            )
            
            # Create or update performance record
            performance, created = TradingPerformance.objects.update_or_create(
                user=request.user,
                period_type=period_type,
                period_start=timezone.datetime.combine(start_date, timezone.datetime.min.time()),
                defaults={
                    'period_end': timezone.datetime.combine(end_date, timezone.datetime.max.time()),
                    **performance_data
                }
            )
            
            serializer = self.get_serializer(performance)
            
            return Response({
                'message': 'Performance calculated successfully',
                'created': created,
                'performance': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def current_period(self, request):
        """Get current period performance metrics"""
        try:
            period_type = request.query_params.get('period_type', 'MONTHLY')
            
            # Determine current period dates
            now = timezone.now()
            if period_type == 'DAILY':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            elif period_type == 'WEEKLY':
                start_date = now - timedelta(days=now.weekday())
                end_date = now
            elif period_type == 'MONTHLY':
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            else:
                start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            
            # Calculate real-time performance
            performance_data = self._calculate_period_performance(
                request.user, start_date.date(), end_date.date(), period_type
            )
            
            return Response({
                'period_type': period_type,
                'period_start': start_date,
                'period_end': end_date,
                'performance': performance_data,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def performance_summary(self, request):
        """Get comprehensive performance summary"""
        try:
            # Get performance across different periods
            daily_perf = self.get_queryset().filter(period_type='DAILY').first()
            monthly_perf = self.get_queryset().filter(period_type='MONTHLY').first()
            yearly_perf = self.get_queryset().filter(period_type='YEARLY').first()
            
            # Get overall statistics
            user_profile = request.user.simulation_profile
            all_trades = SimulatedTrade.objects.filter(
                Q(buy_order__user=request.user) | Q(sell_order__user=request.user)
            )
            
            summary = {
                'total_return_percentage': user_profile.calculate_total_return_percentage(),
                'current_portfolio_value': float(user_profile.current_portfolio_value),
                'initial_balance': float(user_profile.initial_virtual_balance),
                'total_trades': all_trades.count(),
                'win_rate': user_profile.get_win_rate(),
                'performance_periods': {
                    'daily': TradingPerformanceSerializer(daily_perf).data if daily_perf else None,
                    'monthly': TradingPerformanceSerializer(monthly_perf).data if monthly_perf else None,
                    'yearly': TradingPerformanceSerializer(yearly_perf).data if yearly_perf else None
                }
            }
            
            return Response(summary)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_period_performance(self, user, start_date, end_date, period_type):
        """Calculate performance metrics for a specific period"""
        try:
            # Get portfolio values at start and end of period
            profile = user.simulation_profile
            ending_value = profile.current_portfolio_value
            
            # For simulation, use initial balance as starting value
            # In production, this would look up historical portfolio values
            starting_value = profile.initial_virtual_balance
            
            # Calculate return
            total_return = (ending_value - starting_value) / starting_value if starting_value > 0 else Decimal('0')
            
            # Get trades in period
            period_trades = SimulatedTrade.objects.filter(
                Q(buy_order__user=user) | Q(sell_order__user=user),
                trade_timestamp__date__range=[start_date, end_date]
            )
            
            # Calculate trade statistics
            total_trades = period_trades.count()
            
            # For simplification in simulation, assume 50% win rate
            winning_trades = int(total_trades * 0.5)
            losing_trades = total_trades - winning_trades
            
            # Calculate other metrics (simplified for simulation)
            volatility = self._estimate_volatility(user, start_date, end_date)
            sharpe_ratio = self._calculate_sharpe_ratio(total_return, volatility)
            max_drawdown = self._estimate_max_drawdown(user, start_date, end_date)
            
            return {
                'starting_value': starting_value,
                'ending_value': ending_value,
                'total_return': total_return,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'realized_pnl': ending_value - starting_value,  # Simplified
                'unrealized_pnl': Decimal('0'),  # Simplified
                'total_fees': Decimal('0'),  # Would calculate from trades
                'gross_pnl': ending_value - starting_value,
                'net_pnl': ending_value - starting_value
            }
            
        except Exception as e:
            return {}
    
    def _estimate_volatility(self, user, start_date, end_date):
        """Estimate portfolio volatility (simplified)"""
        # In a full implementation, this would calculate actual portfolio volatility
        # For simulation, return a reasonable estimate
        return Decimal('0.15')  # 15% annualized volatility
    
    def _calculate_sharpe_ratio(self, total_return, volatility):
        """Calculate Sharpe ratio"""
        if volatility and volatility > 0:
            risk_free_rate = Decimal('0.02')  # 2% risk-free rate
            excess_return = total_return - risk_free_rate
            return excess_return / volatility
        return None
    
    def _estimate_max_drawdown(self, user, start_date, end_date):
        """Estimate maximum drawdown (simplified)"""
        # In a full implementation, this would calculate actual drawdown from historical values
        # For simulation, return a reasonable estimate based on volatility
        return Decimal('0.05')  # 5% max drawdown


class PortfolioAnalyticsViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Portfolio Analytics
    Advanced portfolio analysis for virtual trading
    """
    serializer_class = PortfolioAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PortfolioAnalytics.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def analyze_current_portfolio(self, request):
        """Analyze current portfolio composition and metrics"""
        try:
            user = request.user
            analysis_date = timezone.now().date()
            
            # Get current positions
            positions = SimulatedPosition.objects.filter(user=user)
            
            # Calculate portfolio metrics
            analytics_data = self._calculate_portfolio_analytics(positions, analysis_date)
            
            # Create or update analytics record
            analytics, created = PortfolioAnalytics.objects.update_or_create(
                user=user,
                analysis_date=analysis_date,
                defaults=analytics_data
            )
            
            serializer = self.get_serializer(analytics)
            
            return Response({
                'message': 'Portfolio analysis completed',
                'created': created,
                'analytics': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def diversification_analysis(self, request):
        """Analyze portfolio diversification"""
        try:
            user = request.user
            positions = SimulatedPosition.objects.filter(user=user)
            
            if not positions.exists():
                return Response({
                    'message': 'No positions found',
                    'diversification': {}
                })
            
            # Sector diversification
            sector_allocation = {}
            total_value = Decimal('0')
            
            for position in positions:
                sector = position.instrument.real_ticker.sector
                sector_name = sector.name if sector else 'Unknown'
                position_value = abs(position.market_value)
                
                if sector_name not in sector_allocation:
                    sector_allocation[sector_name] = Decimal('0')
                
                sector_allocation[sector_name] += position_value
                total_value += position_value
            
            # Convert to percentages
            sector_percentages = {}
            for sector, value in sector_allocation.items():
                sector_percentages[sector] = float((value / total_value * 100)) if total_value > 0 else 0
            
            # Calculate concentration metrics
            concentration_hhi = self._calculate_hhi(sector_allocation.values(), total_value)
            
            # Geographic diversification (simplified)
            geographic_allocation = {'US': 100.0}  # Assume all US for simulation
            
            return Response({
                'sector_diversification': sector_percentages,
                'geographic_diversification': geographic_allocation,
                'concentration_metrics': {
                    'herfindahl_hirschman_index': float(concentration_hhi),
                    'effective_number_of_positions': len(positions),
                    'largest_position_percentage': max(sector_percentages.values()) if sector_percentages else 0
                },
                'total_portfolio_value': float(total_value)
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def performance_attribution(self, request):
        """Calculate performance attribution"""
        try:
            user = request.user
            period_days = int(request.query_params.get('period_days', 30))
            
            # Get positions and their performance
            positions = SimulatedPosition.objects.filter(user=user)
            
            attribution_data = []
            total_contribution = Decimal('0')
            
            for position in positions:
                # Simplified attribution calculation
                position_return = (position.unrealized_pnl / position.total_cost * 100) if position.total_cost > 0 else 0
                portfolio_weight = abs(position.market_value) / user.simulation_profile.current_portfolio_value * 100 if user.simulation_profile.current_portfolio_value > 0 else 0
                contribution = position_return * portfolio_weight / 100
                
                attribution_data.append({
                    'symbol': position.instrument.real_ticker.symbol,
                    'sector': position.instrument.real_ticker.sector.name if position.instrument.real_ticker.sector else 'Unknown',
                    'position_return_pct': float(position_return),
                    'portfolio_weight_pct': float(portfolio_weight),
                    'contribution_to_return': float(contribution),
                    'market_value': float(position.market_value)
                })
                
                total_contribution += contribution
            
            # Sort by contribution
            attribution_data.sort(key=lambda x: abs(x['contribution_to_return']), reverse=True)
            
            return Response({
                'period_days': period_days,
                'total_portfolio_return': float(total_contribution),
                'position_attribution': attribution_data,
                'top_contributors': attribution_data[:5],
                'top_detractors': [x for x in attribution_data if x['contribution_to_return'] < 0][:5]
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_portfolio_analytics(self, positions, analysis_date):
        """Calculate comprehensive portfolio analytics"""
        try:
            total_positions = positions.count()
            long_positions = positions.filter(quantity__gt=0).count()
            short_positions = positions.filter(quantity__lt=0).count()
            
            # Calculate cash percentage
            user = positions.first().user if positions.exists() else None
            if user:
                cash_balance = user.simulation_profile.virtual_cash_balance
                total_portfolio_value = user.simulation_profile.current_portfolio_value
                cash_percentage = (cash_balance / total_portfolio_value * 100) if total_portfolio_value > 0 else 100
            else:
                cash_percentage = 100
            
            # Sector diversification
            sector_allocation = self._calculate_sector_allocation(positions)
            
            # Simplified metrics for simulation
            return {
                'total_positions': total_positions,
                'long_positions': long_positions,
                'short_positions': short_positions,
                'cash_percentage': Decimal(str(cash_percentage)),
                'sector_diversification': sector_allocation,
                'geographic_diversification': {'US': 100.0},  # Simplified
                'market_cap_distribution': {'Large': 70.0, 'Mid': 20.0, 'Small': 10.0},  # Simplified
                'portfolio_beta': Decimal('1.0'),  # Simplified
                'portfolio_correlation_sp500': Decimal('0.8'),  # Simplified
                'concentration_hhi': self._calculate_hhi_from_positions(positions)
            }
            
        except Exception:
            return {}
    
    def _calculate_sector_allocation(self, positions):
        """Calculate sector allocation percentages"""
        sector_allocation = {}
        total_value = Decimal('0')
        
        for position in positions:
            sector = position.instrument.real_ticker.sector
            sector_name = sector.name if sector else 'Unknown'
            position_value = abs(position.market_value)
            
            if sector_name not in sector_allocation:
                sector_allocation[sector_name] = Decimal('0')
            
            sector_allocation[sector_name] += position_value
            total_value += position_value
        
        # Convert to percentages
        sector_percentages = {}
        for sector, value in sector_allocation.items():
            sector_percentages[sector] = float((value / total_value * 100)) if total_value > 0 else 0
        
        return sector_percentages
    
    def _calculate_hhi(self, values, total):
        """Calculate Herfindahl-Hirschman Index"""
        if total == 0:
            return Decimal('0')
        
        hhi = sum((value / total) ** 2 for value in values)
        return Decimal(str(hhi))
    
    def _calculate_hhi_from_positions(self, positions):
        """Calculate HHI from position values"""
        values = [abs(pos.market_value) for pos in positions]
        total = sum(values)
        return self._calculate_hhi(values, total)


class TradingReportsViewSet(viewsets.ViewSet):
    """
    SIMULATED Trading Reports
    Generate comprehensive trading reports
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def generate_monthly_report(self, request):
        """Generate monthly trading report"""
        try:
            user = request.user
            month = request.data.get('month', timezone.now().month)
            year = request.data.get('year', timezone.now().year)
            
            # Calculate date range
            start_date = timezone.datetime(year, month, 1).date()
            if month == 12:
                end_date = timezone.datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = timezone.datetime(year, month + 1, 1).date() - timedelta(days=1)
            
            # Get trading activity for the month
            month_trades = SimulatedTrade.objects.filter(
                Q(buy_order__user=user) | Q(sell_order__user=user),
                trade_timestamp__date__range=[start_date, end_date]
            )
            
            month_orders = SimulatedOrder.objects.filter(
                user=user,
                order_timestamp__date__range=[start_date, end_date]
            )
            
            # Calculate report metrics
            report_data = {
                'period': f"{year}-{month:02d}",
                'start_date': start_date,
                'end_date': end_date,
                'trading_activity': {
                    'total_orders': month_orders.count(),
                    'filled_orders': month_orders.filter(status='FILLED').count(),
                    'cancelled_orders': month_orders.filter(status='CANCELLED').count(),
                    'total_trades': month_trades.count(),
                    'total_volume': month_trades.aggregate(Sum('quantity'))['quantity__sum'] or 0,
                    'total_value': float(month_trades.aggregate(Sum('notional_value'))['notional_value__sum'] or 0)
                },
                'performance': self._calculate_monthly_performance(user, start_date, end_date),
                'risk_metrics': self._calculate_monthly_risk(user, start_date, end_date),
                'top_trades': self._get_top_trades(month_trades, limit=10)
            }
            
            return Response(report_data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def trading_summary(self, request):
        """Get comprehensive trading summary"""
        try:
            user = request.user
            
            # Overall statistics
            all_orders = SimulatedOrder.objects.filter(user=user)
            all_trades = SimulatedTrade.objects.filter(
                Q(buy_order__user=user) | Q(sell_order__user=user)
            )
            
            # Time-based analysis
            today = timezone.now().date()
            this_week = today - timedelta(days=today.weekday())
            this_month = today.replace(day=1)
            
            summary = {
                'overall_statistics': {
                    'total_orders': all_orders.count(),
                    'total_trades': all_trades.count(),
                    'current_portfolio_value': float(user.simulation_profile.current_portfolio_value),
                    'total_return_percentage': user.simulation_profile.calculate_total_return_percentage(),
                    'win_rate_percentage': user.simulation_profile.get_win_rate()
                },
                'recent_activity': {
                    'orders_today': all_orders.filter(order_timestamp__date=today).count(),
                    'orders_this_week': all_orders.filter(order_timestamp__date__gte=this_week).count(),
                    'orders_this_month': all_orders.filter(order_timestamp__date__gte=this_month).count(),
                    'trades_today': all_trades.filter(trade_timestamp__date=today).count(),
                    'trades_this_week': all_trades.filter(trade_timestamp__date__gte=this_week).count(),
                    'trades_this_month': all_trades.filter(trade_timestamp__date__gte=this_month).count()
                },
                'positions_summary': self._get_positions_summary(user),
                'risk_summary': self._get_risk_summary(user)
            }
            
            return Response(summary)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_monthly_performance(self, user, start_date, end_date):
        """Calculate performance metrics for the month"""
        # Simplified calculation for simulation
        profile = user.simulation_profile
        current_value = profile.current_portfolio_value
        initial_value = profile.initial_virtual_balance
        
        return {
            'starting_value': float(initial_value),
            'ending_value': float(current_value),
            'absolute_return': float(current_value - initial_value),
            'percentage_return': float((current_value - initial_value) / initial_value * 100) if initial_value > 0 else 0
        }
    
    def _calculate_monthly_risk(self, user, start_date, end_date):
        """Calculate risk metrics for the month"""
        # Simplified risk calculation
        return {
            'max_drawdown': 5.0,  # Placeholder
            'volatility': 15.0,   # Placeholder
            'sharpe_ratio': 1.2,  # Placeholder
            'var_95': 1000.0      # Placeholder
        }
    
    def _get_top_trades(self, trades, limit=10):
        """Get top trades by value"""
        top_trades = trades.order_by('-notional_value')[:limit]
        
        trade_data = []
        for trade in top_trades:
            trade_data.append({
                'trade_id': str(trade.trade_id),
                'instrument': trade.instrument.real_ticker.symbol,
                'quantity': trade.quantity,
                'price': float(trade.price),
                'value': float(trade.notional_value),
                'timestamp': trade.trade_timestamp
            })
        
        return trade_data
    
    def _get_positions_summary(self, user):
        """Get summary of current positions"""
        positions = SimulatedPosition.objects.filter(user=user)
        
        if not positions.exists():
            return {'total_positions': 0}
        
        total_value = sum(abs(pos.market_value) for pos in positions)
        unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
        
        return {
            'total_positions': positions.count(),
            'total_market_value': float(total_value),
            'total_unrealized_pnl': float(unrealized_pnl),
            'largest_position': {
                'symbol': positions.order_by('-market_value').first().instrument.real_ticker.symbol,
                'value': float(positions.order_by('-market_value').first().market_value)
            } if positions.exists() else None
        }
    
    def _get_risk_summary(self, user):
        """Get risk summary for user"""
        from apps.risk_management.models import RiskAlert, PortfolioRisk
        
        active_alerts = RiskAlert.objects.filter(user=user, is_resolved=False)
        latest_risk = PortfolioRisk.objects.filter(user=user).first()
        
        return {
            'active_alerts': active_alerts.count(),
            'risk_status': latest_risk.risk_status if latest_risk else 'NORMAL',
            'portfolio_var': float(latest_risk.portfolio_var_1d) if latest_risk and latest_risk.portfolio_var_1d else None
        }
