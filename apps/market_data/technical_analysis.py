# apps/market_data/technical_analysis.py
"""
Professional Technical Analysis Framework for Quantitative Research

This module provides a comprehensive set of technical indicators and analysis tools
for quantitative researchers. It includes both built-in indicators and a framework
for implementing custom indicators.

Usage Examples:
    # Calculate RSI for a ticker
    calculator = TechnicalAnalysisCalculator('AAPL')
    rsi_data = calculator.calculate_rsi(period=14)
    
    # Calculate multiple indicators
    indicators = calculator.calculate_indicators(['rsi', 'macd', 'bollinger_bands'])
    
    # Create custom indicator
    class CustomMomentum(TechnicalIndicatorBase):
        def calculate(self, data, **kwargs):
            # Your custom logic here
            return results
"""

import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from django.utils import timezone
from abc import ABC, abstractmethod

from .models import MarketData, Ticker, TechnicalIndicator


class TechnicalIndicatorBase(ABC):
    """
    Base class for all technical indicators
    
    This provides a framework for quantitative researchers to implement
    their own custom technical indicators with consistent interfaces.
    """
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        
    @abstractmethod
    def calculate(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Calculate the technical indicator
        
        Args:
            data: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            **kwargs: Additional parameters specific to the indicator
            
        Returns:
            Dictionary with calculation results
        """
        pass
    
    def validate_data(self, data: pd.DataFrame, min_periods: int = 1) -> bool:
        """Validate that data is sufficient for calculation"""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        
        if not all(col in data.columns for col in required_columns):
            raise ValueError(f"Data must contain columns: {required_columns}")
        
        if len(data) < min_periods:
            raise ValueError(f"Insufficient data: need at least {min_periods} periods, got {len(data)}")
        
        return True
    
    def _round_decimal(self, value: float, places: int = 6) -> Decimal:
        """Round float to Decimal with specified precision"""
        if pd.isna(value) or not np.isfinite(value):
            return None
        return Decimal(str(value)).quantize(
            Decimal('0.' + '0' * places), 
            rounding=ROUND_HALF_UP
        )


class MovingAverageIndicator(TechnicalIndicatorBase):
    """Moving Average indicators (SMA, EMA, WMA, etc.)"""
    
    def __init__(self):
        super().__init__("Moving Averages", "Simple, Exponential, and Weighted Moving Averages")
    
    def calculate(self, data: pd.DataFrame, periods: List[int] = [20, 50, 200], 
                 ma_types: List[str] = ['sma']) -> Dict[str, Any]:
        """
        Calculate various types of moving averages
        
        Args:
            data: OHLCV DataFrame
            periods: List of periods to calculate (e.g., [20, 50, 200])
            ma_types: Types of MA to calculate ['sma', 'ema', 'wma', 'hull', 'tema']
        """
        self.validate_data(data, min_periods=max(periods))
        
        results = {}
        
        for ma_type in ma_types:
            for period in periods:
                key = f"{ma_type}_{period}"
                
                if ma_type == 'sma':
                    values = data['close'].rolling(window=period).mean()
                elif ma_type == 'ema':
                    values = data['close'].ewm(span=period).mean()
                elif ma_type == 'wma':
                    values = self._calculate_wma(data['close'], period)
                elif ma_type == 'hull':
                    values = self._calculate_hull_ma(data['close'], period)
                elif ma_type == 'tema':
                    values = self._calculate_tema(data['close'], period)
                else:
                    continue
                
                results[key] = {
                    'values': values.dropna().to_dict(),
                    'current_value': self._round_decimal(values.iloc[-1]) if not pd.isna(values.iloc[-1]) else None,
                    'period': period,
                    'type': ma_type.upper()
                }
        
        # Add crossover signals
        if 'sma_20' in results and 'sma_50' in results:
            results['golden_cross'] = self._detect_crossover(
                results['sma_20']['values'], 
                results['sma_50']['values']
            )
        
        return results
    
    def _calculate_wma(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Weighted Moving Average"""
        weights = np.arange(1, period + 1)
        return prices.rolling(window=period).apply(
            lambda x: np.dot(x, weights) / weights.sum(), raw=True
        )
    
    def _calculate_hull_ma(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Hull Moving Average"""
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))
        
        wma_half = self._calculate_wma(prices, half_period)
        wma_full = self._calculate_wma(prices, period)
        
        hull_values = 2 * wma_half - wma_full
        return self._calculate_wma(hull_values, sqrt_period)
    
    def _calculate_tema(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Triple Exponential Moving Average"""
        ema1 = prices.ewm(span=period).mean()
        ema2 = ema1.ewm(span=period).mean()
        ema3 = ema2.ewm(span=period).mean()
        
        return 3 * ema1 - 3 * ema2 + ema3
    
    def _detect_crossover(self, fast_values: Dict, slow_values: Dict) -> Dict:
        """Detect moving average crossovers"""
        dates = sorted(set(fast_values.keys()) & set(slow_values.keys()))
        
        if len(dates) < 2:
            return {'signal': 'insufficient_data'}
        
        # Check latest crossover
        latest_date = dates[-1]
        previous_date = dates[-2]
        
        current_fast = fast_values[latest_date]
        current_slow = slow_values[latest_date]
        prev_fast = fast_values[previous_date]
        prev_slow = slow_values[previous_date]
        
        if prev_fast <= prev_slow and current_fast > current_slow:
            return {'signal': 'golden_cross', 'date': latest_date}
        elif prev_fast >= prev_slow and current_fast < current_slow:
            return {'signal': 'death_cross', 'date': latest_date}
        else:
            return {'signal': 'no_signal'}


class MomentumIndicator(TechnicalIndicatorBase):
    """Momentum indicators (RSI, MACD, Stochastic, etc.)"""
    
    def __init__(self):
        super().__init__("Momentum Indicators", "RSI, MACD, Stochastic Oscillator, Williams %R")
    
    def calculate(self, data: pd.DataFrame, indicators: List[str] = ['rsi', 'macd'], 
                 **kwargs) -> Dict[str, Any]:
        """Calculate momentum indicators"""
        self.validate_data(data, min_periods=50)  # Ensure enough data for most indicators
        
        results = {}
        
        if 'rsi' in indicators:
            results['rsi'] = self._calculate_rsi(data, kwargs.get('rsi_period', 14))
        
        if 'macd' in indicators:
            results['macd'] = self._calculate_macd(
                data, 
                kwargs.get('macd_fast', 12),
                kwargs.get('macd_slow', 26), 
                kwargs.get('macd_signal', 9)
            )
        
        if 'stochastic' in indicators:
            results['stochastic'] = self._calculate_stochastic(
                data,
                kwargs.get('stoch_k', 14),
                kwargs.get('stoch_d', 3)
            )
        
        if 'williams_r' in indicators:
            results['williams_r'] = self._calculate_williams_r(data, kwargs.get('williams_period', 14))
        
        if 'cci' in indicators:
            results['cci'] = self._calculate_cci(data, kwargs.get('cci_period', 20))
        
        return results
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
        """Calculate Relative Strength Index"""
        close = data['close']
        delta = close.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = self._round_decimal(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
        
        # Generate signals
        signal = 'neutral'
        if current_rsi:
            if current_rsi > 70:
                signal = 'overbought'
            elif current_rsi < 30:
                signal = 'oversold'
        
        return {
            'values': rsi.dropna().to_dict(),
            'current_value': current_rsi,
            'signal': signal,
            'overbought_threshold': 70,
            'oversold_threshold': 30,
            'period': period
        }
    
    def _calculate_macd(self, data: pd.DataFrame, fast: int = 12, slow: int = 26, 
                       signal: int = 9) -> Dict[str, Any]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        close = data['close']
        
        ema_fast = close.ewm(span=fast).mean()
        ema_slow = close.ewm(span=slow).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        current_macd = self._round_decimal(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None
        current_signal = self._round_decimal(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else None
        current_histogram = self._round_decimal(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else None
        
        # Generate signals
        trend_signal = 'neutral'
        if current_histogram:
            if current_histogram > 0:
                trend_signal = 'bullish'
            elif current_histogram < 0:
                trend_signal = 'bearish'
        
        return {
            'macd_line': current_macd,
            'signal_line': current_signal,
            'histogram': current_histogram,
            'signal': trend_signal,
            'crossover': self._detect_macd_crossover(macd_line, signal_line),
            'parameters': {'fast': fast, 'slow': slow, 'signal': signal}
        }
    
    def _calculate_stochastic(self, data: pd.DataFrame, k_period: int = 14, 
                            d_period: int = 3) -> Dict[str, Any]:
        """Calculate Stochastic Oscillator"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d_percent = k_percent.rolling(window=d_period).mean()
        
        current_k = self._round_decimal(k_percent.iloc[-1]) if not pd.isna(k_percent.iloc[-1]) else None
        current_d = self._round_decimal(d_percent.iloc[-1]) if not pd.isna(d_percent.iloc[-1]) else None
        
        # Generate signals
        signal = 'neutral'
        if current_k and current_d:
            if current_k > 80 and current_d > 80:
                signal = 'overbought'
            elif current_k < 20 and current_d < 20:
                signal = 'oversold'
        
        return {
            'k_percent': current_k,
            'd_percent': current_d,
            'signal': signal,
            'parameters': {'k_period': k_period, 'd_period': d_period}
        }
    
    def _calculate_williams_r(self, data: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
        """Calculate Williams %R"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
        
        current_wr = self._round_decimal(williams_r.iloc[-1]) if not pd.isna(williams_r.iloc[-1]) else None
        
        # Generate signals
        signal = 'neutral'
        if current_wr:
            if current_wr > -20:
                signal = 'overbought'
            elif current_wr < -80:
                signal = 'oversold'
        
        return {
            'current_value': current_wr,
            'signal': signal,
            'period': period
        }
    
    def _calculate_cci(self, data: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
        """Calculate Commodity Channel Index"""
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        
        mean_deviation = typical_price.rolling(window=period).apply(
            lambda x: np.abs(x - x.mean()).mean()
        )
        
        cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
        
        current_cci = self._round_decimal(cci.iloc[-1]) if not pd.isna(cci.iloc[-1]) else None
        
        # Generate signals
        signal = 'neutral'
        if current_cci:
            if current_cci > 100:
                signal = 'overbought'
            elif current_cci < -100:
                signal = 'oversold'
        
        return {
            'current_value': current_cci,
            'signal': signal,
            'period': period
        }
    
    def _detect_macd_crossover(self, macd_line: pd.Series, signal_line: pd.Series) -> str:
        """Detect MACD crossover signals"""
        if len(macd_line) < 2 or len(signal_line) < 2:
            return 'insufficient_data'
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        
        if prev_macd <= prev_signal and current_macd > current_signal:
            return 'bullish_crossover'
        elif prev_macd >= prev_signal and current_macd < current_signal:
            return 'bearish_crossover'
        else:
            return 'no_crossover'


class VolatilityIndicator(TechnicalIndicatorBase):
    """Volatility indicators (Bollinger Bands, ATR, etc.)"""
    
    def __init__(self):
        super().__init__("Volatility Indicators", "Bollinger Bands, ATR, Keltner Channels")
    
    def calculate(self, data: pd.DataFrame, indicators: List[str] = ['bollinger_bands', 'atr'], 
                 **kwargs) -> Dict[str, Any]:
        """Calculate volatility indicators"""
        self.validate_data(data, min_periods=20)
        
        results = {}
        
        if 'bollinger_bands' in indicators:
            results['bollinger_bands'] = self._calculate_bollinger_bands(
                data, 
                kwargs.get('bb_period', 20), 
                kwargs.get('bb_std', 2)
            )
        
        if 'atr' in indicators:
            results['atr'] = self._calculate_atr(data, kwargs.get('atr_period', 14))
        
        if 'keltner_channels' in indicators:
            results['keltner_channels'] = self._calculate_keltner_channels(
                data,
                kwargs.get('keltner_period', 20),
                kwargs.get('keltner_multiplier', 2)
            )
        
        return results
    
    def _calculate_bollinger_bands(self, data: pd.DataFrame, period: int = 20, 
                                  std_dev: float = 2) -> Dict[str, Any]:
        """Calculate Bollinger Bands"""
        close = data['close']
        sma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        current_price = self._round_decimal(close.iloc[-1])
        current_upper = self._round_decimal(upper_band.iloc[-1]) if not pd.isna(upper_band.iloc[-1]) else None
        current_middle = self._round_decimal(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else None
        current_lower = self._round_decimal(lower_band.iloc[-1]) if not pd.isna(lower_band.iloc[-1]) else None
        
        # Calculate %B (position within bands)
        percent_b = None
        if current_upper and current_lower and current_price:
            percent_b = float((current_price - current_lower) / (current_upper - current_lower))
        
        # Calculate bandwidth
        bandwidth = None
        if current_upper and current_lower and current_middle:
            bandwidth = float((current_upper - current_lower) / current_middle)
        
        # Generate signals
        signal = 'neutral'
        if current_price and current_upper and current_lower:
            if current_price > current_upper:
                signal = 'overbought'
            elif current_price < current_lower:
                signal = 'oversold'
        
        return {
            'upper_band': current_upper,
            'middle_band': current_middle,
            'lower_band': current_lower,
            'current_price': current_price,
            'percent_b': self._round_decimal(percent_b) if percent_b else None,
            'bandwidth': self._round_decimal(bandwidth) if bandwidth else None,
            'signal': signal,
            'parameters': {'period': period, 'std_dev': std_dev}
        }
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
        """Calculate Average True Range"""
        high = data['high']
        low = data['low']
        close = data['close'].shift(1)
        
        tr1 = high - low
        tr2 = np.abs(high - close)
        tr3 = np.abs(low - close)
        
        true_range = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = pd.Series(true_range).rolling(window=period).mean()
        
        current_atr = self._round_decimal(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None
        
        # Calculate volatility rating
        volatility_rating = 'medium'
        if current_atr:
            current_price = data['close'].iloc[-1]
            atr_percentage = float(current_atr / current_price * 100)
            
            if atr_percentage < 1:
                volatility_rating = 'low'
            elif atr_percentage > 3:
                volatility_rating = 'high'
        
        return {
            'current_value': current_atr,
            'volatility_rating': volatility_rating,
            'period': period
        }
    
    def _calculate_keltner_channels(self, data: pd.DataFrame, period: int = 20, 
                                   multiplier: float = 2) -> Dict[str, Any]:
        """Calculate Keltner Channels"""
        close = data['close']
        high = data['high']
        low = data['low']
        
        # Calculate typical price and EMA
        typical_price = (high + low + close) / 3
        ema = typical_price.ewm(span=period).mean()
        
        # Calculate ATR
        atr_data = self._calculate_atr(data, period)
        atr_series = pd.Series([float(atr_data['current_value']) if atr_data['current_value'] else 0] * len(data))
        
        upper_channel = ema + (atr_series * multiplier)
        lower_channel = ema - (atr_series * multiplier)
        
        current_upper = self._round_decimal(upper_channel.iloc[-1]) if not pd.isna(upper_channel.iloc[-1]) else None
        current_middle = self._round_decimal(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else None
        current_lower = self._round_decimal(lower_channel.iloc[-1]) if not pd.isna(lower_channel.iloc[-1]) else None
        
        return {
            'upper_channel': current_upper,
            'middle_line': current_middle,
            'lower_channel': current_lower,
            'parameters': {'period': period, 'multiplier': multiplier}
        }


class TechnicalAnalysisCalculator:
    """
    Main calculator class for technical analysis
    
    This provides a unified interface for calculating technical indicators
    and is designed to be used by quantitative researchers.
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.ticker = None
        self.data = None
        
        # Initialize indicator calculators
        self.ma_calculator = MovingAverageIndicator()
        self.momentum_calculator = MomentumIndicator()
        self.volatility_calculator = VolatilityIndicator()
        
        # Load ticker
        try:
            self.ticker = Ticker.objects.get(symbol=symbol, is_active=True)
        except Ticker.DoesNotExist:
            raise ValueError(f"Ticker {symbol} not found or inactive")
    
    def load_data(self, timeframe: str = '1d', limit: int = 500) -> pd.DataFrame:
        """Load market data for calculations"""
        market_data = MarketData.objects.filter(
            ticker=self.ticker,
            timeframe=timeframe
        ).order_by('-timestamp')[:limit]
        
        if not market_data:
            raise ValueError(f"No market data available for {self.symbol}")
        
        # Convert to DataFrame
        data_list = []
        for item in reversed(market_data):
            data_list.append({
                'timestamp': item.timestamp,
                'open': float(item.open),
                'high': float(item.high),
                'low': float(item.low),
                'close': float(item.close),
                'volume': float(item.volume)
            })
        
        self.data = pd.DataFrame(data_list)
        self.data.set_index('timestamp', inplace=True)
        
        return self.data
    
    def calculate_indicators(self, indicators: List[str], timeframe: str = '1d', 
                           **kwargs) -> Dict[str, Any]:
        """
        Calculate multiple technical indicators
        
        Args:
            indicators: List of indicators to calculate
            timeframe: Data timeframe to use
            **kwargs: Additional parameters for indicators
            
        Returns:
            Dictionary with all calculated indicators
        """
        if self.data is None:
            self.load_data(timeframe)
        
        results = {
            'symbol': self.symbol,
            'timeframe': timeframe,
            'data_points': len(self.data),
            'indicators': {}
        }
        
        # Moving averages
        ma_indicators = [i for i in indicators if i.startswith(('sma', 'ema', 'wma', 'hull', 'tema'))]
        if ma_indicators:
            ma_types = list(set([i.split('_')[0] for i in ma_indicators]))
            periods = []
            for indicator in ma_indicators:
                parts = indicator.split('_')
                if len(parts) > 1 and parts[1].isdigit():
                    periods.append(int(parts[1]))
            
            if periods:
                ma_results = self.ma_calculator.calculate(
                    self.data, 
                    periods=periods, 
                    ma_types=ma_types
                )
                results['indicators'].update(ma_results)
        
        # Momentum indicators
        momentum_indicators = [i for i in indicators if i in ['rsi', 'macd', 'stochastic', 'williams_r', 'cci']]
        if momentum_indicators:
            momentum_results = self.momentum_calculator.calculate(
                self.data, 
                indicators=momentum_indicators,
                **kwargs
            )
            results['indicators'].update(momentum_results)
        
        # Volatility indicators
        volatility_indicators = [i for i in indicators if i in ['bollinger_bands', 'atr', 'keltner_channels']]
        if volatility_indicators:
            volatility_results = self.volatility_calculator.calculate(
                self.data,
                indicators=volatility_indicators,
                **kwargs
            )
            results['indicators'].update(volatility_results)
        
        return results
    
    def calculate_rsi(self, period: int = 14, timeframe: str = '1d') -> Dict[str, Any]:
        """Calculate RSI for the symbol"""
        if self.data is None:
            self.load_data(timeframe)
        
        return self.momentum_calculator._calculate_rsi(self.data, period)
    
    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9,
                      timeframe: str = '1d') -> Dict[str, Any]:
        """Calculate MACD for the symbol"""
        if self.data is None:
            self.load_data(timeframe)
        
        return self.momentum_calculator._calculate_macd(self.data, fast, slow, signal)
    
    def calculate_bollinger_bands(self, period: int = 20, std_dev: float = 2,
                                 timeframe: str = '1d') -> Dict[str, Any]:
        """Calculate Bollinger Bands for the symbol"""
        if self.data is None:
            self.load_data(timeframe)
        
        return self.volatility_calculator._calculate_bollinger_bands(self.data, period, std_dev)
    
    def save_indicators_to_db(self, indicators_data: Dict[str, Any]) -> None:
        """Save calculated indicators to database for caching"""
        timestamp = timezone.now()
        
        for indicator_name, indicator_data in indicators_data.get('indicators', {}).items():
            if isinstance(indicator_data, dict) and 'current_value' in indicator_data:
                TechnicalIndicator.objects.update_or_create(
                    ticker=self.ticker,
                    timestamp=timestamp,
                    timeframe=indicators_data.get('timeframe', '1d'),
                    indicator_name=indicator_name,
                    defaults={
                        'value': indicator_data['current_value'],
                        'values': indicator_data if 'values' in indicator_data else None,
                        'parameters': indicator_data.get('parameters', {})
                    }
                )


# Example custom indicator implementation for researchers
class CustomMomentumIndicator(TechnicalIndicatorBase):
    """
    Example custom momentum indicator
    
    This demonstrates how quantitative researchers can implement
    their own custom indicators using the framework.
    """
    
    def __init__(self):
        super().__init__(
            "Custom Momentum", 
            "Example custom momentum indicator combining price and volume"
        )
    
    def calculate(self, data: pd.DataFrame, period: int = 20, 
                 volume_factor: float = 0.3) -> Dict[str, Any]:
        """
        Calculate custom momentum indicator
        
        This combines price momentum with volume momentum
        """
        self.validate_data(data, min_periods=period)
        
        # Price momentum
        price_momentum = (data['close'] - data['close'].shift(period)) / data['close'].shift(period)
        
        # Volume momentum
        volume_sma = data['volume'].rolling(window=period).mean()
        volume_momentum = (data['volume'] - volume_sma) / volume_sma
        
        # Combined momentum
        combined_momentum = price_momentum + (volume_momentum * volume_factor)
        
        current_value = self._round_decimal(combined_momentum.iloc[-1]) if not pd.isna(combined_momentum.iloc[-1]) else None
        
        # Generate signal
        signal = 'neutral'
        if current_value:
            if current_value > 0.1:
                signal = 'strong_bullish'
            elif current_value > 0.05:
                signal = 'bullish'
            elif current_value < -0.1:
                signal = 'strong_bearish'
            elif current_value < -0.05:
                signal = 'bearish'
        
        return {
            'current_value': current_value,
            'signal': signal,
            'components': {
                'price_momentum': self._round_decimal(price_momentum.iloc[-1]) if not pd.isna(price_momentum.iloc[-1]) else None,
                'volume_momentum': self._round_decimal(volume_momentum.iloc[-1]) if not pd.isna(volume_momentum.iloc[-1]) else None
            },
            'parameters': {
                'period': period,
                'volume_factor': volume_factor
            }
        }
