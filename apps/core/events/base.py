# apps/core/events/base.py
"""
Base classes and enums for the event system.
This file exists to prevent circular imports between bus.py and types.py.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from django.utils import timezone as django_timezone


class EventPriority(Enum):
    """Event priority levels for processing order"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


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
    event_id: str = ""
    event_type: str = ""
    timestamp: Optional[datetime] = None
    priority: EventPriority = EventPriority.NORMAL
    source_service: str = ""
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
        data['priority'] = self.priority.name
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseEvent':
        """Create event from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['priority'] = EventPriority[data['priority']]
        cls_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in cls_fields}
        return cls(**filtered_data)

