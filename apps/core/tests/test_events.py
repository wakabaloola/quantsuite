# apps/core/tests/test_events.py

import asyncio
from django.test import TestCase
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.utils import timezone


# Assuming these are your correct imports from your file
from apps.core.events import (
    event_bus, MarketDataUpdatedEvent, EventPriority, BaseEvent
)

class EventSystemTests(TestCase):
    
    def setUp(self):
        # Your setUp is fine, but using Django's TestCase doesn't require manual loop management
        # for many async operations, especially with modern Django. This is okay, though.
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Clear any existing handlers
        event_bus.handlers.clear()
    
    def tearDown(self):
        self.loop.close()
    
    def test_event_creation(self):
        """Test basic event creation and validation"""
        # THIS TEST IS GOOD AND NECESSARY
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
        # THIS TEST IS GOOD AND NECESSARY
        event = MarketDataUpdatedEvent()
        
        # Check that post_init ran
        self.assertIsNotNone(event.event_id)
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.event_type, "market_data.updated")
        self.assertEqual(event.symbol, "")  # Default value
        self.assertEqual(event.volume, 0)  # Default value
    
    def test_event_handler_subscription(self):
        """Test event handler registration"""
        # THIS TEST IS GOOD AND NECESSARY
        handler_called = []
        
        async def test_handler(event):
            handler_called.append(event.event_id)
        
        event_bus.subscribe("test.event", test_handler)
        
        # Verify handler was registered
        self.assertIn("test.event", event_bus.handlers)
        self.assertEqual(len(event_bus.handlers["test.event"]), 1)
    

    @patch('apps.core.events.event_bus.publish', new_callable=MagicMock)
    def test_event_publishing(self, mock_publish):
        """Test that publishing an event calls the bus's publish method."""
        print("📡 Testing Event Publishing...")

        # Create a test event instance
        test_event = BaseEvent(event_type='TEST_EVENT', metadata={'key': 'value'})

        # Action: Call the publish method on the event_bus instance
        event_bus.publish(test_event)

        # Assert: Check that our mocked publish method was called exactly once with the event
        mock_publish.assert_called_once_with(test_event)
        print("✅ Event publishing test passed")

    def test_event_serialization(self):
        """Test event to_dict and from_dict methods"""
        # THIS TEST IS GOOD AND NECESSARY
        original_event = BaseEvent(
            event_id="test-123",
            event_type="test.event",
            timestamp=timezone.now(),
            priority=EventPriority.NORMAL,
            source_service="test_service",
            user_id=123,
            metadata={"test": "data"}
        )
        
        event_dict = original_event.to_dict()
        self.assertIn('event_id', event_dict)
        self.assertEqual(event_dict['event_id'], "test-123")
        
        deserialized_event = BaseEvent.from_dict(event_dict)
        self.assertEqual(deserialized_event.event_id, original_event.event_id)

    def test_market_data_event_serialization(self):
        """Test MarketDataUpdatedEvent specific serialization"""
        # THIS TEST IS GOOD AND NECESSARY
        original_event = MarketDataUpdatedEvent(
            symbol="AAPL",
            price_data={"close": Decimal("150.00")},
            volume=1000,
            exchange="NASDAQ"
        )
        
        event_dict = original_event.to_dict()
        self.assertIn('symbol', event_dict)
        self.assertEqual(event_dict['symbol'], "AAPL")
        self.assertIn('timestamp', event_dict)
