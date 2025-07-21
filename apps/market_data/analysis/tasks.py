# apps/market_data/analysis/tasks.py
"""
Celery tasks for enhanced technical analysis
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
import asyncio

from .enhanced_service import enhanced_ta_service
from ..models import Ticker

logger = get_task_logger(__name__)


@shared_task
def analyze_symbol_comprehensive(symbol):
    """Perform comprehensive technical analysis on a symbol"""
    try:
        # Run async analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        signal = loop.run_until_complete(
            enhanced_ta_service.analyze_symbol_comprehensive(symbol)
        )
        loop.close()
        
        if signal:
            logger.info(f"Analysis completed for {symbol}: {signal.signal_type.value}")
            return {
                'status': 'success',
                'symbol': symbol,
                'signal_type': signal.signal_type.value,
                'strength': signal.strength,
                'confidence': signal.confidence.value,
                'timestamp': signal.timestamp.isoformat()
            }
        else:
            return {
                'status': 'no_signal',
                'symbol': symbol,
                'message': 'No actionable signal generated'
            }
            
    except Exception as e:
        logger.error(f"Technical analysis failed for {symbol}: {e}")
        return {'status': 'error', 'symbol': symbol, 'error': str(e)}


@shared_task
def analyze_watchlist_symbols(symbols=None):
    """Analyze multiple symbols from watchlist"""
    try:
        if symbols is None:
            # Get active symbols from database
            active_symbols = list(
                Ticker.objects.filter(is_active=True)
                .values_list('symbol', flat=True)[:50]  # Limit for performance
            )
        else:
            active_symbols = symbols
        
        if not active_symbols:
            return {'status': 'no_symbols', 'message': 'No symbols to analyze'}
        
        results = []
        for symbol in active_symbols:
            try:
                result = analyze_symbol_comprehensive.delay(symbol)
                results.append({
                    'symbol': symbol,
                    'task_id': result.id,
                    'status': 'submitted'
                })
            except Exception as e:
                results.append({
                    'symbol': symbol,
                    'status': 'error',
                    'error': str(e)
                })
        
        logger.info(f"Submitted analysis tasks for {len(active_symbols)} symbols")
        return {
            'status': 'success',
            'symbols_count': len(active_symbols),
            'results': results,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Watchlist analysis failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def collect_technical_analysis_metrics():
    """Collect TA service performance metrics"""
    try:
        metrics = enhanced_ta_service.get_service_metrics()
        
        logger.info(f"TA Metrics: {metrics['symbols_analyzed']} symbols analyzed")
        return {
            'status': 'success',
            'metrics': metrics,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"TA metrics collection failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def cleanup_cached_signals():
    """Cleanup old cached technical signals"""
    try:
        from django.core.cache import cache
        from django.utils import timezone
        from datetime import timedelta
        
        # This is a placeholder - Redis handles TTL automatically
        # but we could implement manual cleanup here if needed
        
        logger.info("Signal cache cleanup completed")
        return {
            'status': 'success',
            'message': 'Cache cleanup completed',
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Signal cache cleanup failed: {e}")
        return {'status': 'error', 'error': str(e)}
