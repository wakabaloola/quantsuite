# apps/core/events/types.py
"""
Event type definitions for the trading platform
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from .bus import BaseEvent, EventPriority


# Market Data Events
@dataclass
class MarketDataUpdatedEvent(BaseEvent):
    """Market data update event"""
    symbol: str = ""
    price_data: Dict[str, Decimal] = None
    volume: int = 0
    exchange: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "market_data.updated"
        if self.price_data is None:
            self.price_data = {}


@dataclass
class TechnicalSignalEvent(BaseEvent):
    """Technical analysis signal event"""
    symbol: str = ""
    indicator: str = ""
    signal_type: str = "neutral"  # 'buy', 'sell', 'neutral'
    signal_strength: float = 0.0  # 0.0 to 1.0
    indicator_value: float = 0.0
    threshold_crossed: bool = False
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "technical.signal"


# Order Management Events
@dataclass
class OrderCreatedEvent(BaseEvent):
    """Order creation event"""
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: int = 0
    price: Optional[Decimal] = None
    order_type: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "order.created"


@dataclass
class OrderFilledEvent(BaseEvent):
    """Order fill event"""
    order_id: str = ""
    symbol: str = ""
    quantity: int = 0
    price: Decimal = Decimal('0')
    fill_timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "order.filled"
        if self.fill_timestamp is None:
            from django.utils import timezone
            self.fill_timestamp = timezone.now()


@dataclass
class AlgorithmTriggeredEvent(BaseEvent):
    """Algorithm execution trigger event"""
    algo_order_id: str = ""
    algorithm_type: str = ""
    trigger_reason: str = ""
    execution_step: int = 0
    market_conditions: Dict[str, Any] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "algorithm.triggered"
        if self.market_conditions is None:
            self.market_conditions = {}


# Risk Management Events
@dataclass
class RiskAlertEvent(BaseEvent):
    """Risk management alert event"""
    alert_type: str = ""
    severity: str = "low"  # 'low', 'medium', 'high', 'critical'
    message: str = ""
    affected_positions: List[str] = None
    recommended_action: str = ""
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "risk.alert"
        if self.affected_positions is None:
            self.affected_positions = []


# Portfolio Events
@dataclass
class PortfolioUpdatedEvent(BaseEvent):
    """Portfolio value update event"""
    portfolio_id: int = 0
    total_value: Decimal = Decimal('0')
    daily_pnl: Decimal = Decimal('0')
    positions_count: int = 0
    performance_metrics: Dict[str, float] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.event_type = "portfolio.updated"
        if self.performance_metrics is None:
            self.performance_metrics = {}
