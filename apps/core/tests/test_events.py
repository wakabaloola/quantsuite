# apps/core/tests/test_events.py
import asyncio
import pytest
from django.test import TestCase
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from django.utils import timezone

# Update imports to use the new module structure
from apps.core.events import (
    event_bus, MarketDataUpdatedEvent, EventPriority,
    publish_market_data_update
)

class EventSystemTests(TestCase):
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Clear any existing handlers
        event_bus.handlers.clear()
    
    def tearDown(self):
        self.loop.close()
    
    def test_event_creation(self):
        """Test basic event creation and validation"""
        event = MarketDataUpdatedEvent(
            event_id="test-123",
            event_type="market_data.updated",
            timestamp=timezone.now(),
            priority=EventPriority.CRITICAL,
            source_service="test_service",
            symbol="AAPL",
            price_data={"close": Decimal("150.00")},
            volume=1000,
            exchange="NASDAQ"
        )
        
        self.assertEqual(event.symbol, "AAPL")
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.priority, EventPriority.CRITICAL)
        self.assertEqual(event.event_type, "market_data.updated")
    
    def test_event_creation_with_defaults(self):
        """Test event creation with default values"""
        event = MarketDataUpdatedEvent()
        
        # Check that post_init ran
        self.assertIsNotNone(event.event_id)
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.event_type, "market_data.updated")
        self.assertEqual(event.symbol, "")  # Default value
        self.assertEqual(event.volume, 0)  # Default value
    
    def test_event_handler_subscription(self):
        """Test event handler registration"""
        handler_called = []
        
        async def test_handler(event):
            handler_called.append(event.event_id)
        
        event_bus.subscribe("test.event", test_handler)
        
        # Verify handler was registered
        self.assertIn("test.event", event_bus.handlers)
        self.assertEqual(len(event_bus.handlers["test.event"]), 1)
    
    @patch('apps.core.events.bus.cache')
    def test_event_publishing(self, mock_cache):
        """Test event publishing workflow"""
        async def run_test():
            mock_cache.get.return_value = []
            mock_cache.set.return_value = True
            
            result = await publish_market_data_update(
                symbol="AAPL",
                price_data={"close": Decimal("150.00")},
                volume=1000,
                exchange="NASDAQ"
            )
            
            self.assertTrue(result)
        
        self.loop.run_until_complete(run_test())
    
    def test_event_serialization(self):
        """Test event to_dict and from_dict methods"""
        # Test with BaseEvent directly
        from apps.core.events import BaseEvent
        from django.utils import timezone
        
        original_event = BaseEvent(
            event_id="test-123",
            event_type="test.event",
            timestamp=timezone.now(),
            priority=EventPriority.NORMAL,
            source_service="test_service",
            user_id=123,
            metadata={"test": "data"}
        )
        
        # Test serialization
        event_dict = original_event.to_dict()
        self.assertIn('event_id', event_dict)
        self.assertIn('timestamp', event_dict)
        self.assertIn('priority', event_dict)
        self.assertEqual(event_dict['event_id'], "test-123")
        self.assertEqual(event_dict['user_id'], 123)
        
        # Test deserialization
        deserialized_event = BaseEvent.from_dict(event_dict)
        self.assertEqual(deserialized_event.event_id, original_event.event_id)
        self.assertEqual(deserialized_event.event_type, original_event.event_type)
        self.assertEqual(deserialized_event.user_id, original_event.user_id)
    
    def test_market_data_event_serialization(self):
        """Test MarketDataUpdatedEvent specific serialization"""
        from decimal import Decimal
        
        original_event = MarketDataUpdatedEvent(
            symbol="AAPL",
            price_data={"close": Decimal("150.00")},
            volume=1000,
            exchange="NASDAQ"
        )
        
        # Test that event can be serialized
        event_dict = original_event.to_dict()
        self.assertIn('symbol', event_dict)
        self.assertIn('volume', event_dict)
        self.assertEqual(event_dict['symbol'], "AAPL")
        self.assertEqual(event_dict['volume'], 1000)
        
        # Test that timestamp and priority are properly set
        self.assertIn('timestamp', event_dict)
        self.assertIn('priority', event_dict)
