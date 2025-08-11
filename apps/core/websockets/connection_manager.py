# apps/core/websockets/connection_manager.py
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict, deque
from dataclasses import dataclass, asdict

from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection"""
    channel_name: str
    user_id: Optional[int]
    consumer_type: str
    connected_at: datetime
    last_activity: datetime
    message_count: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    subscription_groups: Set[str] = None
    
    def __post_init__(self):
        if self.subscription_groups is None:
            self.subscription_groups = set()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['connected_at'] = self.connected_at.isoformat()
        data['last_activity'] = self.last_activity.isoformat()
        data['subscription_groups'] = list(self.subscription_groups)
        return data


@dataclass
class ConnectionMetrics:
    """Connection performance metrics"""
    total_connections: int = 0
    active_connections: int = 0
    authenticated_connections: int = 0
    connections_by_type: Dict[str, int] = None
    avg_connection_duration: float = 0.0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    total_bytes_transferred: int = 0
    error_rate: float = 0.0
    last_cleanup: Optional[datetime] = None
    
    def __post_init__(self):
        if self.connections_by_type is None:
            self.connections_by_type = defaultdict(int)


@dataclass
class QueuedMessage:
    """Message queued for offline user"""
    user_id: int
    message: Dict[str, Any]
    priority: int
    created_at: datetime
    expires_at: datetime
    message_type: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['expires_at'] = self.expires_at.isoformat()
        return data


class ConnectionManager:
    """
    Manages WebSocket connections with performance monitoring and message queuing
    
    Features:
    - Connection tracking and cleanup
    - User session management
    - Message queuing for offline users
    - Performance metrics collection
    - Rate limiting and connection limits
    - Automatic reconnection handling
    """
    
    def __init__(self):
        self.connections: Dict[str, ConnectionInfo] = {}
        self.user_connections: Dict[int, Set[str]] = defaultdict(set)
        self.connection_groups: Dict[str, Set[str]] = defaultdict(set)
        self.message_queues: Dict[int, deque] = defaultdict(lambda: deque(maxlen=100))
        self.metrics = ConnectionMetrics()
        self.channel_layer = get_channel_layer()
        
        # Configuration
        self.max_connections_per_user = getattr(settings, 'WEBSOCKET_SETTINGS', {}).get('MAX_CONNECTIONS_PER_USER', 5)
        self.message_queue_ttl = 3600  # 1 hour
        self.cleanup_interval = 300  # 5 minutes
        self.heartbeat_timeout = 60  # 1 minute
        
        # Rate limiting
        self.rate_limits: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.rate_limit_per_minute = getattr(settings, 'WEBSOCKET_SETTINGS', {}).get('RATE_LIMIT_PER_MINUTE', 100)
        
        # Background task management - DON'T START IMMEDIATELY
        self._cleanup_task = None
        self._background_tasks_started = False
        
        logger.info("ConnectionManager initialized (background tasks will start on first connection)")
    
    def _ensure_background_tasks(self):
        """Start background tasks if they haven't been started yet and there's an event loop"""
        if self._background_tasks_started:
            return
            
        try:
            # Only start if there's a running event loop
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                self._start_background_tasks()
                self._background_tasks_started = True
                logger.info("Background tasks started for ConnectionManager")
        except RuntimeError:
            # No running event loop - that's fine, tasks will start later
            logger.debug("No running event loop, background tasks will start later")
    
    async def register_connection(self, channel_name: str, user_id: Optional[int] = None, 
                                 consumer_type: str = "unknown") -> bool:
        """Register a new WebSocket connection"""
        try:
            # Ensure background tasks are running when first connection is made
            self._ensure_background_tasks()
            
            now = timezone.now()
            
            # Check connection limits for authenticated users
            if user_id:
                current_connections = len(self.user_connections.get(user_id, set()))
                if current_connections >= self.max_connections_per_user:
                    logger.warning(f"Connection limit exceeded for user {user_id}")
                    return False
            
            # Create connection info
            connection_info = ConnectionInfo(
                channel_name=channel_name,
                user_id=user_id,
                consumer_type=consumer_type,
                connected_at=now,
                last_activity=now
            )
            
            # Store connection
            self.connections[channel_name] = connection_info
            
            if user_id:
                self.user_connections[user_id].add(channel_name)
                self.metrics.authenticated_connections += 1
                
                # Deliver queued messages
                await self._deliver_queued_messages(user_id, channel_name)
            
            self.metrics.total_connections += 1
            self.metrics.active_connections += 1
            self.metrics.connections_by_type[consumer_type] += 1
            
            logger.info(f"Registered connection: {channel_name} (user: {user_id}, type: {consumer_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error registering connection {channel_name}: {e}")
            return False
    
    async def unregister_connection(self, channel_name: str):
        """Unregister a WebSocket connection"""
        try:
            connection_info = self.connections.get(channel_name)
            if not connection_info:
                return
            
            # Remove from user connections
            if connection_info.user_id:
                self.user_connections[connection_info.user_id].discard(channel_name)
                if not self.user_connections[connection_info.user_id]:
                    del self.user_connections[connection_info.user_id]
                self.metrics.authenticated_connections -= 1
            
            # Remove from groups
            for group in connection_info.subscription_groups:
                self.connection_groups[group].discard(channel_name)
                if not self.connection_groups[group]:
                    del self.connection_groups[group]
            
            # Update metrics
            self.metrics.active_connections -= 1
            self.metrics.connections_by_type[connection_info.consumer_type] -= 1
            
            # Calculate connection duration for averages
            duration = (timezone.now() - connection_info.connected_at).total_seconds()
            self.metrics.avg_connection_duration = (
                self.metrics.avg_connection_duration * 0.9 + duration * 0.1
            )
            
            # Remove connection
            del self.connections[channel_name]
            
            logger.info(f"Unregistered connection: {channel_name}")
            
        except Exception as e:
            logger.error(f"Error unregistering connection {channel_name}: {e}")
    
    async def update_activity(self, channel_name: str, message_size: int = 0, 
                            direction: str = "sent"):
        """Update connection activity metrics"""
        try:
            connection_info = self.connections.get(channel_name)
            if not connection_info:
                return
            
            connection_info.last_activity = timezone.now()
            connection_info.message_count += 1
            
            if direction == "sent":
                connection_info.bytes_sent += message_size
                self.metrics.total_messages_sent += 1
            else:
                connection_info.bytes_received += message_size
                self.metrics.total_messages_received += 1
            
            self.metrics.total_bytes_transferred += message_size
            
        except Exception as e:
            logger.error(f"Error updating activity for {channel_name}: {e}")
    
    async def add_to_group(self, channel_name: str, group_name: str):
        """Add connection to a subscription group"""
        try:
            connection_info = self.connections.get(channel_name)
            if connection_info:
                connection_info.subscription_groups.add(group_name)
                self.connection_groups[group_name].add(channel_name)
        except Exception as e:
            logger.error(f"Error adding {channel_name} to group {group_name}: {e}")
    
    async def remove_from_group(self, channel_name: str, group_name: str):
        """Remove connection from a subscription group"""
        try:
            connection_info = self.connections.get(channel_name)
            if connection_info:
                connection_info.subscription_groups.discard(group_name)
                self.connection_groups[group_name].discard(channel_name)
                if not self.connection_groups[group_name]:
                    del self.connection_groups[group_name]
        except Exception as e:
            logger.error(f"Error removing {channel_name} from group {group_name}: {e}")
    
    async def queue_message(self, user_id: int, message: Dict[str, Any], 
                          priority: int = 1, ttl_seconds: int = None):
        """Queue message for offline user"""
        try:
            if user_id in self.user_connections and self.user_connections[user_id]:
                # User is online, don't queue
                return False
            
            ttl = ttl_seconds or self.message_queue_ttl
            expires_at = timezone.now() + timedelta(seconds=ttl)
            
            queued_msg = QueuedMessage(
                user_id=user_id,
                message=message,
                priority=priority,
                created_at=timezone.now(),
                expires_at=expires_at,
                message_type=message.get('type', 'unknown')
            )
            
            # Add to queue (deque automatically handles max length)
            self.message_queues[user_id].append(queued_msg)
            
            # Also store in Redis for persistence
            try:
                cache_key = f"websocket_queue:{user_id}"
                queue_data = cache.get(cache_key, [])
                queue_data.append(queued_msg.to_dict())
                cache.set(cache_key, queue_data[-100:], ttl)  # Keep last 100 messages
            except Exception as cache_error:
                logger.warning(f"Could not persist message queue to cache: {cache_error}")
            
            logger.info(f"Queued message for offline user {user_id}: {message.get('type')}")
            return True
            
        except Exception as e:
            logger.error(f"Error queueing message for user {user_id}: {e}")
            return False
    
    async def _deliver_queued_messages(self, user_id: int, channel_name: str):
        """Deliver queued messages to newly connected user"""
        try:
            # Get messages from cache
            cache_key = f"websocket_queue:{user_id}"
            queue_data = []
            
            try:
                queue_data = cache.get(cache_key, [])
            except Exception as cache_error:
                logger.warning(f"Could not retrieve queued messages from cache: {cache_error}")
                return
            
            if not queue_data:
                return
            
            now = timezone.now()
            delivered_count = 0
            
            for msg_data in queue_data:
                try:
                    expires_at = datetime.fromisoformat(msg_data['expires_at'])
                    if expires_at < now:
                        continue  # Message expired
                    
                    # Send message
                    await self.channel_layer.send(channel_name, {
                        'type': 'queued_message',
                        'message': msg_data['message'],
                        'queued_at': msg_data['created_at']
                    })
                    
                    delivered_count += 1
                    
                except Exception as msg_error:
                    logger.error(f"Error delivering queued message: {msg_error}")
            
            # Clear the queue
            try:
                cache.delete(cache_key)
            except Exception:
                pass
                
            if user_id in self.message_queues:
                self.message_queues[user_id].clear()
            
            if delivered_count > 0:
                logger.info(f"Delivered {delivered_count} queued messages to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error delivering queued messages to user {user_id}: {e}")
    
    def check_rate_limit(self, identifier: str) -> bool:
        """Check if identifier has exceeded rate limit"""
        try:
            now = time.time()
            minute_ago = now - 60
            
            # Clean old entries
            while self.rate_limits[identifier] and self.rate_limits[identifier][0] < minute_ago:
                self.rate_limits[identifier].popleft()
            
            # Check current rate
            current_count = len(self.rate_limits[identifier])
            if current_count >= self.rate_limit_per_minute:
                return False
            
            # Add current request
            self.rate_limits[identifier].append(now)
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit for {identifier}: {e}")
            return True  # Allow on error
    
    async def broadcast_to_user(self, user_id: int, message: Dict[str, Any], 
                              queue_if_offline: bool = True):
        """Broadcast message to all user's connections"""
        try:
            user_channels = self.user_connections.get(user_id, set())
            
            if not user_channels and queue_if_offline:
                await self.queue_message(user_id, message)
                return
            
            # Send to all user's connections
            for channel_name in user_channels.copy():  # Copy to avoid iteration issues
                try:
                    await self.channel_layer.send(channel_name, {
                        'type': 'broadcast_message',
                        'message': message
                    })
                    await self.update_activity(channel_name, len(json.dumps(message)), "sent")
                except Exception as send_error:
                    logger.error(f"Error sending to channel {channel_name}: {send_error}")
                    # Remove dead connection
                    await self.unregister_connection(channel_name)
            
        except Exception as e:
            logger.error(f"Error broadcasting to user {user_id}: {e}")
    
    async def cleanup_stale_connections(self):
        """Clean up stale connections and expired messages"""
        try:
            now = timezone.now()
            cleanup_threshold = now - timedelta(seconds=self.heartbeat_timeout)
            stale_connections = []
            
            # Find stale connections
            for channel_name, connection_info in self.connections.items():
                if connection_info.last_activity < cleanup_threshold:
                    stale_connections.append(channel_name)
            
            # Remove stale connections
            for channel_name in stale_connections:
                await self.unregister_connection(channel_name)
                logger.info(f"Cleaned up stale connection: {channel_name}")
            
            # Clean expired message queues
            for user_id, queue in list(self.message_queues.items()):
                if not queue:
                    del self.message_queues[user_id]
                    continue
                
                # Remove expired messages
                while queue and queue[0].expires_at < now:
                    queue.popleft()
                
                if not queue:
                    del self.message_queues[user_id]
            
            # Update cleanup timestamp
            self.metrics.last_cleanup = now
            
            logger.info(f"Cleanup completed: removed {len(stale_connections)} stale connections")
            
        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive connection metrics"""
        return {
            'connections': {
                'total': self.metrics.total_connections,
                'active': self.metrics.active_connections,
                'authenticated': self.metrics.authenticated_connections,
                'by_type': dict(self.metrics.connections_by_type),
                'avg_duration_seconds': self.metrics.avg_connection_duration
            },
            'messages': {
                'total_sent': self.metrics.total_messages_sent,
                'total_received': self.metrics.total_messages_received,
                'total_bytes': self.metrics.total_bytes_transferred,
                'error_rate': self.metrics.error_rate
            },
            'queues': {
                'users_with_queued_messages': len(self.message_queues),
                'total_queued_messages': sum(len(q) for q in self.message_queues.values())
            },
            'system': {
                'last_cleanup': self.metrics.last_cleanup.isoformat() if self.metrics.last_cleanup else None,
                'active_groups': len(self.connection_groups),
                'rate_limited_users': len(self.rate_limits)
            }
        }
    
    def get_user_connections(self, user_id: int) -> List[Dict[str, Any]]:
        """Get information about user's connections"""
        user_channels = self.user_connections.get(user_id, set())
        return [
            self.connections[channel_name].to_dict() 
            for channel_name in user_channels 
            if channel_name in self.connections
        ]
    
    def _start_background_tasks(self):
        """Start background maintenance tasks (only when event loop is available)"""
        try:
            if not self._cleanup_task or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                logger.info("Background cleanup task started")
        except RuntimeError as e:
            logger.warning(f"Could not start background tasks: {e}")
    
    async def _cleanup_loop(self):
        """Background task for periodic cleanup"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_stale_connections()
            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    def shutdown(self):
        """Shutdown the connection manager gracefully"""
        logger.info("Shutting down ConnectionManager")
        
        # Cancel background tasks
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        # Clear connections
        self.connections.clear()
        self.user_connections.clear()
        self.connection_groups.clear()
        self.message_queues.clear()
        
        logger.info("ConnectionManager shutdown complete")


# Global connection manager instance - no background tasks started until first connection
connection_manager = ConnectionManager()
