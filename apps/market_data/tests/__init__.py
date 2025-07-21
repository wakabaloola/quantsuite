# apps/market_data/tests/__init__.py
from .test_streaming import *

# Only import enhanced analysis tests if they exist
try:
    from .test_enhanced_analysis import *
except ImportError:
    pass
