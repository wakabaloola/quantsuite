# apps/market_data/common.py
"""
Common data structures and types shared across market data modules
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Any
from enum import Enum


class StreamStatus(Enum):
    """Streaming service status"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    DEGRADED = "degraded"


class DataQuality(Enum):
    """Data quality levels"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


@dataclass
class MarketDataPoint:
    """Structured market data point"""
    symbol: str
    timestamp: datetime
    price: Decimal
    volume: int
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    high_24h: Optional[Decimal] = None
    low_24h: Optional[Decimal] = None
    change_24h: Optional[Decimal] = None
    change_pct_24h: Optional[float] = None
    market_cap: Optional[int] = None
    
    def to_cache_dict(self) -> Dict[str, Any]:
        """Convert to cache-friendly dictionary"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'price': str(self.price),
            'volume': self.volume,
            'bid': str(self.bid) if self.bid else None,
            'ask': str(self.ask) if self.ask else None,
            'high_24h': str(self.high_24h) if self.high_24h else None,
            'low_24h': str(self.low_24h) if self.low_24h else None,
            'change_24h': str(self.change_24h) if self.change_24h else None,
            'change_pct_24h': self.change_pct_24h,
            'market_cap': self.market_cap
        }
    
    @classmethod
    def from_cache_dict(cls, data: Dict[str, Any]) -> 'MarketDataPoint':
        """Create from cached dictionary"""
        return cls(
            symbol=data['symbol'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            price=Decimal(data['price']),
            volume=data['volume'],
            bid=Decimal(data['bid']) if data['bid'] else None,
            ask=Decimal(data['ask']) if data['ask'] else None,
            high_24h=Decimal(data['high_24h']) if data['high_24h'] else None,
            low_24h=Decimal(data['low_24h']) if data['low_24h'] else None,
            change_24h=Decimal(data['change_24h']) if data['change_24h'] else None,
            change_pct_24h=data['change_pct_24h'],
            market_cap=data['market_cap']
        )
