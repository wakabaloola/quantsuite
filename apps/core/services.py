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
        """Get historical market data for a ticker"""
        queryset = MarketData.objects.filter(
            ticker__symbol=ticker_symbol,
            timestamp__gte=start_date,
            timestamp__lte=end_date
        ).order_by('timestamp')
        
        if not queryset.exists():
            return None
            
        data = pd.DataFrame.from_records(queryset.values())
        data.set_index('timestamp', inplace=True)
        return data

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
