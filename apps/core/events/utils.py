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


async def publish_algorithm_execution_started(algo_order_id: str, algorithm_type: str,
                                            total_quantity: int, estimated_duration_minutes: int,
                                            execution_parameters: Dict[str, Any], user_id: int):
    """Publish algorithm execution started event"""
    from .types import AlgorithmExecutionStartedEvent

    event = AlgorithmExecutionStartedEvent(
        algo_order_id=algo_order_id,
        algorithm_type=algorithm_type,
        total_quantity=total_quantity,
        estimated_duration_minutes=estimated_duration_minutes,
        execution_parameters=execution_parameters,
        user_id=user_id,
        source_service="order_management"
    )

    return await event_bus.publish(event, broadcast_websocket=True)


async def publish_algorithm_execution_progress(algo_order_id: str, execution_step: int,
                                             total_steps: int, executed_quantity: int,
                                             remaining_quantity: int, average_execution_price: Optional[Decimal],
                                             current_slippage_bps: float, estimated_completion_time: Optional[datetime],
                                             user_id: int):
    """Publish algorithm execution progress event"""
    from .types import AlgorithmExecutionProgressEvent

    event = AlgorithmExecutionProgressEvent(
        algo_order_id=algo_order_id,
        execution_step=execution_step,
        total_steps=total_steps,
        executed_quantity=executed_quantity,
        remaining_quantity=remaining_quantity,
        average_execution_price=average_execution_price,
        current_slippage_bps=current_slippage_bps,
        estimated_completion_time=estimated_completion_time,
        user_id=user_id,
        source_service="order_management"
    )

    return await event_bus.publish(event, broadcast_websocket=True)


async def publish_algorithm_execution_completed(algo_order_id: str, final_status: str,
                                              total_executed_quantity: int, average_execution_price: Optional[Decimal],
                                              total_slippage_bps: float, implementation_shortfall: Optional[float],
                                              execution_duration_minutes: int, performance_metrics: Dict[str, Any],
                                              user_id: int):
    """Publish algorithm execution completed event"""
    from .types import AlgorithmExecutionCompletedEvent

    event = AlgorithmExecutionCompletedEvent(
        algo_order_id=algo_order_id,
        final_status=final_status,
        total_executed_quantity=total_executed_quantity,
        average_execution_price=average_execution_price,
        total_slippage_bps=total_slippage_bps,
        implementation_shortfall=implementation_shortfall,
        execution_duration_minutes=execution_duration_minutes,
        performance_metrics=performance_metrics,
        user_id=user_id,
        source_service="order_management"
    )

    return await event_bus.publish(event, broadcast_websocket=True)


async def publish_algorithm_execution_error(algo_order_id: str, error_type: str,
                                          error_message: str, execution_step: int,
                                          recovery_action: str, user_id: int):
    """Publish algorithm execution error event"""
    from .types import AlgorithmExecutionErrorEvent

    event = AlgorithmExecutionErrorEvent(
        algo_order_id=algo_order_id,
        error_type=error_type,
        error_message=error_message,
        execution_step=execution_step,
        recovery_action=recovery_action,
        user_id=user_id,
        source_service="order_management"
    )

    return await event_bus.publish(event, broadcast_websocket=True)
