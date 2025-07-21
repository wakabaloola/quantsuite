#!/usr/bin/env python3
"""
Event System Test Script
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Now import your modules
from apps.core.events import (
    MarketDataUpdatedEvent,
    EventPriority,
    event_bus,
    publish_market_data_update
)

async def main():
    # Rest of your script remains the same...
    print("\n=== Testing Event Creation ===")
    event = MarketDataUpdatedEvent(
        symbol="AAPL",
        price_data={"close": Decimal("150.00"), "volume": 1000},
        volume=1000,
        exchange="NASDAQ"
    )

    print(f"✅ Event created: {event.symbol} - {event.event_id}")
    print(f"✅ Event type: {event.event_type}")
    print(f"✅ Priority: {event.priority}")

    # 2. Test event handler registration
    print("\n=== Testing Handler Registration ===")
    received_events = []

    async def market_data_handler(event):
        received_events.append(f"Received: {event.symbol} @ {event.timestamp}")
        print(f"📊 Handler processed: {event.symbol}")

    event_bus.subscribe("market_data.updated", market_data_handler)
    print(f"✅ Handler subscribed. Total handlers: {len(event_bus.handlers)}")

    # 3. Test event publishing
    print("\n=== Testing Event Publishing ===")
    result = await event_bus.publish(event, broadcast_websocket=False, queue_celery=False)
    print(f"✅ Event published successfully: {result}")
    print(f"✅ Events received: {len(received_events)}")
    if received_events:
        print(f"📨 Last received: {received_events[-1]}")

    # 4. Test utility functions
    print("\n=== Testing Utility Function ===")
    utility_result = await publish_market_data_update(
        symbol="GOOGL",
        price_data={"close": Decimal("2500.00")},
        volume=500,
        exchange="NASDAQ"
    )
    print(f"✅ Utility function worked: {utility_result}")

    # 5. Check metrics
    print("\n=== Checking Metrics ===")
    metrics = event_bus.get_metrics()
    print(f"✅ Event system metrics: {metrics}")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()

