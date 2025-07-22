# apps/core/websockets/monitoring.py
import json
import logging
from typing import Dict, Any

from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .connection_manager import connection_manager
from .permissions import WebSocketPermissionMixin, IsAuthenticated

logger = logging.getLogger(__name__)


class WebSocketMonitoringConsumer(WebSocketPermissionMixin, AsyncWebsocketConsumer):
    """Consumer for real-time WebSocket performance monitoring"""
    
    permission_classes = [IsAuthenticated()]
    
    async def connect(self):
        # Check if user is staff/admin
        user = getattr(self.scope, 'user', None)
        if not user or not user.is_authenticated or not user.is_staff:
            await self.close(code=4003)
            return
        
        self.monitoring_group = 'websocket_monitoring'
        
        # Join monitoring group
        await self.channel_layer.group_add(
            self.monitoring_group,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial metrics
        await self.send_metrics()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.monitoring_group,
            self.channel_name
        )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_metrics':
                await self.send_metrics()
            elif message_type == 'get_user_connections':
                user_id = data.get('user_id')
                if user_id:
                    await self.send_user_connections(user_id)
            elif message_type == 'force_cleanup':
                await connection_manager.cleanup_stale_connections()
                await self.send(text_data=json.dumps({
                    'type': 'cleanup_completed',
                    'timestamp': timezone.now().isoformat()
                }))
            elif message_type == 'heartbeat':
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_response',
                    'timestamp': timezone.now().isoformat()
                }))
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing monitoring message: {e}")
            await self.send_error(str(e))
    
    async def send_metrics(self):
        """Send current WebSocket metrics"""
        try:
            metrics = connection_manager.get_metrics()
            await self.send(text_data=json.dumps({
                'type': 'metrics_update',
                'metrics': metrics,
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending metrics: {e}")
            await self.send_error("Error retrieving metrics")
    
    async def send_user_connections(self, user_id: int):
        """Send information about a specific user's connections"""
        try:
            connections = connection_manager.get_user_connections(user_id)
            await self.send(text_data=json.dumps({
                'type': 'user_connections',
                'user_id': user_id,
                'connections': connections,
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending user connections: {e}")
            await self.send_error(f"Error retrieving connections for user {user_id}")
    
    async def send_error(self, message: str):
        """Send error message"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))
    
    # Handle metrics updates from monitoring tasks
    async def metrics_broadcast(self, event):
        """Handle metrics broadcast from monitoring tasks"""
        await self.send(text_data=json.dumps({
            'type': 'metrics_broadcast',
            'data': event['data'],
            'timestamp': timezone.now().isoformat()
        }))
