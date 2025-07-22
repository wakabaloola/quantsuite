# apps/core/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger

# Update import path
from .events import BaseEvent, event_bus

import logging
from datetime import timedelta
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3)
def process_event(self, event_data):
    """Process events via Celery for async handling"""
    try:
        # Reconstruct event from data
        event = BaseEvent.from_dict(event_data)

        # Process through event bus
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            event_bus._publish_to_handlers(event)
        )
        loop.close()

        return {'status': 'success', 'event_id': event.event_id}

    except Exception as exc:
        logger.error(f"Event processing failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=exc)
        return {'status': 'failed', 'error': str(exc)}

@shared_task
def monitor_websocket_performance():
    """Monitor WebSocket performance and broadcast metrics"""
    try:
        from .websockets.connection_manager import connection_manager
        
        # Get current metrics
        metrics = connection_manager.get_metrics()
        
        # Add timestamp
        metrics['timestamp'] = timezone.now().isoformat()
        
        # Broadcast to monitoring consumers
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)('websocket_monitoring', {
                'type': 'metrics_broadcast',
                'data': metrics
            })
        
        # Log summary
        logger.info(
            f"WebSocket metrics: "
            f"{metrics['connections']['active']} active connections, "
            f"{metrics['messages']['total_sent']} messages sent, "
            f"{metrics['queues']['total_queued_messages']} queued messages"
        )
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error monitoring WebSocket performance: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_websocket_connections():
    """Clean up stale WebSocket connections"""
    try:
        from .websockets.connection_manager import connection_manager
        
        # Run connection cleanup
        async_to_sync(connection_manager.cleanup_stale_connections)()
        
        # Get updated metrics
        metrics = connection_manager.get_metrics()
        
        logger.info(f"WebSocket cleanup completed: {metrics['connections']['active']} active connections")
        return metrics
        
    except Exception as e:
        logger.error(f"Error cleaning up WebSocket connections: {e}")
        return {'error': str(e)}


@shared_task
def websocket_health_check():
    """Perform WebSocket system health check"""
    try:
        from .websockets.connection_manager import connection_manager
        
        metrics = connection_manager.get_metrics()
        
        # Define health thresholds
        max_connections = 1000
        max_error_rate = 0.05
        max_queue_size = 500
        
        health_status = {
            'healthy': True,
            'warnings': [],
            'errors': [],
            'metrics': metrics,
            'timestamp': timezone.now().isoformat()
        }
        
        # Check connection limits
        if metrics['connections']['active'] > max_connections:
            health_status['warnings'].append(
                f"High connection count: {metrics['connections']['active']}"
            )
        
        # Check error rates
        if metrics['messages']['error_rate'] > max_error_rate:
            health_status['errors'].append(
                f"High error rate: {metrics['messages']['error_rate']:.2%}"
            )
            health_status['healthy'] = False
        
        # Check queue sizes
        if metrics['queues']['total_queued_messages'] > max_queue_size:
            health_status['warnings'].append(
                f"High message queue size: {metrics['queues']['total_queued_messages']}"
            )
        
        # Log health status
        if not health_status['healthy']:
            logger.error(f"WebSocket health check failed: {health_status['errors']}")
        elif health_status['warnings']:
            logger.warning(f"WebSocket health warnings: {health_status['warnings']}")
        else:
            logger.info("WebSocket health check passed")
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error performing WebSocket health check: {e}")
        return {
            'healthy': False,
            'errors': [str(e)],
            'timestamp': timezone.now().isoformat()
        }
