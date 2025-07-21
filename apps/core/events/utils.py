# apps/core/events/utils.py
"""
Utility functions for common event operations
"""

import uuid
from decimal import Decimal
from typing import Dict, Optional, Any
from django.utils import timezone

from .bus import event_bus, EventPriority
from .types import (
    MarketDataUpdatedEvent, TechnicalSignalEvent, AlgorithmTriggeredEvent
)


async def publish_market_data_update(symbol: str, price_data: Dict[str, Decimal], 
                                   volume: int, exchange: str, user_id: Optional[int] = None):
    """Utility to publish market data update event"""
    event = MarketDataUpdatedEvent(
        event_id=str(uuid.uuid4()),
        event_type="market_data.updated",
        timestamp=timezone.now(),
        priority=EventPriority.CRITICAL,
        source_service="market_data_service",
        user_id=user_id,
        symbol=symbol,
        price_data=price_data,
        volume=volume,
        exchange=exchange
    )
    
    return await event_bus.publish(event, broadcast_websocket=True, queue_celery=True)


async def publish_technical_signal(symbol: str, indicator: str, signal_type: str,
                                 signal_strength: float, indicator_value: float,
                                 user_id: Optional[int] = None):
    """Utility to publish technical analysis signal"""
    event = TechnicalSignalEvent(
        event_id=str(uuid.uuid4()),
        event_type="technical.signal",
        timestamp=timezone.now(),
        priority=EventPriority.HIGH,
        source_service="technical_analysis_service",
        user_id=user_id,
        symbol=symbol,
        indicator=indicator,
        signal_type=signal_type,
        signal_strength=signal_strength,
        indicator_value=indicator_value,
        threshold_crossed=signal_strength > 0.7  # Strong signal threshold
    )
    
    return await event_bus.publish(event, broadcast_websocket=True, queue_celery=True)


async def publish_algorithm_trigger(algo_order_id: str, algorithm_type: str,
                                  trigger_reason: str, execution_step: int,
                                  market_conditions: Dict[str, Any], user_id: int):
    """Utility to publish algorithm execution trigger"""
    event = AlgorithmTriggeredEvent(
        event_id=str(uuid.uuid4()),
        event_type="algorithm.triggered",
        timestamp=timezone.now(),
        priority=EventPriority.HIGH,
        source_service="algorithm_execution_service",
        user_id=user_id,
        algo_order_id=algo_order_id,
        algorithm_type=algorithm_type,
        trigger_reason=trigger_reason,
        execution_step=execution_step,
        market_conditions=market_conditions
    )
    
    return await event_bus.publish(event, broadcast_websocket=True, queue_celery=True)
