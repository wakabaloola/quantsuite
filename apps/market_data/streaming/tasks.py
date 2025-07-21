# apps/market_data/streaming/tasks.py
"""
Celery tasks for real-time market data streaming
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
import asyncio

from .service import streaming_engine, StreamStatus

logger = get_task_logger(__name__)


@shared_task(bind=True)
def start_streaming_engine(self):
    """Start the streaming engine via Celery"""
    try:
        if streaming_engine.status == StreamStatus.RUNNING:
            return {'status': 'already_running', 'active_symbols': len(streaming_engine.active_symbols)}
        
        # Run async start method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        success = loop.run_until_complete(streaming_engine.start())
        loop.close()
        
        if success:
            logger.info("Streaming engine started successfully")
            return {
                'status': 'started',
                'active_symbols': len(streaming_engine.active_symbols),
                'task_id': self.request.id
            }
        else:
            logger.error("Failed to start streaming engine")
            return {'status': 'failed', 'error': 'startup_failed'}
            
    except Exception as e:
        logger.error(f"Streaming engine start task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task(bind=True)
def stop_streaming_engine(self):
    """Stop the streaming engine via Celery"""
    try:
        # Run async stop method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(streaming_engine.stop())
        loop.close()
        
        logger.info("Streaming engine stopped successfully")
        return {'status': 'stopped', 'task_id': self.request.id}
        
    except Exception as e:
        logger.error(f"Streaming engine stop task failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def subscribe_to_symbols(symbols, high_frequency=False):
    """Subscribe to streaming data for symbols"""
    try:
        if not isinstance(symbols, list):
            symbols = [symbols]
        
        for symbol in symbols:
            streaming_engine.subscribe_symbol(symbol, high_frequency)
        
        logger.info(f"Subscribed to {len(symbols)} symbols: {symbols}")
        return {
            'status': 'subscribed',
            'symbols': symbols,
            'total_active': len(streaming_engine.active_symbols)
        }
        
    except Exception as e:
        logger.error(f"Symbol subscription failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def unsubscribe_from_symbols(symbols):
    """Unsubscribe from streaming data for symbols"""
    try:
        if not isinstance(symbols, list):
            symbols = [symbols]
        
        for symbol in symbols:
            streaming_engine.unsubscribe_symbol(symbol)
        
        logger.info(f"Unsubscribed from {len(symbols)} symbols: {symbols}")
        return {
            'status': 'unsubscribed',
            'symbols': symbols,
            'total_active': len(streaming_engine.active_symbols)
        }
        
    except Exception as e:
        logger.error(f"Symbol unsubscription failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def get_streaming_metrics():
    """Get streaming engine metrics"""
    try:
        metrics = streaming_engine.get_metrics()
        return {
            'status': 'success',
            'metrics': metrics,
            'timestamp': metrics['performance']['last_update']
        }
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def health_check_streaming():
    """Health check for streaming service"""
    try:
        metrics = streaming_engine.get_metrics()
        
        # Determine health based on metrics
        is_healthy = (
            streaming_engine.status == StreamStatus.RUNNING and
            metrics['performance']['data_quality'] in ['excellent', 'good'] and
            metrics['performance']['errors'] / max(1, metrics['performance']['quotes_processed']) < 0.1
        )
        
        return {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'engine_status': metrics['status'],
            'active_symbols': metrics['active_symbols'],
            'data_quality': metrics['performance']['data_quality'],
            'last_update': metrics['performance']['last_update']
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {'status': 'error', 'error': str(e)}
