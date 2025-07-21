# apps/core/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger

# Update import path
from .events import BaseEvent, event_bus

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
