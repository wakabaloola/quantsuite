# apps/trading_simulation/views.py
"""
SIMULATED Trading API Views
==========================
RESTful endpoints for VIRTUAL trading simulation.
All endpoints handle PAPER TRADING - no real money involved.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal

from .models import (
    SimulatedExchange, SimulatedInstrument, TradingSession, 
    MarketMaker, UserSimulationProfile, SimulationScenario
)
from .serializers import (
    SimulatedExchangeSerializer, SimulatedInstrumentSerializer,
    TradingSessionSerializer, UserSimulationProfileSerializer,
    SimulationScenarioSerializer, MarketMakerSerializer
)
from .services import (
    SimulatedExchangeService, UserTradingService, 
    MarketSimulationService, SimulationMonitoringService
)
from apps.market_data.models import Ticker, Exchange


class SimulatedExchangeViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Exchange Management
    Create and manage virtual trading exchanges
    """
    queryset = SimulatedExchange.objects.all()
    serializer_class = SimulatedExchangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'real_exchange']
    
    @action(detail=False, methods=['post'])
    def create_from_real_exchange(self, request):
        """Create a simulated exchange based on a real exchange"""
        try:
            real_exchange_id = request.data.get('real_exchange_id')
            if not real_exchange_id:
                return Response(
                    {'error': 'real_exchange_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            real_exchange = Exchange.objects.get(id=real_exchange_id)
            service = SimulatedExchangeService()
            
            sim_exchange = service.create_simulated_exchange(
                real_exchange=real_exchange,
                trading_fee_percentage=Decimal(request.data.get('trading_fee_percentage', '0.0010')),
                simulated_latency_ms=int(request.data.get('simulated_latency_ms', 50))
            )
            
            serializer = self.get_serializer(sim_exchange)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exchange.DoesNotExist:
            return Response(
                {'error': 'Real exchange not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def add_instrument(self, request, pk=None):
        """Add a real ticker as a simulated instrument to the exchange"""
        try:
            sim_exchange = self.get_object()
            ticker_id = request.data.get('ticker_id')
            
            if not ticker_id:
                return Response(
                    {'error': 'ticker_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            real_ticker = Ticker.objects.get(id=ticker_id)
            service = SimulatedExchangeService()
            
            sim_instrument = service.add_instrument_to_exchange(
                sim_exchange=sim_exchange,
                real_ticker=real_ticker,
                price_multiplier=Decimal(request.data.get('price_multiplier', '1.0')),
                volatility_multiplier=Decimal(request.data.get('volatility_multiplier', '1.0'))
            )
            
            serializer = SimulatedInstrumentSerializer(sim_instrument)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Ticker.DoesNotExist:
            return Response(
                {'error': 'Ticker not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def instruments(self, request, pk=None):
        """Get all instruments for this exchange"""
        sim_exchange = self.get_object()
        instruments = sim_exchange.instruments.all()
        serializer = SimulatedInstrumentSerializer(instruments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get exchange status and statistics"""
        try:
            sim_exchange = self.get_object()
            
            # Calculate statistics
            total_instruments = sim_exchange.instruments.count()
            active_instruments = sim_exchange.instruments.filter(is_tradable=True).count()
            total_orders_today = sim_exchange.orders.filter(
                order_timestamp__date=timezone.now().date()
            ).count()
            total_trades_today = sim_exchange.trades.filter(
                trade_timestamp__date=timezone.now().date()
            ).count()
            
            return Response({
                'exchange_code': sim_exchange.code,
                'status': sim_exchange.status,
                'total_instruments': total_instruments,
                'active_instruments': active_instruments,
                'orders_today': total_orders_today,
                'trades_today': total_trades_today,
                'trading_fee_percentage': float(sim_exchange.trading_fee_percentage),
                'simulated_latency_ms': sim_exchange.simulated_latency_ms,
                'last_updated': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TradingSessionViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Trading Session Management
    Manage virtual trading sessions
    """
    queryset = TradingSession.objects.all()
    serializer_class = TradingSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange', 'session_type', 'status']
    
    @action(detail=False, methods=['post'])
    def create_session(self, request):
        """Create a new trading session"""
        try:
            exchange_id = request.data.get('exchange_id')
            if not exchange_id:
                return Response(
                    {'error': 'exchange_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            sim_exchange = SimulatedExchange.objects.get(id=exchange_id)
            service = SimulatedExchangeService()
            
            session = service.create_trading_session(
                exchange=sim_exchange,
                session_type=request.data.get('session_type', 'CONTINUOUS'),
                duration_hours=int(request.data.get('duration_hours', 8))
            )
            
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except SimulatedExchange.DoesNotExist:
            return Response(
                {'error': 'Simulated exchange not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def start_session(self, request, pk=None):
        """Start a trading session"""
        try:
            session = self.get_object()
            session.status = 'ACTIVE'
            session.start_time = timezone.now()
            session.save()
            
            serializer = self.get_serializer(session)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def stop_session(self, request, pk=None):
        """Stop a trading session"""
        try:
            session = self.get_object()
            session.status = 'STOPPED'
            session.end_time = timezone.now()
            session.save()
            
            serializer = self.get_serializer(session)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserSimulationProfileViewSet(viewsets.ModelViewSet):
    """
    User SIMULATION Profile Management
    Manage virtual trading profiles
    """
    queryset = UserSimulationProfile.objects.all()
    serializer_class = UserSimulationProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own profile
        return UserSimulationProfile.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def my_profile(self, request):
        """Get current user's simulation profile"""
        try:
            service = UserTradingService()
            profile = service.initialize_user_profile(request.user)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def reset_simulation(self, request):
        """Reset user's simulation to start fresh"""
        try:
            new_balance = Decimal(request.data.get('new_balance', '100000.00'))
            service = UserTradingService()
            
            profile = service.reset_user_simulation(request.user, new_balance)
            serializer = self.get_serializer(profile)
            
            return Response({
                'message': 'Simulation reset successfully',
                'profile': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get comprehensive user trading statistics"""
        try:
            service = UserTradingService()
            stats = service.get_user_statistics(request.user)
            
            return Response({
                'user': request.user.username,
                'statistics': stats,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def update_portfolio_value(self, request):
        """Recalculate current portfolio value"""
        try:
            service = UserTradingService()
            total_value = service.calculate_portfolio_value(request.user)
            
            return Response({
                'total_portfolio_value': float(total_value),
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SimulationScenarioViewSet(viewsets.ModelViewSet):
    """
    SIMULATION Scenario Management
    Apply market scenarios to exchanges
    """
    queryset = SimulationScenario.objects.all()
    serializer_class = SimulationScenarioSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['scenario_type']
    
    @action(detail=True, methods=['post'])
    def apply_to_exchange(self, request, pk=None):
        """Apply scenario to a simulated exchange"""
        try:
            scenario = self.get_object()
            exchange_id = request.data.get('exchange_id')
            
            if not exchange_id:
                return Response(
                    {'error': 'exchange_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            sim_exchange = SimulatedExchange.objects.get(id=exchange_id)
            service = MarketSimulationService()
            
            service.apply_scenario(sim_exchange, scenario)
            
            return Response({
                'message': f'Applied scenario "{scenario.name}" to exchange {sim_exchange.code}',
                'scenario': self.get_serializer(scenario).data
            })
            
        except SimulatedExchange.DoesNotExist:
            return Response(
                {'error': 'Simulated exchange not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def create_custom_scenario(self, request):
        """Create a custom market scenario"""
        try:
            scenario_data = {
                'name': request.data.get('name', 'Custom Scenario'),
                'description': request.data.get('description', ''),
                'scenario_type': 'CUSTOM',
                'volatility_factor': Decimal(request.data.get('volatility_factor', '1.0')),
                'volume_factor': Decimal(request.data.get('volume_factor', '1.0')),
                'liquidity_factor': Decimal(request.data.get('liquidity_factor', '1.0')),
                'daily_drift_percentage': Decimal(request.data.get('daily_drift_percentage', '0.0'))
            }
            
            scenario = SimulationScenario.objects.create(**scenario_data)
            serializer = self.get_serializer(scenario)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MarketMakerViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Market Maker Management
    Configure virtual market makers for liquidity
    """
    queryset = MarketMaker.objects.all()
    serializer_class = MarketMakerSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange', 'algorithm_type', 'is_active']
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a market maker"""
        try:
            market_maker = self.get_object()
            market_maker.is_active = True
            market_maker.save()
            
            serializer = self.get_serializer(market_maker)
            return Response({
                'message': f'Market maker {market_maker.name} activated',
                'market_maker': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a market maker"""
        try:
            market_maker = self.get_object()
            market_maker.is_active = False
            market_maker.save()
            
            serializer = self.get_serializer(market_maker)
            return Response({
                'message': f'Market maker {market_maker.name} deactivated',
                'market_maker': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SimulationMonitoringViewSet(viewsets.ViewSet):
    """
    SIMULATION System Monitoring
    Monitor health and status of simulation components
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def health_report(self, request):
        """Get comprehensive system health report"""
        try:
            service = SimulationMonitoringService()
            report = service.generate_health_report()
            return Response(report)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def update_market_data(self, request):
        """Manually trigger market data update for all instruments"""
        try:
            service = SimulationMonitoringService()
            service.update_all_market_data()
            
            return Response({
                'message': 'Market data update initiated',
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def cleanup_expired_orders(self, request):
        """Clean up expired orders"""
        try:
            service = SimulationMonitoringService()
            service.cleanup_expired_orders()
            
            return Response({
                'message': 'Order cleanup completed',
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def exchange_summary(self, request):
        """Get summary of all exchanges"""
        try:
            exchanges = SimulatedExchange.objects.all()
            summary = []
            
            for exchange in exchanges:
                exchange_data = {
                    'code': exchange.code,
                    'name': exchange.name,
                    'status': exchange.status,
                    'instruments_count': exchange.instruments.count(),
                    'active_instruments': exchange.instruments.filter(is_tradable=True).count(),
                    'orders_today': exchange.orders.filter(
                        order_timestamp__date=timezone.now().date()
                    ).count(),
                    'trades_today': exchange.trades.filter(
                        trade_timestamp__date=timezone.now().date()
                    ).count()
                }
                summary.append(exchange_data)
            
            return Response({
                'total_exchanges': len(summary),
                'exchanges': summary,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def user_summary(self, request):
        """Get summary of simulation users"""
        try:
            profiles = UserSimulationProfile.objects.all()
            
            summary = {
                'total_users': profiles.count(),
                'active_users': profiles.filter(
                    current_portfolio_value__gt=0
                ).count(),
                'average_portfolio_value': float(
                    profiles.aggregate(
                        avg_value=models.Avg('current_portfolio_value')
                    )['avg_value'] or 0
                ),
                'total_virtual_capital': float(
                    profiles.aggregate(
                        total_capital=models.Sum('current_portfolio_value')
                    )['total_capital'] or 0
                )
            }
            
            return Response(summary)
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
