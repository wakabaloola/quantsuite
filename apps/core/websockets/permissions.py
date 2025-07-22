# apps/core/websockets/permissions.py
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class WebSocketPermission(ABC):
    """Base class for WebSocket permissions"""
    
    @abstractmethod
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        """Check if user has permission for this action"""
        pass
    
    @abstractmethod
    def get_permission_name(self) -> str:
        """Get permission name for logging"""
        pass


class IsAuthenticated(WebSocketPermission):
    """Require authenticated user"""
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        return user and user.is_authenticated
    
    def get_permission_name(self) -> str:
        return "IsAuthenticated"


class IsOwnerOrReadOnly(WebSocketPermission):
    """Allow owners full access, others read-only"""
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        if not user or not user.is_authenticated:
            return False
        
        # Extract user_id from URL or scope
        target_user_id = kwargs.get('user_id') or consumer.scope.get('url_route', {}).get('kwargs', {}).get('user_id')
        
        if not target_user_id:
            return True  # No specific user targeting
        
        try:
            return int(target_user_id) == user.id
        except (ValueError, TypeError):
            return False
    
    def get_permission_name(self) -> str:
        return "IsOwnerOrReadOnly"


class HasTradingPermission(WebSocketPermission):
    """Check if user has trading permissions"""
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        if not user or not user.is_authenticated:
            return False
        
        # Check user's simulation profile
        try:
            profile = await self._get_user_profile(user.id)
            return profile is not None
        except Exception as e:
            logger.error(f"Error checking trading permission for user {user.id}: {e}")
            return False
    
    @database_sync_to_async
    def _get_user_profile(self, user_id: int):
        from apps.trading_simulation.models import UserSimulationProfile
        try:
            return UserSimulationProfile.objects.get(user_id=user_id)
        except UserSimulationProfile.DoesNotExist:
            return None
    
    def get_permission_name(self) -> str:
        return "HasTradingPermission"


class CanAccessMarketData(WebSocketPermission):
    """Check market data access permissions"""
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        # For simulation, allow all authenticated users
        return user and user.is_authenticated
    
    def get_permission_name(self) -> str:
        return "CanAccessMarketData"


class CanControlAlgorithms(WebSocketPermission):
    """Check algorithm control permissions"""
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        if not user or not user.is_authenticated:
            return False
        
        # Check if user has advanced trading permissions
        try:
            profile = await self._get_user_profile(user.id)
            return profile and profile.experience_level in ['ADVANCED', 'PROFESSIONAL']
        except Exception as e:
            logger.error(f"Error checking algorithm permission for user {user.id}: {e}")
            return False
    
    @database_sync_to_async
    def _get_user_profile(self, user_id: int):
        from apps.trading_simulation.models import UserSimulationProfile
        try:
            return UserSimulationProfile.objects.get(user_id=user_id)
        except UserSimulationProfile.DoesNotExist:
            return None
    
    def get_permission_name(self) -> str:
        return "CanControlAlgorithms"


class WebSocketPermissionMixin:
    """Mixin to add permission checking to WebSocket consumers"""
    
    permission_classes: List[WebSocketPermission] = []
    
    async def check_permissions(self, action: str = "connect", **kwargs) -> bool:
        """Check all permissions for the given action"""
        user = getattr(self.scope, 'user', AnonymousUser())
        
        for permission_class in self.permission_classes:
            permission = permission_class()
            
            if not await permission.has_permission(self, user, **kwargs):
                logger.warning(
                    f"Permission denied: {permission.get_permission_name()} "
                    f"for user {getattr(user, 'id', 'anonymous')} "
                    f"on {self.__class__.__name__}.{action}"
                )
                return False
        
        return True
    
    async def connect(self):
        """Enhanced connect with permission checking"""
        if not await self.check_permissions("connect"):
            await self.close(code=4003)  # Forbidden
            return
        
        await super().connect()
    
    async def receive(self, text_data=None, bytes_data=None):
        """Enhanced receive with permission checking"""
        if text_data:
            try:
                import json
                data = json.loads(text_data)
                action = data.get('type', 'unknown')
                
                # Check permissions for specific actions
                if not await self.check_permissions(action, **data):
                    await self.send_error("Permission denied", code=4003)
                    return
                    
            except json.JSONDecodeError:
                pass  # Let parent handle invalid JSON
        
        await super().receive(text_data, bytes_data)
    
    async def send_error(self, message: str, code: int = 4000):
        """Send error message to client"""
        import json
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'code': code,
            'timestamp': timezone.now().isoformat()
        }))


class PermissionCache:
    """Cache for permission checks to improve performance"""
    
    @staticmethod
    def get_cache_key(user_id: int, permission_name: str, context: str = "") -> str:
        """Generate cache key for permission"""
        return f"ws_permission:{user_id}:{permission_name}:{context}"
    
    @staticmethod
    async def get_cached_permission(user_id: int, permission_name: str, 
                                  context: str = "", ttl: int = 300) -> Optional[bool]:
        """Get cached permission result"""
        try:
            cache_key = PermissionCache.get_cache_key(user_id, permission_name, context)
            return cache.get(cache_key)
        except Exception as e:
            logger.error(f"Error getting cached permission: {e}")
            return None
    
    @staticmethod
    async def cache_permission(user_id: int, permission_name: str, 
                             result: bool, context: str = "", ttl: int = 300):
        """Cache permission result"""
        try:
            cache_key = PermissionCache.get_cache_key(user_id, permission_name, context)
            cache.set(cache_key, result, ttl)
        except Exception as e:
            logger.error(f"Error caching permission: {e}")


class CachedPermission(WebSocketPermission):
    """Base class for cached permissions"""
    
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
    
    async def has_permission(self, consumer, user, **kwargs) -> bool:
        if not user or not user.is_authenticated:
            return False
        
        context = self._get_context(**kwargs)
        
        # Check cache first
        cached_result = await PermissionCache.get_cached_permission(
            user.id, self.get_permission_name(), context, self.ttl
        )
        
        if cached_result is not None:
            return cached_result
        
        # Calculate permission
        result = await self._check_permission(consumer, user, **kwargs)
        
        # Cache result
        await PermissionCache.cache_permission(
            user.id, self.get_permission_name(), result, context, self.ttl
        )
        
        return result
    
    @abstractmethod
    async def _check_permission(self, consumer, user, **kwargs) -> bool:
        """Implement actual permission check"""
        pass
    
    def _get_context(self, **kwargs) -> str:
        """Get context string for caching"""
        return ""
