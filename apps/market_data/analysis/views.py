# apps/market_data/analysis/views.py
"""
API views for enhanced technical analysis service
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import asyncio

from .enhanced_service import enhanced_ta_service
from .tasks import analyze_symbol_comprehensive, analyze_watchlist_symbols


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def analyze_symbol(request, symbol):
    """Perform comprehensive technical analysis on a symbol"""
    try:
        # Submit analysis task
        task = analyze_symbol_comprehensive.delay(symbol.upper())
        
        return Response({
            'status': 'analyzing',
            'symbol': symbol.upper(),
            'task_id': task.id,
            'message': f'Technical analysis initiated for {symbol.upper()}'
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cached_signal(request, symbol):
    """Get cached technical signal for symbol"""
    try:
        signal = enhanced_ta_service.get_cached_signal(symbol.upper())
        
        if signal:
            return Response({
                'status': 'success',
                'signal': signal.to_dict()
            })
        else:
            return Response({
                'status': 'not_found',
                'message': f'No cached signal found for {symbol.upper()}'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_watchlist(request):
    """Analyze multiple symbols from watchlist"""
    try:
        symbols = request.data.get('symbols', [])
        
        if not symbols:
            # Analyze default active symbols
            task = analyze_watchlist_symbols.delay()
        else:
            # Analyze specified symbols
            task = analyze_watchlist_symbols.delay(symbols)
        
        return Response({
            'status': 'analyzing',
            'symbols_count': len(symbols) if symbols else 'auto',
            'task_id': task.id,
            'message': 'Watchlist analysis initiated'
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_service_metrics(request):
    """Get technical analysis service metrics"""
    try:
        metrics = enhanced_ta_service.get_service_metrics()
        
        return Response({
            'status': 'success',
            'metrics': metrics
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_signal_history(request, symbol):
    """Get historical signals for a symbol"""
    try:
        from ..models import TechnicalIndicator, Ticker
        from django.utils import timezone
        from datetime import timedelta
        
        # Get signals from last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        ticker = Ticker.objects.filter(symbol=symbol.upper(), is_active=True).first()
        if not ticker:
            return Response({
                'status': 'error',
                'error': f'Ticker {symbol.upper()} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        signals = TechnicalIndicator.objects.filter(
            ticker=ticker,
            indicator_name='comprehensive_signal',
            timestamp__gte=thirty_days_ago
        ).order_by('-timestamp')[:50]
        
        signal_data = []
        for signal in signals:
            if signal.values:
                signal_data.append({
                    'timestamp': signal.timestamp.isoformat(),
                    'strength': float(signal.value),
                    'details': signal.values,
                    'parameters': signal.parameters
                })
        
        return Response({
            'status': 'success',
            'symbol': symbol.upper(),
            'signals_count': len(signal_data),
            'signals': signal_data
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
