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
