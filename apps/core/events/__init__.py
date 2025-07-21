# apps/core/events/__init__.py
"""
Event system package for QSuite
"""

from .bus import (
    EventBus, EventPriority, EventStatus, BaseEvent,
    EventMiddleware, LoggingMiddleware, MetricsMiddleware,
    event_bus, event_handler
)

from .types import (
    MarketDataUpdatedEvent, TechnicalSignalEvent, OrderCreatedEvent,
    OrderFilledEvent, AlgorithmTriggeredEvent, RiskAlertEvent,
    PortfolioUpdatedEvent
)

from .utils import (
    publish_market_data_update, publish_technical_signal, 
    publish_algorithm_trigger
)

__all__ = [
    # Core event system
    'EventBus', 'EventPriority', 'EventStatus', 'BaseEvent',
    'EventMiddleware', 'LoggingMiddleware', 'MetricsMiddleware',
    'event_bus', 'event_handler',
    
    # Event types
    'MarketDataUpdatedEvent', 'TechnicalSignalEvent', 'OrderCreatedEvent',
    'OrderFilledEvent', 'AlgorithmTriggeredEvent', 'RiskAlertEvent', 
    'PortfolioUpdatedEvent',
    
    # Utilities
    'publish_market_data_update', 'publish_technical_signal',
    'publish_algorithm_trigger'
]
