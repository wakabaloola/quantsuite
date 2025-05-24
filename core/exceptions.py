"""Custom exceptions for quant finance platform"""

class QuantFinanceError(Exception):
    """Base exception for all quant finance errors"""
    pass

class FinancialDataException(QuantFinanceError):
    """Base exception for financial data errors"""
    pass

class ComputationException(Exception):
    """Exception for computation errors"""
    
    def __init__(self, message, computation_type=None):
        self.computation_type = computation_type
        super().__init__(message)

class ConvergenceError(ComputationException):
    """Exception when numerical methods fail to converge"""
    pass

class PortfolioOptimizationError(FinancialDataException):
    """Exception for portfolio optimization failures"""
    pass

class RealTimeDataError(FinancialDataException):
    """Exception for real-time data streaming issues"""
    pass
