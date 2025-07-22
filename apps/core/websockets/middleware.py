# apps/core/websockets/middleware.py
import asyncio
import json
import time
import logging
from typing import Any, Dict, Optional

from django.utils import timezone
from .connection_manager import connection_manager

logger = logging.getLogger(__name__)


class PerformanceMiddleware:
    """Middleware for WebSocket performance monitoring"""
    
    def __init__(self, consumer):
        self.consumer = consumer
        self.start_time = None
        self.message_count = 0
    
    async def __call__(self, scope, receive, send):
        """ASGI middleware wrapper"""
        # Wrap send to monitor outgoing messages
        async def monitored_send(message):
            if message['type'] == 'websocket.send':
                # Track outgoing message
                text_data = message.get('text', '')
                if text_data:
                    size = len(text_data.encode('utf-8'))
                    await connection_manager.update_activity(
                        scope.get('channel', ''), 
                        size, 
                        "sent"
                    )
            
            await send(message)
        
        # Wrap receive to monitor incoming messages
        async def monitored_receive():
            message = await receive()
            
            if message['type'] == 'websocket.receive':
                # Track incoming message
                text_data = message.get('text', '')
                if text_data:
                    size = len(text_data.encode('utf-8'))
                    await connection_manager.update_activity(
                        scope.get('channel', ''), 
                        size, 
                        "received"
                    )
            
            return message
        
        # Call the consumer with monitoring wrappers
        return await self.consumer(scope, monitored_receive, monitored_send)


class RateLimitMiddleware:
    """Middleware for WebSocket rate limiting"""
    
    def __init__(self, consumer):
        self.consumer = consumer
        self.last_message_time = {}
        self.message_counts = {}
    
    async def __call__(self, scope, receive, send):
        """ASGI middleware wrapper"""
        user_id = scope.get('user', {}).get('id') if scope.get('user') else None
        client_ip = scope.get('client', ['unknown'])[0]
        identifier = f"user_{user_id}" if user_id else f"ip_{client_ip}"
        
        async def rate_limited_receive():
            message = await receive()
            
            if message['type'] == 'websocket.receive':
                # Check rate limit
                if not connection_manager.check_rate_limit(identifier):
                    logger.warning(f"Rate limit exceeded for {identifier}")
                    
                    # Send rate limit message
                    await send({
                        'type': 'websocket.send',
                        'text': json.dumps({
                            'type': 'rate_limit_exceeded',
                            'message': 'Rate limit exceeded. Please slow down.',
                            'retry_after': 60
                        })
                    })
                    
                    # Don't forward the message
                    return await receive()
            
            return message
        
        return await self.consumer(scope, rate_limited_receive, send)


class ConnectionTrackingMixin:
    """Mixin for consumers to integrate with connection manager"""
    
    async def connect(self):
        """Enhanced connect with connection tracking"""
        # Get user info
        user = getattr(self.scope, 'user', None)
        user_id = user.id if user and user.is_authenticated else None
        
        # Register connection
        success = await connection_manager.register_connection(
            channel_name=self.channel_name,
            user_id=user_id,
            consumer_type=self.__class__.__name__
        )
        
        if not success:
            await self.close(code=4003)  # Service unavailable
            return
        
        # Call parent connect
        await super().connect()
    
    async def disconnect(self, close_code):
        """Enhanced disconnect with connection cleanup"""
        # Unregister connection
        await connection_manager.unregister_connection(self.channel_name)
        
        # Call parent disconnect
        await super().disconnect(close_code)
    
    async def send_tracked_message(self, message: Dict[str, Any]):
        """Send message with tracking"""
        text_data = json.dumps(message)
        await self.send(text_data=text_data)
        
        # Update activity
        await connection_manager.update_activity(
            self.channel_name, 
            len(text_data.encode('utf-8')), 
            "sent"
        )
    
    async def join_tracked_group(self, group_name: str):
        """Join group with tracking"""
        await self.channel_layer.group_add(group_name, self.channel_name)
        await connection_manager.add_to_group(self.channel_name, group_name)
    
    async def leave_tracked_group(self, group_name: str):
        """Leave group with tracking"""
        await self.channel_layer.group_discard(group_name, self.channel_name)
        await connection_manager.remove_from_group(self.channel_name, group_name)
    
    # Handler for broadcast messages
    async def broadcast_message(self, event):
        """Handle broadcast message from connection manager"""
        await self.send_tracked_message(event['message'])
    
    # Handler for queued messages
    async def queued_message(self, event):
        """Handle queued message delivery"""
        message = event['message']
        message['queued_at'] = event['queued_at']
        message['type'] = 'queued_' + message.get('type', 'message')
        
        await self.send_tracked_message(message)
