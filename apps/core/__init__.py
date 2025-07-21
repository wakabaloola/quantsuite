"""Core utilities for quant finance platform"""
# Importing specific utilities to avoid circular imports
from .exceptions import QuantFinanceError
from .decorators import time_execution, validate_financial_data, gpu_required

# Services are imported lazily when needed to prevent circular imports

default_app_config = 'apps.core.apps.CoreConfig'
