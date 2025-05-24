"""Common decorators for quant finance platform"""
import time
from functools import wraps
from django.conf import settings
from .exceptions import ComputationException

def time_execution(func):
    """Decorator to time function execution"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} executed in {end-start:.4f}s")
        return result
    return wrapper

def validate_financial_data(func):
    """Decorator to validate financial data inputs"""
    @wraps(func)
    def wrapper(series, *args, **kwargs):
        if series.isnull().any():
            raise ValueError("Input series contains NaN values")
        if len(series) < 2:
            raise ValueError("Input series too short for analysis")
        return func(series, *args, **kwargs)
    return wrapper

def gpu_required(func):
    """Decorator to check GPU availability"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not getattr(settings, 'USE_GPU', False):
            raise ComputationException(
                "GPU computation requested but not enabled",
                computation_type="GPU"
            )
        return func(*args, **kwargs)
    return wrapper
