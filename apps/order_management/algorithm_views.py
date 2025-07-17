from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import AlgorithmicOrder, AlgorithmExecution, CustomStrategy
from .serializers import AlgorithmicOrderSerializer, AlgorithmExecutionSerializer, CustomStrategySerializer
from .algorithm_services import AlgorithmExecutionEngine


class AlgorithmicOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing algorithmic orders"""
    
    serializer_class = AlgorithmicOrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return AlgorithmicOrder.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start algorithm execution"""
        algo_order = self.get_object()
        
        if algo_order.status != 'PENDING':
            return Response(
                {'error': f'Cannot start algorithm in status: {algo_order.status}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        engine = AlgorithmExecutionEngine()
        success = engine.start_algorithm(algo_order)
        
        if success:
            return Response({'message': 'Algorithm started successfully'})
        else:
            return Response(
                {'error': 'Failed to start algorithm'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause algorithm execution"""
        algo_order = self.get_object()
        
        engine = AlgorithmExecutionEngine()
        success = engine.pause_algorithm(algo_order)
        
        if success:
            return Response({'message': 'Algorithm paused successfully'})
        else:
            return Response(
                {'error': 'Failed to pause algorithm'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume algorithm execution"""
        algo_order = self.get_object()
        
        engine = AlgorithmExecutionEngine()
        success = engine.resume_algorithm(algo_order)
        
        if success:
            return Response({'message': 'Algorithm resumed successfully'})
        else:
            return Response(
                {'error': 'Failed to resume algorithm'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel algorithm execution"""
        algo_order = self.get_object()
        
        engine = AlgorithmExecutionEngine()
        success = engine.cancel_algorithm(algo_order)
        
        if success:
            return Response({'message': 'Algorithm cancelled successfully'})
        else:
            return Response(
                {'error': 'Failed to cancel algorithm'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """Get algorithm executions"""
        algo_order = self.get_object()
        executions = algo_order.executions.all()
        serializer = AlgorithmExecutionSerializer(executions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get algorithm performance metrics"""
        algo_order = self.get_object()
        
        performance = {
            'algo_order_id': str(algo_order.algo_order_id),
            'algorithm_type': algo_order.algorithm_type,
            'status': algo_order.status,
            'fill_ratio': algo_order.fill_ratio,
            'average_execution_price': float(algo_order.average_execution_price) if algo_order.average_execution_price else None,
            'implementation_shortfall': float(algo_order.implementation_shortfall) if algo_order.implementation_shortfall else None,
            'total_slippage': float(algo_order.total_slippage),
            'execution_count': algo_order.executions.count(),
            'duration_minutes': algo_order.duration_minutes,
            'started_timestamp': algo_order.started_timestamp,
            'completed_timestamp': algo_order.completed_timestamp
        }
        
        return Response(performance)

    @action(detail=True, methods=['get'], url_path='market-data')
    def market_data(self, request, pk=None):
        """Get real-time market data for algorithm"""
        try:
            algo_order = self.get_object()
            
            # Get enhanced market data
            from .algorithm_services import AlgorithmExecutionEngine
            engine = AlgorithmExecutionEngine()
            market_data = engine._get_enhanced_market_data(algo_order.instrument)
            
            # Add algorithm-specific metrics
            algorithm_metrics = {
                'execution_favorability': self._calculate_execution_favorability(market_data),
                'price_impact_estimate': self._estimate_price_impact(algo_order, market_data),
                'optimal_execution_time': self._suggest_optimal_timing(algo_order, market_data)
            }
            
            return Response({
                'algorithm_id': str(pk),
                'symbol': algo_order.instrument.real_ticker.symbol,
                'market_data': market_data,
                'algorithm_metrics': algorithm_metrics,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response({'error': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _calculate_execution_favorability(self, market_data):
        """Calculate how favorable current conditions are for execution"""
        try:
            spread_bps = float(market_data.get('spread_bps', 100))
            volume = float(market_data.get('volume', 0))
            volatility = market_data.get('volatility_24h', 0)
            
            # Score based on tight spreads, high volume, low volatility
            spread_score = max(0, 1 - (spread_bps / 100))  # Lower spread = better
            volume_score = min(1, volume / 100000)  # Higher volume = better
            volatility_score = max(0, 1 - volatility)  # Lower volatility = better
            
            overall_score = (spread_score + volume_score + volatility_score) / 3
            return round(overall_score, 3)
            
        except Exception:
            return 0.5

    def _estimate_price_impact(self, algo_order, market_data):
        """Estimate price impact of algorithm execution"""
        try:
            volume = float(market_data.get('volume', 1))
            order_size = float(algo_order.total_quantity)
            
            # Simple price impact estimation
            participation_rate = order_size / volume if volume > 0 else 1
            impact_bps = participation_rate * 10  # Rough estimate
            
            return {
                'estimated_impact_bps': round(impact_bps, 2),
                'participation_rate': round(participation_rate * 100, 2),
                'impact_level': 'LOW' if impact_bps < 5 else 'MEDIUM' if impact_bps < 15 else 'HIGH'
            }
            
        except Exception:
            return {'estimated_impact_bps': 0, 'participation_rate': 0, 'impact_level': 'UNKNOWN'}

    def _suggest_optimal_timing(self, algo_order, market_data):
        """Suggest optimal timing for algorithm execution"""
        try:
            market_status = market_data.get('market_status', 'closed')
            spread_bps = float(market_data.get('spread_bps', 100))
            
            if market_status == 'closed':
                return 'WAIT_FOR_MARKET_OPEN'
            elif spread_bps > 50:
                return 'WAIT_FOR_TIGHTER_SPREADS'
            elif market_data.get('volatility_24h', 0) > 0.05:
                return 'WAIT_FOR_LOWER_VOLATILITY'
            else:
                return 'OPTIMAL_NOW'
                
        except Exception:
            return 'UNKNOWN'


class AlgorithmExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing algorithm executions"""
    
    serializer_class = AlgorithmExecutionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return AlgorithmExecution.objects.filter(
            algo_order__user=self.request.user
        )


class CustomStrategyViewSet(viewsets.ModelViewSet):
    """ViewSet for managing custom trading strategies"""
    
    serializer_class = CustomStrategySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return CustomStrategy.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def validate_code(self, request, pk=None):
        """Validate strategy code syntax"""
        strategy = self.get_object()
        
        try:
            # Basic syntax validation
            compile(strategy.strategy_code, '<strategy>', 'exec')
            
            strategy.is_validated = True
            strategy.save()
            
            return Response({'message': 'Strategy code validated successfully'})
            
        except SyntaxError as e:
            return Response(
                {'error': f'Syntax error in strategy code: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Validation error: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def backtest(self, request, pk=None):
        """Run backtest for strategy"""
        strategy = self.get_object()
        
        # This would integrate with backtesting engine
        # For now, return placeholder
        
        return Response({
            'message': 'Backtest initiated',
            'strategy_id': strategy.id,
            'estimated_completion': '5 minutes'
        })
