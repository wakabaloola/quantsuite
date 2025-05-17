# config/settings/__init__.py
"""
Settings module initialization.
Automatically imports the appropriate settings based on environment.
"""
import os

# Default to development settings
ENVIRONMENT = os.environ.get('DJANGO_ENVIRONMENT', 'development')

if ENVIRONMENT == 'production':
    from .production import *
elif ENVIRONMENT == 'testing':
    from .testing import *
else:
    from .development import *
