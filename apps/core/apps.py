# apps/core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    
    def ready(self):
        """Initialize event system when Django starts"""
        from .events import event_bus
        
        # Event bus is already initialised as a global instance
        # Additional setup can go here
        pass
