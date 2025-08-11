# apps/core/events/__init__.py
"""
Event system package for QSuite.
This file defines the public API of the events module, preventing circular imports.
"""

# Import base classes and enums from the base.py file
from .base import BaseEvent, EventPriority, EventStatus

# Import the bus, handlers, and helpers from their specific modules
from .bus import event_bus, event_handler, publish_risk_alert
from .types import (
    MarketDataUpdatedEvent, TechnicalSignalEvent, OrderCreatedEvent,
    OrderFilledEvent, AlgorithmTriggeredEvent, RiskAlertEvent,
    PortfolioUpdatedEvent
)

# Import and expose the utility functions so other apps can use them
from .utils import (
    publish_market_data_update,
    publish_technical_signal,
    publish_algorithm_trigger,
    publish_algorithm_execution_started,
    publish_algorithm_execution_progress,
    publish_algorithm_execution_completed,
    publish_algorithm_execution_error
)


# This makes the most important components available directly from the 'events' package
__all__ = [
    # Core event system from base.py and bus.py
    'BaseEvent',
    'EventPriority',
    'EventStatus',
    'event_bus',
    'event_handler',
    'publish_risk_alert',
    
    # Event types from types.py
    'MarketDataUpdatedEvent',
    'TechnicalSignalEvent',
    'OrderCreatedEvent',
    'OrderFilledEvent',
    'AlgorithmTriggeredEvent',
    'RiskAlertEvent',
    'PortfolioUpdatedEvent',

    # Utility functions from utils.py
    'publish_market_data_update',
    'publish_technical_signal',
    'publish_algorithm_trigger',
    'publish_algorithm_execution_started',
    'publish_algorithm_execution_progress',
    'publish_algorithm_execution_completed',
    'publish_algorithm_execution_error',
]

