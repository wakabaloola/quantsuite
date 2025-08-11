# apps/core/events/bus.py
"""
Enterprise Event System Foundation
"""

import asyncio
import logging
from typing import Dict, List, Any, Callable

from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async
from celery import current_app as celery_app

from .base import BaseEvent
from .types import RiskAlertEvent

logger = logging.getLogger(__name__)


class EventHandler:
    """Wrapper for event handler functions"""
    def __init__(self, event_type: str, handler_func: Callable):
        self.event_type = event_type
        self.handler_func = handler_func
        self.is_async = asyncio.iscoroutinefunction(handler_func)

    async def handle(self, event: BaseEvent) -> Any:
        if self.is_async:
            return await self.handler_func(event)
        else:
            return await sync_to_async(self.handler_func)(event)


class EventBus:
    """Enterprise-grade event bus"""
    def __init__(self):
        self.handlers: Dict[str, List[EventHandler]] = {}
        self.channel_layer = get_channel_layer()

    def subscribe(self, event_type: str, handler_func: Callable):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(EventHandler(event_type, handler_func))
        logger.info(f"Subscribed handler for event: {event_type}")

    async def publish(self, event: BaseEvent, broadcast_websocket: bool = True, queue_celery: bool = False):
        """Publish event to all subscribers."""
        try:
            await self._publish_to_handlers(event)
            if broadcast_websocket and self.channel_layer:
                await self._broadcast_websocket(event)
            if queue_celery:
                self._queue_celery_task(event)
        except Exception as e:
            logger.error(f"Event publishing failed: {e}", exc_info=True)

    async def _publish_to_handlers(self, event: BaseEvent):
        if event.event_type in self.handlers:
            tasks = [h.handle(event) for h in self.handlers[event.event_type]]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _broadcast_websocket(self, event: BaseEvent):
        groups = self._get_websocket_groups(event)
        for group in groups:
            await self.channel_layer.group_send(group, {
                'type': 'event_message',
                'event': event.to_dict()
            })

    def _get_websocket_groups(self, event: BaseEvent) -> List[str]:
        groups = []
        if event.user_id:
            groups.append(f'user_{event.user_id}')
        if hasattr(event, 'symbol'):
            groups.append(f'market_{event.symbol}')
        return list(set(groups))
    
    def _queue_celery_task(self, event: BaseEvent):
        """Queue event for Celery task processing"""
        try:
            # A generic task to process events
            celery_app.send_task('apps.core.tasks.process_event', args=[event.to_dict()], queue='events')
        except Exception as e:
            logger.error(f"Celery task queueing failed: {e}")

# Global instance
event_bus = EventBus()

def event_handler(event_type: str):
    def decorator(func):
        event_bus.subscribe(event_type, func)
        return func
    return decorator

async def publish_risk_alert(user_id: int, alert_type: str, severity: str, message: str, **kwargs):
    """Creates and publishes a RiskAlertEvent."""
    event = RiskAlertEvent(
        user_id=user_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        source_service="risk_management_service",
        metadata=kwargs
    )
    await event_bus.publish(event)

