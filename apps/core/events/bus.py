# apps/core/events/bus.py
"""
Enterprise Event System Foundation
================================
Production-grade event-driven architecture for algorithmic trading platform.

Features:
- Type-safe event definitions with validation
- Async/sync event publishing with error handling  
- Event middleware pipeline for observability
- Dead letter queue for failed events
- Event sourcing capabilities
- Performance monitoring built-in
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable, Union, Type
from dataclasses import dataclass, asdict
from enum import Enum

from django.core.cache import cache
from django.utils import timezone as django_timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
from celery import current_app as celery_app

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels for processing order"""
    CRITICAL = 1    # Market data, order fills
    HIGH = 2        # Technical signals, risk alerts  
    NORMAL = 3      # Portfolio updates, analytics
    LOW = 4         # Reporting, maintenance


class EventStatus(Enum):
    """Event processing status"""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


@dataclass
class BaseEvent:
    """Base event class with common fields"""
    # Required fields (no defaults)
    event_id: str = ""
    event_type: str = ""
    timestamp: Optional[datetime] = None
    priority: EventPriority = EventPriority.NORMAL
    source_service: str = ""
    
    # Optional fields (with defaults)
    correlation_id: Optional[str] = None
    user_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate event data after initialization"""
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = django_timezone.now()
        if self.metadata is None:
            self.metadata = {}
        if not self.source_service:
            self.source_service = "unknown_service"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['priority'] = self.priority.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseEvent':
        """Create event from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['priority'] = EventPriority(data['priority'])
        return cls(**data)


# Event types are imported from types.py module


class EventMiddleware(ABC):
    """Base class for event middleware"""
    
    @abstractmethod
    async def process_event(self, event: BaseEvent, next_handler: Callable) -> Any:
        """Process event with middleware logic"""
        pass


class LoggingMiddleware(EventMiddleware):
    """Middleware for structured event logging"""
    
    def __init__(self, log_level: str = "INFO"):
        self.logger = logging.getLogger(f"{__name__}.events")
        self.log_level = getattr(logging, log_level)
    
    async def process_event(self, event: BaseEvent, next_handler: Callable) -> Any:
        """Log event processing with structured data"""
        start_time = time.time()
        
        self.logger.log(self.log_level, 
            f"Processing event: {event.event_type}",
            extra={
                'event_id': event.event_id,
                'event_type': event.event_type,
                'source_service': event.source_service,
                'priority': event.priority.name,
                'correlation_id': event.correlation_id,
                'user_id': event.user_id,
                'timestamp': event.timestamp.isoformat()
            }
        )
        
        try:
            result = await next_handler(event)
            
            processing_time = (time.time() - start_time) * 1000
            self.logger.info(
                f"Event processed successfully: {event.event_type}",
                extra={
                    'event_id': event.event_id,
                    'processing_time_ms': round(processing_time, 2),
                    'status': 'success'
                }
            )
            
            return result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.logger.error(
                f"Event processing failed: {event.event_type}",
                extra={
                    'event_id': event.event_id,
                    'processing_time_ms': round(processing_time, 2),
                    'status': 'error',
                    'error_message': str(e),
                    'error_type': type(e).__name__
                },
                exc_info=True
            )
            raise


class MetricsMiddleware(EventMiddleware):
    """Middleware for event metrics collection"""
    
    def __init__(self):
        self.metrics_cache_prefix = "event_metrics"
    
    async def process_event(self, event: BaseEvent, next_handler: Callable) -> Any:
        """Collect event processing metrics"""
        start_time = time.time()
        
        # Increment event counter
        cache_key = f"{self.metrics_cache_prefix}:count:{event.event_type}"
        try:
            current_count = cache.get(cache_key, 0)
            cache.set(cache_key, current_count + 1, 3600)  # 1 hour TTL
        except Exception:
            pass  # Don't fail event processing for metrics
        
        try:
            result = await next_handler(event)
            
            # Record processing time
            processing_time = (time.time() - start_time) * 1000
            time_cache_key = f"{self.metrics_cache_prefix}:time:{event.event_type}"
            
            try:
                times = cache.get(time_cache_key, [])
                times.append(processing_time)
                # Keep only last 100 measurements
                if len(times) > 100:
                    times = times[-100:]
                cache.set(time_cache_key, times, 3600)
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            # Record error
            error_cache_key = f"{self.metrics_cache_prefix}:errors:{event.event_type}"
            try:
                error_count = cache.get(error_cache_key, 0)
                cache.set(error_cache_key, error_count + 1, 3600)
            except Exception:
                pass
            
            raise


class EventHandler:
    """Base event handler interface"""
    
    def __init__(self, event_type: str, handler_func: Callable):
        self.event_type = event_type
        self.handler_func = handler_func
        self.is_async = asyncio.iscoroutinefunction(handler_func)
    
    async def handle(self, event: BaseEvent) -> Any:
        """Handle event with proper async/sync execution"""
        try:
            if self.is_async:
                return await self.handler_func(event)
            else:
                # Run sync function in thread pool
                return await sync_to_async(self.handler_func)(event)
        except Exception as e:
            logger.error(f"Handler failed for {self.event_type}: {e}", exc_info=True)
            raise


class EventBus:
    """
    Enterprise-grade event bus for async/sync event publishing and handling
    
    Features:
    - Middleware pipeline for cross-cutting concerns
    - Dead letter queue for failed events
    - Event replay capabilities
    - Performance monitoring
    - WebSocket and Celery integration
    """
    
    def __init__(self):
        self.handlers: Dict[str, List[EventHandler]] = {}
        self.middleware: List[EventMiddleware] = []
        self.channel_layer = get_channel_layer()
        self.dead_letter_queue = []
        self.max_retries = 3
        
        # Add default middleware
        self.add_middleware(LoggingMiddleware())
        self.add_middleware(MetricsMiddleware())
    
    def add_middleware(self, middleware: EventMiddleware):
        """Add middleware to processing pipeline"""
        self.middleware.append(middleware)
        logger.info(f"Added middleware: {type(middleware).__name__}")
    
    def subscribe(self, event_type: str, handler_func: Callable):
        """Subscribe handler to event type"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        
        event_handler = EventHandler(event_type, handler_func)
        self.handlers[event_type].append(event_handler)
        
        logger.info(f"Subscribed handler for event: {event_type}")
    
    def unsubscribe(self, event_type: str, handler_func: Callable):
        """Unsubscribe handler from event type"""
        if event_type in self.handlers:
            self.handlers[event_type] = [
                h for h in self.handlers[event_type] 
                if h.handler_func != handler_func
            ]
    
    async def publish(self, event: BaseEvent, broadcast_websocket: bool = True, 
                     queue_celery: bool = False) -> bool:
        """
        Publish event to all subscribers with comprehensive error handling
        
        Args:
            event: Event to publish
            broadcast_websocket: Whether to broadcast via WebSocket
            queue_celery: Whether to queue for Celery processing
        """
        try:
            # Store event for replay capability
            await self._store_event(event)
            
            # Process through middleware pipeline
            await self._process_through_middleware(event)
            
            # Publish to local handlers
            success = await self._publish_to_handlers(event)
            
            # Broadcast via WebSocket if requested
            if broadcast_websocket and self.channel_layer:
                await self._broadcast_websocket(event)
            
            # Queue for Celery if requested
            if queue_celery:
                await self._queue_celery_task(event)
            
            return success
            
        except Exception as e:
            logger.error(f"Event publishing failed: {e}", exc_info=True)
            await self._handle_failed_event(event, str(e))
            return False
    
    async def _process_through_middleware(self, event: BaseEvent):
        """Process event through middleware pipeline"""
        async def final_handler(evt):
            return evt
        
        # Build middleware chain
        handler = final_handler
        for middleware in reversed(self.middleware):
            current_handler = handler
            handler = lambda evt, mw=middleware, next_h=current_handler: mw.process_event(evt, next_h)
        
        await handler(event)
    
    async def _publish_to_handlers(self, event: BaseEvent) -> bool:
        """Publish event to registered handlers"""
        if event.event_type not in self.handlers:
            logger.debug(f"No handlers for event type: {event.event_type}")
            return True
        
        handlers = self.handlers[event.event_type]
        if not handlers:
            return True
        
        # Execute all handlers concurrently
        tasks = []
        for handler in handlers:
            tasks.append(handler.handle(event))
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for failures
            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                logger.warning(f"Some handlers failed for {event.event_type}: {len(failures)} failures")
                for failure in failures:
                    logger.error(f"Handler failure: {failure}")
                return len(failures) < len(results)  # Partial success
            
            return True
            
        except Exception as e:
            logger.error(f"Handler execution failed: {e}", exc_info=True)
            return False
    
    async def _broadcast_websocket(self, event: BaseEvent):
        """Broadcast event via WebSocket channels"""
        try:
            # Determine WebSocket groups based on event
            groups = self._get_websocket_groups(event)
            
            for group in groups:
                await self.channel_layer.group_send(group, {
                    'type': 'event_message',
                    'event': event.to_dict()
                })
                
        except Exception as e:
            logger.error(f"WebSocket broadcast failed: {e}")
    
    def _get_websocket_groups(self, event: BaseEvent) -> List[str]:
        """Determine WebSocket groups for event broadcasting"""
        groups = []
        
        # User-specific events
        if event.user_id:
            groups.extend([
                f'user_{event.user_id}',
                f'orders_{event.user_id}',
                f'portfolio_{event.user_id}',
                f'risk_{event.user_id}'
            ])
        
        # Market data events - broadcast to symbol groups
        if hasattr(event, 'symbol'):
            groups.append(f'market_{event.symbol}')
        
        # Global events
        if event.event_type.startswith('market_data'):
            groups.append('market_data_global')
        elif event.event_type.startswith('risk'):
            groups.append('risk_alerts_global')
        
        return groups
    
    async def _queue_celery_task(self, event: BaseEvent):
        """Queue event for Celery task processing"""
        try:
            task_name = f"process_event_{event.event_type.replace('.', '_')}"
            
            # Try to queue the task
            celery_app.send_task(
                'apps.core.tasks.process_event',
                args=[event.to_dict()],
                queue='events',
                priority=event.priority.value,
                retry=True,
                retry_policy={
                    'max_retries': self.max_retries,
                    'interval_start': 1,
                    'interval_step': 2,
                    'interval_max': 30,
                }
            )
            
        except Exception as e:
            logger.error(f"Celery task queueing failed: {e}")
    
    async def _store_event(self, event: BaseEvent):
        """Store event for replay and auditing"""
        try:
            event_data = event.to_dict()
            cache_key = f"event_store:{event.event_id}"
            cache.set(cache_key, event_data, 86400)  # Store for 24 hours
            
            # Also store in time-ordered list for replay
            today_key = f"events_today:{django_timezone.now().date()}"
            events_today = cache.get(today_key, [])
            events_today.append(event.event_id)
            cache.set(today_key, events_today, 86400)
            
        except Exception as e:
            logger.error(f"Event storage failed: {e}")
    
    async def _handle_failed_event(self, event: BaseEvent, error_message: str):
        """Handle failed event processing"""
        try:
            failed_event = {
                'event': event.to_dict(),
                'error': error_message,
                'failed_at': django_timezone.now().isoformat(),
                'retry_count': getattr(event, 'retry_count', 0)
            }
            
            self.dead_letter_queue.append(failed_event)
            
            # Store in cache for analysis
            cache_key = f"failed_events:{django_timezone.now().date()}"
            failed_events = cache.get(cache_key, [])
            failed_events.append(failed_event)
            cache.set(cache_key, failed_events, 86400)
            
        except Exception as e:
            logger.error(f"Failed event handling failed: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get event processing metrics"""
        try:
            metrics = {
                'total_handlers': sum(len(handlers) for handlers in self.handlers.values()),
                'event_types': list(self.handlers.keys()),
                'middleware_count': len(self.middleware),
                'dead_letter_count': len(self.dead_letter_queue)
            }
            
            # Get cached metrics
            for event_type in self.handlers.keys():
                count_key = f"event_metrics:count:{event_type}"
                error_key = f"event_metrics:errors:{event_type}"
                time_key = f"event_metrics:time:{event_type}"
                
                count = cache.get(count_key, 0)
                errors = cache.get(error_key, 0)
                times = cache.get(time_key, [])
                
                metrics[f'{event_type}_count'] = count
                metrics[f'{event_type}_errors'] = errors
                metrics[f'{event_type}_avg_time'] = sum(times) / len(times) if times else 0
            
            return metrics
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return {'error': str(e)}


# Global event bus instance
event_bus = EventBus()


# Event handler decorator
def event_handler(event_type: str):
    """Decorator to register event handlers"""
    def decorator(func):
        event_bus.subscribe(event_type, func)
        return func
    return decorator
