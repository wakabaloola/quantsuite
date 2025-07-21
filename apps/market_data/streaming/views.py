# apps/market_data/streaming/views.py
"""
API views for streaming service control
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .service import streaming_engine
from .tasks import (
    start_streaming_engine, stop_streaming_engine, 
    subscribe_to_symbols, unsubscribe_from_symbols
)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_streaming(request):
    """Start the streaming engine"""
    try:
        task = start_streaming_engine.delay()
        return Response({
            'status': 'starting',
            'task_id': task.id,
            'message': 'Streaming engine start initiated'
        })
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_streaming(request):
    """Stop the streaming engine"""
    try:
        task = stop_streaming_engine.delay()
        return Response({
            'status': 'stopping',
            'task_id': task.id,
            'message': 'Streaming engine stop initiated'
        })
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def streaming_status(request):
    """Get streaming engine status and metrics"""
    try:
        metrics = streaming_engine.get_metrics()
        return Response(metrics)
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscribe_symbols(request):
    """Subscribe to symbols for streaming"""
    try:
        symbols = request.data.get('symbols', [])
        high_frequency = request.data.get('high_frequency', False)
        
        if not symbols:
            return Response({
                'status': 'error',
                'error': 'symbols parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        task = subscribe_to_symbols.delay(symbols, high_frequency)
        return Response({
            'status': 'subscribing',
            'symbols': symbols,
            'high_frequency': high_frequency,
            'task_id': task.id
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unsubscribe_symbols(request):
    """Unsubscribe from symbols"""
    try:
        symbols = request.data.get('symbols', [])
        
        if not symbols:
            return Response({
                'status': 'error',
                'error': 'symbols parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        task = unsubscribe_from_symbols.delay(symbols)
        return Response({
            'status': 'unsubscribing',
            'symbols': symbols,
            'task_id': task.id
        })
        
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quote(request, symbol):
    """Get current quote for symbol"""
    try:
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        quote = loop.run_until_complete(streaming_engine.get_current_quote(symbol))
        loop.close()
        
        if quote:
            return Response({
                'symbol': quote.symbol,
                'price': float(quote.price),
                'volume': quote.volume,
                'timestamp': quote.timestamp.isoformat(),
                'bid': float(quote.bid) if quote.bid else None,
                'ask': float(quote.ask) if quote.ask else None,
                'change_24h': float(quote.change_24h) if quote.change_24h else None,
                'change_pct_24h': quote.change_pct_24h
            })
        else:
            return Response({
                'status': 'error',
                'error': 'Quote not available'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
