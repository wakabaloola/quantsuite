# apps/core/services.py
"""Core services for quant finance platform"""
import numpy as np
import pandas as pd
import torch
from django.conf import settings
from apps.market_data.models import MarketData, BaseModel

class FinancialDataService:
    """Service for financial data operations"""
    
    @staticmethod
    def normalize_prices(series):
        """Normalize price series to percentage returns"""
        return series.pct_change().dropna()
        
    @staticmethod
    def calculate_volatility(series, window=30):
        """Calculate rolling volatility"""
        returns = FinancialDataService.normalize_prices(series)
        return returns.rolling(window).std() * np.sqrt(252)

    @classmethod
    def get_historical_data(cls, ticker_symbol, start_date, end_date):
        """Optimized version preserving your advantages"""
        # Only fetch necessary fields to reduce memory
        fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'adjusted_close']

        queryset = MarketData.objects.filter(
            ticker__symbol=ticker_symbol,
            timestamp__range=(start_date, end_date)
        ).order_by('timestamp').values(*fields)

        if not queryset.exists():
            return None

        # Use more efficient DataFrame construction
        data = pd.DataFrame.from_records(queryset, coerce_float=True)
        data['timestamp'] = pd.to_datetime(data['timestamp'], utc=True)
        return data.set_index('timestamp')

class ComputationService:
    """Service for numerical computations"""
    
    def __init__(self):
        self.device = self._get_device()
        
    def _get_device(self):
        """Get appropriate computation device (GPU if available)"""
        if getattr(settings, 'USE_GPU', False) and torch.backends.mps.is_available():
            return torch.device('mps')  # Metal Performance Shaders for macOS
        return torch.device('cpu')
        
    def matrix_operation(self, matrix_a, matrix_b):
        """Perform matrix operation with GPU acceleration if available"""
        # Convert numpy arrays to PyTorch tensors
        tensor_a = torch.from_numpy(matrix_a).to(self.device)
        tensor_b = torch.from_numpy(matrix_b).to(self.device)
        
        # Perform matrix multiplication
        result = torch.matmul(tensor_a, tensor_b)
        
        # Convert back to numpy array
        return result.cpu().numpy()
