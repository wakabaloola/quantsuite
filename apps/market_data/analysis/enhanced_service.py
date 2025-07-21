# apps/market_data/analysis/enhanced_service.py
"""
Enhanced Real-Time Technical Analysis Service
===========================================

Enterprise-grade technical analysis engine that provides:
- Real-time indicator calculations from streaming data
- Event-driven signal generation with strength scoring
- Advanced pattern recognition and trend analysis
- Redis caching for high-performance repeated calculations
- Automatic algorithm trigger events for strong signals
- WebSocket broadcasting for real-time signal delivery
- Extensible framework for custom indicators and strategies

Features:
- Integrates with existing TechnicalAnalysisCalculator foundation
- Extends beyond RSI/MACD to include advanced indicators
- Provides signal confidence scoring and trend strength analysis
- Caches calculations in Redis for sub-millisecond response times
- Publishes events that trigger algorithmic trading decisions
- Supports real-time and historical analysis modes
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Any, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, deque
import numpy as np
import pandas as pd

from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from apps.core.events import publish_technical_signal, publish_algorithm_trigger
from ..technical_analysis import TechnicalAnalysisCalculator
from ..models import Ticker, MarketData, TechnicalIndicator
from ..common import MarketDataPoint

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types of trading signals"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    NEUTRAL = "neutral"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SignalConfidence(Enum):
    """Signal confidence levels"""
    VERY_HIGH = "very_high"    # 90-100%
    HIGH = "high"              # 75-89%
    MEDIUM = "medium"          # 50-74%
    LOW = "low"                # 25-49%
    VERY_LOW = "very_low"      # 0-24%


class TrendDirection(Enum):
    """Market trend directions"""
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    SIDEWAYS = "sideways"
    DOWNTREND = "downtrend"
    STRONG_DOWNTREND = "strong_downtrend"


@dataclass
class TechnicalSignal:
    """Comprehensive technical signal with metadata"""
    symbol: str
    timestamp: datetime
    signal_type: SignalType
    confidence: SignalConfidence
    strength: float  # 0.0 to 1.0
    
    # Contributing indicators
    indicators: Dict[str, Dict[str, Any]]
    
    # Market context
    trend_direction: TrendDirection
    volatility_level: str
    volume_profile: str
    
    # Signal metadata
    trigger_price: Decimal
    target_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    risk_reward_ratio: Optional[float] = None
    
    # Event tracking
    signal_id: str = ""
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.signal_id:
            import uuid
            self.signal_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for caching/serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['signal_type'] = self.signal_type.value
        data['confidence'] = self.confidence.value
        data['trend_direction'] = self.trend_direction.value
        data['trigger_price'] = str(self.trigger_price)
        data['target_price'] = str(self.target_price) if self.target_price else None
        data['stop_loss'] = str(self.stop_loss) if self.stop_loss else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TechnicalSignal':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['signal_type'] = SignalType(data['signal_type'])
        data['confidence'] = SignalConfidence(data['confidence'])
        data['trend_direction'] = TrendDirection(data['trend_direction'])
        data['trigger_price'] = Decimal(data['trigger_price'])
        data['target_price'] = Decimal(data['target_price']) if data['target_price'] else None
        data['stop_loss'] = Decimal(data['stop_loss']) if data['stop_loss'] else None
        return cls(**data)


@dataclass
class IndicatorResult:
    """Result from individual indicator calculation"""
    name: str
    value: float
    signal_contribution: float  # -1.0 to 1.0 (negative = bearish, positive = bullish)
    confidence: float  # 0.0 to 1.0
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdvancedIndicators:
    """
    Advanced technical indicators beyond basic RSI/MACD
    Extends the existing TechnicalAnalysisCalculator framework
    """
    
    @staticmethod
    def calculate_stochastic_rsi(data: pd.Series, period: int = 14, 
                               smooth_k: int = 3, smooth_d: int = 3) -> Dict[str, float]:
        """Calculate Stochastic RSI for enhanced momentum analysis"""
        try:
            # Calculate RSI first
            delta = data.diff()
            gain = delta.where(delta > 0, 0).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Apply Stochastic to RSI
            rsi_min = rsi.rolling(window=period).min()
            rsi_max = rsi.rolling(window=period).max()
            
            stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min) * 100
            
            # Smooth the results
            k_percent = stoch_rsi.rolling(window=smooth_k).mean()
            d_percent = k_percent.rolling(window=smooth_d).mean()
            
            return {
                'stoch_rsi': float(stoch_rsi.iloc[-1]) if not pd.isna(stoch_rsi.iloc[-1]) else 0.0,
                'k_percent': float(k_percent.iloc[-1]) if not pd.isna(k_percent.iloc[-1]) else 0.0,
                'd_percent': float(d_percent.iloc[-1]) if not pd.isna(d_percent.iloc[-1]) else 0.0
            }
            
        except Exception as e:
            logger.error(f"Stochastic RSI calculation error: {e}")
            return {'stoch_rsi': 0.0, 'k_percent': 0.0, 'd_percent': 0.0}
    
    @staticmethod
    def calculate_williams_r(high: pd.Series, low: pd.Series, close: pd.Series, 
                           period: int = 14) -> float:
        """Calculate Williams %R momentum indicator"""
        try:
            highest_high = high.rolling(window=period).max()
            lowest_low = low.rolling(window=period).min()
            
            williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
            return float(williams_r.iloc[-1]) if not pd.isna(williams_r.iloc[-1]) else 0.0
            
        except Exception as e:
            logger.error(f"Williams %R calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_cci(high: pd.Series, low: pd.Series, close: pd.Series, 
                     period: int = 20) -> float:
        """Calculate Commodity Channel Index"""
        try:
            typical_price = (high + low + close) / 3
            sma_tp = typical_price.rolling(window=period).mean()
            
            mean_deviation = typical_price.rolling(window=period).apply(
                lambda x: np.abs(x - x.mean()).mean()
            )
            
            cci = (typical_price - sma_tp) / (0.015 * mean_deviation)
            return float(cci.iloc[-1]) if not pd.isna(cci.iloc[-1]) else 0.0
            
        except Exception as e:
            logger.error(f"CCI calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, 
                     period: int = 14) -> Dict[str, float]:
        """Calculate Average Directional Index (trend strength)"""
        try:
            # Calculate True Range
            tr1 = high - low
            tr2 = np.abs(high - close.shift(1))
            tr3 = np.abs(low - close.shift(1))
            true_range = np.maximum(tr1, np.maximum(tr2, tr3))
            
            # Calculate Directional Movement
            dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low), 
                              np.maximum(high - high.shift(1), 0), 0)
            dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)), 
                               np.maximum(low.shift(1) - low, 0), 0)
            
            # Smooth the values
            tr_smooth = pd.Series(true_range).rolling(window=period).mean()
            dm_plus_smooth = pd.Series(dm_plus).rolling(window=period).mean()
            dm_minus_smooth = pd.Series(dm_minus).rolling(window=period).mean()
            
            # Calculate Directional Indicators
            di_plus = 100 * dm_plus_smooth / tr_smooth
            di_minus = 100 * dm_minus_smooth / tr_smooth
            
            # Calculate ADX
            dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus)
            adx = dx.rolling(window=period).mean()
            
            return {
                'adx': float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0,
                'di_plus': float(di_plus.iloc[-1]) if not pd.isna(di_plus.iloc[-1]) else 0.0,
                'di_minus': float(di_minus.iloc[-1]) if not pd.isna(di_minus.iloc[-1]) else 0.0
            }
            
        except Exception as e:
            logger.error(f"ADX calculation error: {e}")
            return {'adx': 0.0, 'di_plus': 0.0, 'di_minus': 0.0}
    
    @staticmethod
    def calculate_ichimoku(high: pd.Series, low: pd.Series, close: pd.Series) -> Dict[str, float]:
        """Calculate Ichimoku Cloud components"""
        try:
            # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
            tenkan_high = high.rolling(window=9).max()
            tenkan_low = low.rolling(window=9).min()
            tenkan_sen = (tenkan_high + tenkan_low) / 2
            
            # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
            kijun_high = high.rolling(window=26).max()
            kijun_low = low.rolling(window=26).min()
            kijun_sen = (kijun_high + kijun_low) / 2
            
            # Senkou Span A: (Tenkan-sen + Kijun-sen) / 2, plotted 26 periods ahead
            senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(26)
            
            # Senkou Span B: (52-period high + 52-period low) / 2, plotted 26 periods ahead
            senkou_high = high.rolling(window=52).max()
            senkou_low = low.rolling(window=52).min()
            senkou_b = ((senkou_high + senkou_low) / 2).shift(26)
            
            # Chikou Span: Close plotted 26 periods behind
            chikou_span = close.shift(-26)
            
            return {
                'tenkan_sen': float(tenkan_sen.iloc[-1]) if not pd.isna(tenkan_sen.iloc[-1]) else 0.0,
                'kijun_sen': float(kijun_sen.iloc[-1]) if not pd.isna(kijun_sen.iloc[-1]) else 0.0,
                'senkou_a': float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0.0,
                'senkou_b': float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0.0,
                'chikou_span': float(chikou_span.iloc[-1]) if not pd.isna(chikou_span.iloc[-1]) else 0.0,
                'current_price': float(close.iloc[-1])
            }
            
        except Exception as e:
            logger.error(f"Ichimoku calculation error: {e}")
            return {
                'tenkan_sen': 0.0, 'kijun_sen': 0.0, 'senkou_a': 0.0,
                'senkou_b': 0.0, 'chikou_span': 0.0, 'current_price': 0.0
            }


class SignalGenerator:
    """
    Advanced signal generation engine that combines multiple indicators
    for comprehensive market analysis and trading signal generation
    """
    
    def __init__(self):
        self.indicators = AdvancedIndicators()
        self.signal_cache_ttl = 300  # 5 minutes
        self.channel_layer = get_channel_layer()
    
    def generate_comprehensive_signal(self, symbol: str, 
                                    market_data: pd.DataFrame) -> Optional[TechnicalSignal]:
        """Generate comprehensive trading signal from multiple indicators"""
        try:
            if len(market_data) < 52:  # Need enough data for calculations
                logger.debug(f"Insufficient data for {symbol}: {len(market_data)} periods")
                return None
            
            current_price = Decimal(str(market_data['close'].iloc[-1]))
            timestamp = timezone.now()
            
            # Calculate all indicators
            indicator_results = self._calculate_all_indicators(market_data)
            
            # Determine trend direction
            trend_direction = self._analyze_trend(indicator_results, market_data)
            
            # Calculate signal strength and type
            signal_strength, signal_type = self._calculate_signal_strength(indicator_results)
            
            # Determine confidence level
            confidence = self._calculate_confidence(indicator_results, signal_strength)
            
            # Calculate risk/reward levels
            target_price, stop_loss, risk_reward = self._calculate_risk_reward(
                current_price, signal_type, indicator_results, market_data
            )
            
            # Assess market conditions
            volatility_level = self._assess_volatility(market_data)
            volume_profile = self._assess_volume(market_data)
            
            signal = TechnicalSignal(
                symbol=symbol,
                timestamp=timestamp,
                signal_type=signal_type,
                confidence=confidence,
                strength=signal_strength,
                indicators=indicator_results,
                trend_direction=trend_direction,
                volatility_level=volatility_level,
                volume_profile=volume_profile,
                trigger_price=current_price,
                target_price=target_price,
                stop_loss=stop_loss,
                risk_reward_ratio=risk_reward
            )
            
            # Cache the signal
            self._cache_signal(signal)
            
            logger.info(f"Generated signal for {symbol}: {signal_type.value} "
                       f"(strength: {signal_strength:.2f}, confidence: {confidence.value})")
            
            return signal
            
        except Exception as e:
            logger.error(f"Signal generation failed for {symbol}: {e}")
            return None
    
    def _calculate_all_indicators(self, data: pd.DataFrame) -> Dict[str, IndicatorResult]:
        """Calculate all available technical indicators"""
        results = {}
        
        try:
            # Basic price data
            close = data['close']
            high = data['high']
            low = data['low']
            volume = data['volume']
            
            # RSI
            rsi_value = self._calculate_rsi(close)
            rsi_signal = self._rsi_to_signal(rsi_value)
            results['rsi'] = IndicatorResult(
                name='rsi',
                value=rsi_value,
                signal_contribution=rsi_signal,
                confidence=0.8 if abs(rsi_signal) > 0.5 else 0.6,
                metadata={'overbought_threshold': 70, 'oversold_threshold': 30}
            )
            
            # MACD
            macd_data = self._calculate_macd(close)
            macd_signal = self._macd_to_signal(macd_data)
            results['macd'] = IndicatorResult(
                name='macd',
                value=macd_data['histogram'],
                signal_contribution=macd_signal,
                confidence=0.75,
                metadata=macd_data
            )
            
            # Stochastic RSI
            stoch_rsi = self.indicators.calculate_stochastic_rsi(close)
            stoch_signal = self._stochastic_to_signal(stoch_rsi)
            results['stochastic_rsi'] = IndicatorResult(
                name='stochastic_rsi',
                value=stoch_rsi['stoch_rsi'],
                signal_contribution=stoch_signal,
                confidence=0.7,
                metadata=stoch_rsi
            )
            
            # Williams %R
            williams_r = self.indicators.calculate_williams_r(high, low, close)
            williams_signal = self._williams_to_signal(williams_r)
            results['williams_r'] = IndicatorResult(
                name='williams_r',
                value=williams_r,
                signal_contribution=williams_signal,
                confidence=0.65,
                metadata={'current_value': williams_r}
            )
            
            # ADX (trend strength)
            adx_data = self.indicators.calculate_adx(high, low, close)
            adx_signal = self._adx_to_signal(adx_data)
            results['adx'] = IndicatorResult(
                name='adx',
                value=adx_data['adx'],
                signal_contribution=adx_signal,
                confidence=0.8 if adx_data['adx'] > 25 else 0.4,
                metadata=adx_data
            )
            
            # Moving Average convergence
            ma_signal = self._calculate_ma_signals(close)
            results['moving_averages'] = IndicatorResult(
                name='moving_averages',
                value=ma_signal['strength'],
                signal_contribution=ma_signal['signal'],
                confidence=0.7,
                metadata=ma_signal
            )
            
            # Volume analysis
            volume_signal = self._analyze_volume_signal(data)
            results['volume'] = IndicatorResult(
                name='volume',
                value=volume_signal['relative_volume'],
                signal_contribution=volume_signal['signal'],
                confidence=0.6,
                metadata=volume_signal
            )
            
        except Exception as e:
            logger.error(f"Indicator calculation error: {e}")
        
        return results
    
    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Calculate RSI value"""
        try:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        except Exception:
            return 50.0
    
    def _rsi_to_signal(self, rsi: float) -> float:
        """Convert RSI to signal contribution (-1.0 to 1.0)"""
        if rsi > 80:
            return -0.8  # Strong sell
        elif rsi > 70:
            return -0.5  # Sell
        elif rsi < 20:
            return 0.8   # Strong buy
        elif rsi < 30:
            return 0.5   # Buy
        else:
            return (50 - rsi) / 50  # Neutral zone scaling
    
    def _calculate_macd(self, close: pd.Series) -> Dict[str, float]:
        """Calculate MACD components"""
        try:
            ema_12 = close.ewm(span=12).mean()
            ema_26 = close.ewm(span=26).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9).mean()
            histogram = macd_line - signal_line
            
            return {
                'macd_line': float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0.0,
                'signal_line': float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0.0,
                'histogram': float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else 0.0
            }
        except Exception:
            return {'macd_line': 0.0, 'signal_line': 0.0, 'histogram': 0.0}
    
    def _macd_to_signal(self, macd_data: Dict[str, float]) -> float:
        """Convert MACD to signal contribution"""
        histogram = macd_data['histogram']
        macd_line = macd_data['macd_line']
        
        # Histogram above/below zero
        histogram_signal = np.tanh(histogram * 10)  # Scale and bound to [-1, 1]
        
        # MACD line trend
        trend_signal = 0.5 if macd_line > 0 else -0.5
        
        return (histogram_signal * 0.7 + trend_signal * 0.3)
    
    def _stochastic_to_signal(self, stoch_data: Dict[str, float]) -> float:
        """Convert Stochastic RSI to signal contribution"""
        stoch_rsi = stoch_data['stoch_rsi']
        
        if stoch_rsi > 80:
            return -0.6  # Overbought
        elif stoch_rsi < 20:
            return 0.6   # Oversold
        else:
            return (50 - stoch_rsi) / 100  # Scaled neutral
    
    def _williams_to_signal(self, williams_r: float) -> float:
        """Convert Williams %R to signal contribution"""
        if williams_r > -20:
            return -0.5  # Overbought
        elif williams_r < -80:
            return 0.5   # Oversold
        else:
            return (williams_r + 50) / 100  # Scaled
    
    def _adx_to_signal(self, adx_data: Dict[str, float]) -> float:
        """Convert ADX to signal contribution (trend strength modifier)"""
        adx = adx_data['adx']
        di_plus = adx_data['di_plus']
        di_minus = adx_data['di_minus']
        
        # Direction signal
        if di_plus > di_minus:
            direction = 0.5
        else:
            direction = -0.5
        
        # Strength modifier (ADX > 25 indicates strong trend)
        strength_modifier = min(adx / 50, 1.0)
        
        return direction * strength_modifier
    
    def _calculate_ma_signals(self, close: pd.Series) -> Dict[str, Any]:
        """Calculate moving average signals"""
        try:
            sma_20 = close.rolling(window=20).mean()
            sma_50 = close.rolling(window=50).mean()
            ema_12 = close.ewm(span=12).mean()
            
            current_price = close.iloc[-1]
            current_sma_20 = sma_20.iloc[-1]
            current_sma_50 = sma_50.iloc[-1]
            current_ema_12 = ema_12.iloc[-1]
            
            # Calculate signals
            signals = []
            
            # Price vs moving averages
            if current_price > current_sma_20:
                signals.append(0.3)
            else:
                signals.append(-0.3)
            
            if current_price > current_sma_50:
                signals.append(0.4)
            else:
                signals.append(-0.4)
            
            # SMA crossover
            if current_sma_20 > current_sma_50:
                signals.append(0.5)
            else:
                signals.append(-0.5)
            
            # EMA vs price
            if current_price > current_ema_12:
                signals.append(0.2)
            else:
                signals.append(-0.2)
            
            total_signal = np.mean(signals)
            strength = abs(total_signal)
            
            return {
                'signal': total_signal,
                'strength': strength,
                'sma_20': float(current_sma_20),
                'sma_50': float(current_sma_50),
                'ema_12': float(current_ema_12),
                'current_price': float(current_price)
            }
            
        except Exception as e:
            logger.error(f"MA signal calculation error: {e}")
            return {'signal': 0.0, 'strength': 0.0}
    
    def _analyze_volume_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume for signal confirmation"""
        try:
            volume = data['volume']
            close = data['close']
            
            # Calculate volume moving averages
            volume_sma = volume.rolling(window=20).mean()
            current_volume = volume.iloc[-1]
            avg_volume = volume_sma.iloc[-1]
            
            # Relative volume
            relative_volume = float(current_volume / avg_volume) if avg_volume > 0 else 1.0
            
            # Price change
            price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
            
            # Volume signal
            if relative_volume > 1.5:  # High volume
                if price_change > 0:
                    signal = 0.4  # Bullish confirmation
                else:
                    signal = -0.4  # Bearish confirmation
            elif relative_volume < 0.5:  # Low volume
                signal = 0.0  # No confirmation
            else:
                signal = 0.1 if price_change > 0 else -0.1
            
            return {
                'signal': signal,
                'relative_volume': relative_volume,
                'current_volume': float(current_volume),
                'average_volume': float(avg_volume),
                'price_change': float(price_change)
            }
            
        except Exception as e:
            logger.error(f"Volume analysis error: {e}")
            return {'signal': 0.0, 'relative_volume': 1.0}
    
    def _analyze_trend(self, indicators: Dict[str, IndicatorResult], 
                      data: pd.DataFrame) -> TrendDirection:
        """Analyze overall trend direction"""
        try:
            # Get trend signals from multiple indicators
            trend_signals = []
            
            # Moving averages trend
            if 'moving_averages' in indicators:
                ma_signal = indicators['moving_averages'].signal_contribution
                trend_signals.append(ma_signal)
            
            # ADX directional movement
            if 'adx' in indicators:
                adx_signal = indicators['adx'].signal_contribution
                trend_signals.append(adx_signal)
            
            # MACD trend
            if 'macd' in indicators:
                macd_signal = indicators['macd'].signal_contribution
                trend_signals.append(macd_signal)
            
            # Price momentum
            close = data['close']
            if len(close) >= 20:
                price_momentum = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
                momentum_signal = np.tanh(price_momentum * 10)
                trend_signals.append(momentum_signal)
            
            # Average trend signal
            avg_signal = np.mean(trend_signals) if trend_signals else 0.0
            
            # Classify trend
            if avg_signal > 0.6:
                return TrendDirection.STRONG_UPTREND
            elif avg_signal > 0.2:
                return TrendDirection.UPTREND
            elif avg_signal > -0.2:
                return TrendDirection.SIDEWAYS
            elif avg_signal > -0.6:
                return TrendDirection.DOWNTREND
            else:
                return TrendDirection.STRONG_DOWNTREND
                
        except Exception as e:
            logger.error(f"Trend analysis error: {e}")
            return TrendDirection.SIDEWAYS
    
    def _calculate_signal_strength(self, indicators: Dict[str, IndicatorResult]) -> Tuple[float, SignalType]:
        """Calculate overall signal strength and type"""
        try:
            # Weight indicators by their confidence
            weighted_signals = []
            total_weight = 0.0
            
            for indicator in indicators.values():
                weight = indicator.confidence
                signal = indicator.signal_contribution
                weighted_signals.append(signal * weight)
                total_weight += weight
            
            # Calculate weighted average
            if total_weight > 0:
                avg_signal = sum(weighted_signals) / total_weight
            else:
                avg_signal = 0.0
            
            # Convert to 0-1 scale
            signal_strength = abs(avg_signal)
            
            # Determine signal type
            if avg_signal > 0.7:
                signal_type = SignalType.STRONG_BUY
            elif avg_signal > 0.4:
                signal_type = SignalType.BUY
            elif avg_signal > 0.1:
                signal_type = SignalType.WEAK_BUY
            elif avg_signal < -0.7:
                signal_type = SignalType.STRONG_SELL
            elif avg_signal < -0.4:
                signal_type = SignalType.SELL
            elif avg_signal < -0.1:
                signal_type = SignalType.WEAK_SELL
            else:
                signal_type = SignalType.NEUTRAL
            
            return signal_strength, signal_type
            
        except Exception as e:
            logger.error(f"Signal strength calculation error: {e}")
            return 0.0, SignalType.NEUTRAL
    
    def _calculate_confidence(self, indicators: Dict[str, IndicatorResult], 
                            signal_strength: float) -> SignalConfidence:
        """Calculate signal confidence level"""
        try:
            # Base confidence on indicator agreement
            signals = [ind.signal_contribution for ind in indicators.values()]
            
            # Calculate consensus (how much indicators agree)
            if len(signals) <= 1:
                consensus = 0.5
            else:
                # Measure signal dispersion
                signal_std = np.std(signals)
                consensus = max(0, 1 - signal_std)
            
            # Combine with signal strength
            confidence_score = (signal_strength * 0.6 + consensus * 0.4)
            
            # Classify confidence
            if confidence_score >= 0.9:
                return SignalConfidence.VERY_HIGH
            elif confidence_score >= 0.75:
                return SignalConfidence.HIGH
            elif confidence_score >= 0.5:
                return SignalConfidence.MEDIUM
            elif confidence_score >= 0.25:
                return SignalConfidence.LOW
            else:
                return SignalConfidence.VERY_LOW
                
        except Exception as e:
            logger.error(f"Confidence calculation error: {e}")
            return SignalConfidence.LOW
    
    def _calculate_risk_reward(self, current_price: Decimal, signal_type: SignalType,
                             indicators: Dict[str, IndicatorResult], 
                             data: pd.DataFrame) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[float]]:
        """Calculate target price, stop loss, and risk/reward ratio"""
        try:
            if signal_type == SignalType.NEUTRAL:
                return None, None, None
            
            price_float = float(current_price)
            
            # Calculate volatility for risk sizing
            close = data['close']
            returns = close.pct_change().dropna()
            volatility = float(returns.std() * np.sqrt(252))  # Annualized volatility
            
            # Risk percentage based on volatility
            risk_pct = min(0.02, max(0.005, volatility * 0.5))  # 0.5% to 2%
            
            is_buy_signal = signal_type in [SignalType.STRONG_BUY, SignalType.BUY, SignalType.WEAK_BUY]
            
            if is_buy_signal:
                # For buy signals
                stop_loss = Decimal(str(price_float * (1 - risk_pct)))
                
                # Target based on signal strength
                if signal_type == SignalType.STRONG_BUY:
                    target_multiplier = 3.0  # 3:1 risk/reward
                elif signal_type == SignalType.BUY:
                    target_multiplier = 2.0  # 2:1 risk/reward
                else:
                    target_multiplier = 1.5  # 1.5:1 risk/reward
                
                target_price = Decimal(str(price_float * (1 + risk_pct * target_multiplier)))
                
            else:
                # For sell signals
                stop_loss = Decimal(str(price_float * (1 + risk_pct)))
                
                # Target based on signal strength
                if signal_type == SignalType.STRONG_SELL:
                    target_multiplier = 3.0
                elif signal_type == SignalType.SELL:
                    target_multiplier = 2.0
                else:
                    target_multiplier = 1.5
                
                target_price = Decimal(str(price_float * (1 - risk_pct * target_multiplier)))
            
            # Calculate risk/reward ratio
            risk = abs(float(current_price - stop_loss))
            reward = abs(float(target_price - current_price))
            risk_reward_ratio = reward / risk if risk > 0 else None
            
            return target_price, stop_loss, risk_reward_ratio
            
        except Exception as e:
            logger.error(f"Risk/reward calculation error: {e}")
            return None, None, None
    
    def _assess_volatility(self, data: pd.DataFrame) -> str:
        """Assess current volatility level"""
        try:
            close = data['close']
            returns = close.pct_change().dropna()
            
            # Calculate recent volatility
            recent_vol = returns.tail(20).std() * np.sqrt(252)
            long_term_vol = returns.std() * np.sqrt(252)
            
            vol_ratio = recent_vol / long_term_vol if long_term_vol > 0 else 1.0
            
            if vol_ratio > 1.5:
                return "high"
            elif vol_ratio < 0.7:
                return "low"
            else:
                return "normal"
                
        except Exception:
            return "normal"
    
    def _assess_volume(self, data: pd.DataFrame) -> str:
        """Assess volume profile"""
        try:
            volume = data['volume']
            recent_volume = volume.tail(5).mean()
            avg_volume = volume.mean()
            
            vol_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
            
            if vol_ratio > 1.5:
                return "high"
            elif vol_ratio < 0.7:
                return "low"
            else:
                return "normal"
                
        except Exception:
            return "normal"
    
    def _cache_signal(self, signal: TechnicalSignal):
        """Cache signal for quick retrieval"""
        try:
            cache_key = f"technical_signal:{signal.symbol}:{signal.timestamp.date()}"
            signal_data = signal.to_dict()
            cache.set(cache_key, signal_data, self.signal_cache_ttl)
        except Exception as e:
            logger.error(f"Signal caching error: {e}")


class EnhancedTechnicalAnalysisService:
    """
    Main service class that orchestrates real-time technical analysis
    Integrates with streaming service and event system for automated signal generation
    """
    
    def __init__(self):
        self.signal_generator = SignalGenerator()
        self.channel_layer = get_channel_layer()
        self.last_analysis: Dict[str, datetime] = {}
        self.analysis_interval = 60  # seconds between analyses per symbol
        self.strong_signal_threshold = 0.7
        
    async def analyze_streaming_data(self, symbol: str, market_data_point: MarketDataPoint) -> Optional[TechnicalSignal]:
        """Analyze streaming market data for signal generation"""
        try:
            # Throttle analysis frequency
            now = timezone.now()
            last_time = self.last_analysis.get(symbol)
            
            if last_time and (now - last_time).total_seconds() < self.analysis_interval:
                return None
            
            self.last_analysis[symbol] = now
            
            # Get historical data for analysis
            historical_data = await self._get_historical_data(symbol)
            if historical_data is None or len(historical_data) < 52:
                logger.debug(f"Insufficient historical data for {symbol}")
                return None
            
            # Add current data point
            current_row = {
                'timestamp': market_data_point.timestamp,
                'open': float(market_data_point.price),  # Use current price as open
                'high': float(market_data_point.price),
                'low': float(market_data_point.price),
                'close': float(market_data_point.price),
                'volume': market_data_point.volume
            }
            
            # Append to historical data
            historical_data = pd.concat([
                historical_data, 
                pd.DataFrame([current_row])
            ], ignore_index=True)
            
            # Generate signal
            signal = self.signal_generator.generate_comprehensive_signal(symbol, historical_data)
            
            if signal:
                # Publish signal event
                await self._publish_signal_event(signal)
                
                # Broadcast via WebSocket
                await self._broadcast_signal(signal)
                
                # Trigger algorithm if strong signal
                if signal.strength >= self.strong_signal_threshold:
                    await self._trigger_algorithm_execution(signal)
            
            return signal
            
        except Exception as e:
            logger.error(f"Streaming analysis failed for {symbol}: {e}")
            return None
    
    async def analyze_symbol_comprehensive(self, symbol: str) -> Optional[TechnicalSignal]:
        """Perform comprehensive analysis on a symbol using latest data"""
        try:
            # Get recent market data
            historical_data = await self._get_historical_data(symbol, periods=200)
            if historical_data is None or len(historical_data) < 52:
                logger.warning(f"Insufficient data for comprehensive analysis of {symbol}")
                return None
            
            # Generate signal
            signal = self.signal_generator.generate_comprehensive_signal(symbol, historical_data)
            
            if signal:
                # Store in database for persistence
                await self._store_signal_in_db(signal)
                
                # Publish events
                await self._publish_signal_event(signal)
                await self._broadcast_signal(signal)
                
                logger.info(f"Comprehensive analysis completed for {symbol}: "
                           f"{signal.signal_type.value} (strength: {signal.strength:.2f})")
            
            return signal
            
        except Exception as e:
            logger.error(f"Comprehensive analysis failed for {symbol}: {e}")
            return None
    
    async def _get_historical_data(self, symbol: str, periods: int = 100) -> Optional[pd.DataFrame]:
        """Get historical market data for analysis"""
        try:
            # Try to get ticker
            ticker = Ticker.objects.filter(symbol=symbol, is_active=True).first()
            if not ticker:
                logger.warning(f"Ticker not found: {symbol}")
                return None
            
            # Get market data from database
            market_data = MarketData.objects.filter(
                ticker=ticker,
                timeframe='1d'
            ).order_by('-timestamp')[:periods]
            
            if not market_data:
                logger.warning(f"No market data found for {symbol}")
                return None
            
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
            
            df = pd.DataFrame(data_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            return df
            
        except Exception as e:
            logger.error(f"Historical data retrieval failed for {symbol}: {e}")
            return None
    
    async def _publish_signal_event(self, signal: TechnicalSignal):
        """Publish technical signal event"""
        try:
            await publish_technical_signal(
                symbol=signal.symbol,
                indicator="comprehensive",
                signal_type=signal.signal_type.value,
                signal_strength=signal.strength,
                indicator_value=signal.strength * 100
            )
            
            logger.debug(f"Published signal event for {signal.symbol}")
            
        except Exception as e:
            logger.error(f"Signal event publishing failed: {e}")
    
    async def _broadcast_signal(self, signal: TechnicalSignal):
        """Broadcast signal via WebSocket"""
        try:
            if not self.channel_layer:
                return
            
            message = {
                'type': 'technical_signal',
                'signal': {
                    'symbol': signal.symbol,
                    'signal_type': signal.signal_type.value,
                    'confidence': signal.confidence.value,
                    'strength': signal.strength,
                    'trend_direction': signal.trend_direction.value,
                    'trigger_price': float(signal.trigger_price),
                    'target_price': float(signal.target_price) if signal.target_price else None,
                    'stop_loss': float(signal.stop_loss) if signal.stop_loss else None,
                    'risk_reward_ratio': signal.risk_reward_ratio,
                    'timestamp': signal.timestamp.isoformat(),
                    'volatility_level': signal.volatility_level,
                    'volume_profile': signal.volume_profile
                }
            }
            
            # Broadcast to symbol-specific group
            await self.channel_layer.group_send(f'market_{signal.symbol}', message)
            
            # Broadcast to technical signals group
            await self.channel_layer.group_send('technical_signals_global', message)
            
            logger.debug(f"Broadcasted signal for {signal.symbol}")
            
        except Exception as e:
            logger.error(f"Signal broadcasting failed: {e}")
    
    async def _trigger_algorithm_execution(self, signal: TechnicalSignal):
        """Trigger algorithm execution for strong signals"""
        try:
            # Only trigger for strong signals
            if signal.strength < self.strong_signal_threshold:
                return
            
            # Determine algorithm type based on signal
            if signal.signal_type in [SignalType.STRONG_BUY, SignalType.BUY]:
                algorithm_type = "MOMENTUM_BUY"
            elif signal.signal_type in [SignalType.STRONG_SELL, SignalType.SELL]:
                algorithm_type = "MOMENTUM_SELL"
            else:
                return
            
            # Create market conditions context
            market_conditions = {
                'signal_strength': signal.strength,
                'confidence': signal.confidence.value,
                'trend_direction': signal.trend_direction.value,
                'volatility': signal.volatility_level,
                'volume_profile': signal.volume_profile,
                'indicators': {name: ind.to_dict() for name, ind in signal.indicators.items()},
                'risk_reward_ratio': signal.risk_reward_ratio
            }
            
            # Publish algorithm trigger event
            await publish_algorithm_trigger(
                algo_order_id=f"AUTO_{signal.signal_id}",
                algorithm_type=algorithm_type,
                trigger_reason=f"Strong technical signal: {signal.signal_type.value}",
                execution_step=1,
                market_conditions=market_conditions,
                user_id=1  # System user for automated triggers
            )
            
            logger.info(f"Triggered {algorithm_type} algorithm for {signal.symbol} "
                       f"(strength: {signal.strength:.2f})")
            
        except Exception as e:
            logger.error(f"Algorithm triggering failed: {e}")
    
    async def _store_signal_in_db(self, signal: TechnicalSignal):
        """Store signal in database for persistence"""
        try:
            ticker = Ticker.objects.filter(symbol=signal.symbol, is_active=True).first()
            if not ticker:
                return
            
            # Store as TechnicalIndicator record
            TechnicalIndicator.objects.create(
                ticker=ticker,
                timestamp=signal.timestamp,
                timeframe='1d',
                indicator_name='comprehensive_signal',
                value=Decimal(str(signal.strength)),
                values=signal.to_dict(),
                parameters={
                    'signal_type': signal.signal_type.value,
                    'confidence': signal.confidence.value,
                    'trend_direction': signal.trend_direction.value
                }
            )
            
            logger.debug(f"Stored signal in database for {signal.symbol}")
            
        except Exception as e:
            logger.error(f"Signal storage failed: {e}")
    
    def get_cached_signal(self, symbol: str) -> Optional[TechnicalSignal]:
        """Get cached signal for symbol"""
        try:
            cache_key = f"technical_signal:{symbol}:{timezone.now().date()}"
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return TechnicalSignal.from_dict(cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Signal cache retrieval failed: {e}")
            return None
    
    def get_service_metrics(self) -> Dict[str, Any]:
        """Get service performance metrics"""
        try:
            return {
                'symbols_analyzed': len(self.last_analysis),
                'analysis_interval': self.analysis_interval,
                'strong_signal_threshold': self.strong_signal_threshold,
                'last_analyses': {
                    symbol: time.isoformat() for symbol, time in self.last_analysis.items()
                }
            }
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return {'error': str(e)}


# Global service instance
enhanced_ta_service = EnhancedTechnicalAnalysisService()
