#!/usr/bin/env python3
"""
Streaming System Test Script
"""

import asyncio
import sys
import os
from pathlib import Path
from decimal import Decimal

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Initialize Django first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qsuite.settings')
import django
django.setup()

# Now import your modules
from apps.market_data.streaming import streaming_engine
from apps.market_data.streaming.service import MarketDataPoint
from django.utils import timezone

async def main():
    """Main async test function"""
    
    print("\n=== Testing Streaming Engine Initialization ===")
    print(f"✅ Engine status: {streaming_engine.status}")
    print(f"✅ Active symbols: {len(streaming_engine.active_symbols)}")

    # 1. Test symbol subscription
    print("\n=== Testing Symbol Subscription ===")
    # Handle both async and non-async versions
    if hasattr(streaming_engine.subscribe_symbol, '__call__'):
        # Non-async version
        streaming_engine.subscribe_symbol("AAPL", high_frequency=True)
        streaming_engine.subscribe_symbol("GOOGL", high_frequency=False)
    else:
        # Async version
        await streaming_engine.subscribe_symbol("AAPL", high_frequency=True)
        await streaming_engine.subscribe_symbol("GOOGL", high_frequency=False)
    
    active_symbols = streaming_engine.get_active_symbols()
    print(f"✅ Subscribed to symbols: {active_symbols}")

    # 2. Test metrics collection
    print("\n=== Testing Metrics Collection ===")
    if hasattr(streaming_engine.get_metrics, '__call__'):
        metrics = streaming_engine.get_metrics()
    else:
        metrics = await streaming_engine.get_metrics()
    
    print(f"✅ Performance metrics:")
    print(f"   - Active symbols: {metrics['active_symbols']}")
    print(f"   - High frequency: {metrics['high_frequency_symbols']}")
    print(f"   - Status: {metrics['status']}")
    print(f"   - Cache hit ratio: {metrics['cache_stats']['hit_ratio']:.1%}")

    # 3. Test cache operations
    print("\n=== Testing Cache Operations ===")
    test_quote = MarketDataPoint(
        symbol="AAPL",
        timestamp=timezone.now(),
        price=Decimal("150.25"),
        volume=5000,
        bid=Decimal("150.20"),
        ask=Decimal("150.30")
    )

    if hasattr(streaming_engine.cache_manager.set_quote, '__call__'):
        success = streaming_engine.cache_manager.set_quote(test_quote, is_high_frequency=True)
    else:
        success = await streaming_engine.cache_manager.set_quote(test_quote, is_high_frequency=True)
    print(f"✅ Cache set success: {success}")

    if hasattr(streaming_engine.cache_manager.get_quote, '__call__'):
        cached_quote = streaming_engine.cache_manager.get_quote("AAPL")
    else:
        cached_quote = await streaming_engine.cache_manager.get_quote("AAPL")
    
    if cached_quote:
        print(f"✅ Retrieved quote: {cached_quote.symbol} @ ${cached_quote.price}")
    else:
        print("⚠️  Quote not in cache")

    if hasattr(streaming_engine.cache_manager.get_cache_stats, '__call__'):
        cache_stats = streaming_engine.cache_manager.get_cache_stats()
    else:
        cache_stats = await streaming_engine.cache_manager.get_cache_stats()
    print(f"✅ Cache stats: {cache_stats}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
    finally:
        loop.close()
