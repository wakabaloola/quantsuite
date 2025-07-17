# apps/trading_simulation/middleware.py
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    """JWT authentication middleware for WebSockets"""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Parse token from query string
        query_string = scope.get('query_string', b'').decode()
        token = None

        if 'token=' in query_string:
            token = query_string.split('token=')[1].split('&')[0]

        if token:
            try:
                # Validate token
                UntypedToken(token)
                decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user = await get_user(decoded_data["user_id"])
                scope['user'] = user
            except (InvalidToken, TokenError, KeyError) as e:
                logger.warning(f"WebSocket JWT authentication failed: {e}")
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        return await self.inner(scope, receive, send)

def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
