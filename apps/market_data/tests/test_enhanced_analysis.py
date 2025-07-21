# apps/market_data/tests/test_enhanced_analysis.py
"""
Tests for enhanced technical analysis service
"""

import asyncio
import pytest
from django.test import TestCase
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from django.utils import timezone
import pandas as pd
import numpy as np

from ..analysis.enhanced_service import (
    EnhancedTechnicalAnalysisService, SignalGenerator, TechnicalSignal,
    SignalType, SignalConfidence, TrendDirection, AdvancedIndicators
)
from ..models import Ticker, Exchange, DataSource, MarketData
from ..common import MarketDataPoint


class AdvancedIndicatorsTests(TestCase):
    """Test advanced technical indicators"""
    
    def setUp(self):
        # Create sample data
        np.random.seed(42)  # For reproducible tests
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        prices = 100 + np.cumsum(np.random.randn(100) * 0.02)
        
        self.sample_data = pd.DataFrame({
            'close': prices,
            'high': prices * 1.02,
            'low': prices * 0.98,
            'volume': np.random.randint(1000, 10000, 100)
        })
        
        self.indicators = AdvancedIndicators()
    
    def test_stochastic_rsi_calculation(self):
        """Test Stochastic RSI calculation"""
        result = self.indicators.calculate_stochastic_rsi(self.sample_data['close'])
        
        self.assertIn('stoch_rsi', result)
        self.assertIn('k_percent', result)
        self.assertIn('d_percent', result)
        
        # Values should be between 0 and 100
        self.assertGreaterEqual(result['stoch_rsi'], 0)
        self.assertLessEqual(result['stoch_rsi'], 100)
    
    def test_williams_r_calculation(self):
        """Test Williams %R calculation"""
        result = self.indicators.calculate_williams_r(
            self.sample_data['high'],
            self.sample_data['low'],
            self.sample_data['close']
        )
        
        # Williams %R should be between -100 and 0
        self.assertGreaterEqual(result, -100)
        self.assertLessEqual(result, 0)
    
    def test_cci_calculation(self):
        """Test Commodity Channel Index calculation"""
        result = self.indicators.calculate_cci(
            self.sample_data['high'],
            self.sample_data['low'],
            self.sample_data['close']
        )
        
        self.assertIsInstance(result, float)
        # CCI can range widely, so just check it's a valid number
        self.assertFalse(np.isnan(result))
    
    def test_adx_calculation(self):
        """Test Average Directional Index calculation"""
        result = self.indicators.calculate_adx(
            self.sample_data['high'],
            self.sample_data['low'],
            self.sample_data['close']
        )
        
        self.assertIn('adx', result)
        self.assertIn('di_plus', result)
        self.assertIn('di_minus', result)
        
        # ADX should be between 0 and 100
        self.assertGreaterEqual(result['adx'], 0)
        self.assertLessEqual(result['adx'], 100)
    
    def test_ichimoku_calculation(self):
        """Test Ichimoku Cloud calculation"""
        result = self.indicators.calculate_ichimoku(
            self.sample_data['high'],
            self.sample_data['low'],
            self.sample_data['close']
        )
        
        expected_keys = ['tenkan_sen', 'kijun_sen', 'senkou_a', 'senkou_b', 'chikou_span', 'current_price']
        for key in expected_keys:
            self.assertIn(key, result)
            self.assertIsInstance(result[key], float)


class SignalGeneratorTests(TestCase):
    """Test signal generation functionality"""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create test data
        self.data_source = DataSource.objects.create(
            name="Test Source", code="TEST", requires_api_key=False
        )
        self.exchange = Exchange.objects.create(
            name="NASDAQ", code="NASDAQ", country="US", currency="USD"
        )
        self.ticker = Ticker.objects.create(
            symbol="AAPL", name="Apple Inc", exchange=self.exchange, data_source=self.data_source
        )
        
        # Create sample market data
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        prices = 150 + np.cumsum(np.random.randn(100) * 0.5)
        
        self.market_data = pd.DataFrame({
            'close': prices,
            'open': prices + np.random.randn(100) * 0.1,
            'high': prices + np.abs(np.random.randn(100) * 0.3),
            'low': prices - np.abs(np.random.randn(100) * 0.3),
            'volume': np.random.randint(10000, 100000, 100)
        })
        
        self.signal_generator = SignalGenerator()
    
    def tearDown(self):
        self.loop.close()
    
    def test_signal_generation_with_sufficient_data(self):
        """Test signal generation with adequate market data"""
        signal = self.signal_generator.generate_comprehensive_signal("AAPL", self.market_data)
        
        self.assertIsNotNone(signal)
        self.assertIsInstance(signal, TechnicalSignal)
        self.assertEqual(signal.symbol, "AAPL")
        self.assertIsInstance(signal.signal_type, SignalType)
        self.assertIsInstance(signal.confidence, SignalConfidence)
        self.assertIsInstance(signal.trend_direction, TrendDirection)
        
        # Strength should be between 0 and 1
        self.assertGreaterEqual(signal.strength, 0.0)
        self.assertLessEqual(signal.strength, 1.0)
    
    def test_signal_generation_insufficient_data(self):
        """Test signal generation with insufficient data"""
        small_data = self.market_data.head(20)  # Only 20 periods
        signal = self.signal_generator.generate_comprehensive_signal("AAPL", small_data)
        
        self.assertIsNone(signal)
    
    def test_rsi_signal_conversion(self):
        """Test RSI to signal conversion"""
        # Test overbought condition
        oversold_signal = self.signal_generator._rsi_to_signal(25)
        self.assertGreater(oversold_signal, 0)  # Should be bullish
        
        # Test oversold condition
        overbought_signal = self.signal_generator._rsi_to_signal(75)
        self.assertLess(overbought_signal, 0)  # Should be bearish
        
        # Test neutral condition
        neutral_signal = self.signal_generator._rsi_to_signal(50)
        self.assertEqual(neutral_signal, 0.0)
    
    def test_trend_analysis(self):
        """Test trend direction analysis"""
        # Create mock indicators
        mock_indicators = {
            'moving_averages': MagicMock(signal_contribution=0.7),
            'adx': MagicMock(signal_contribution=0.6),
            'macd': MagicMock(signal_contribution=0.5)
        }
        
        trend = self.signal_generator._analyze_trend(mock_indicators, self.market_data)
        
        self.assertIsInstance(trend, TrendDirection)
    
    def test_signal_strength_calculation(self):
        """Test signal strength and type calculation"""
        # Create mock indicators with strong bullish signals
        mock_indicators = {
            'rsi': MagicMock(signal_contribution=0.8, confidence=0.9),
            'macd': MagicMock(signal_contribution=0.7, confidence=0.8),
            'adx': MagicMock(signal_contribution=0.6, confidence=0.7)
        }
        
        strength, signal_type = self.signal_generator._calculate_signal_strength(mock_indicators)
        
        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)
        self.assertIsInstance(signal_type, SignalType)
    
    def test_confidence_calculation(self):
        """Test signal confidence calculation"""
        # High agreement indicators
        mock_indicators = {
            'rsi': MagicMock(signal_contribution=0.8),
            'macd': MagicMock(signal_contribution=0.75),
            'adx': MagicMock(signal_contribution=0.85)
        }
        
        confidence = self.signal_generator._calculate_confidence(mock_indicators, 0.8)
        self.assertIsInstance(confidence, SignalConfidence)
    
    @patch('apps.market_data.analysis.enhanced_service.cache')
    def test_signal_caching(self, mock_cache):
        """Test signal caching functionality"""
        mock_cache.set.return_value = True
        
        signal = TechnicalSignal(
            symbol="AAPL",
            timestamp=timezone.now(),
            signal_type=SignalType.BUY,
            confidence=SignalConfidence.HIGH,
            strength=0.8,
            indicators={},
            trend_direction=TrendDirection.UPTREND,
            volatility_level="normal",
            volume_profile="normal",
            trigger_price=Decimal("150.00")
        )
        
        self.signal_generator._cache_signal(signal)
        
        # Verify cache.set was called
        mock_cache.set.assert_called_once()


class EnhancedTechnicalAnalysisServiceTests(TestCase):
    """Test the main enhanced TA service"""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create test data
        self.data_source = DataSource.objects.create(
            name="Test Source", code="TEST", requires_api_key=False
        )
        self.exchange = Exchange.objects.create(
            name="NASDAQ", code="NASDAQ", country="US", currency="USD"
        )
        self.ticker = Ticker.objects.create(
            symbol="AAPL", name="Apple Inc", exchange=self.exchange, data_source=self.data_source
        )
        
        self.service = EnhancedTechnicalAnalysisService()
    
    def tearDown(self):
        self.loop.close()
    
    def test_service_initialization(self):
        """Test service initializes correctly"""
        self.assertIsNotNone(self.service.signal_generator)
        self.assertIsNotNone(self.service.channel_layer)
        self.assertEqual(self.service.analysis_interval, 60)
        self.assertEqual(self.service.strong_signal_threshold, 0.7)
    
    def test_service_metrics_collection(self):
        """Test service metrics collection"""
        metrics = self.service.get_service_metrics()
        
        self.assertIn('symbols_analyzed', metrics)
        self.assertIn('analysis_interval', metrics)
        self.assertIn('strong_signal_threshold', metrics)
        self.assertIn('last_analyses', metrics)
    
    @patch('apps.market_data.analysis.enhanced_service.cache')
    def test_cached_signal_retrieval(self, mock_cache):
        """Test cached signal retrieval"""
        # Mock cached signal data
        mock_signal_data = {
            'symbol': 'AAPL',
            'timestamp': timezone.now().isoformat(),
            'signal_type': 'buy',
            'confidence': 'high',
            'strength': 0.8,
            'indicators': {},
            'trend_direction': 'uptrend',
            'volatility_level': 'normal',
            'volume_profile': 'normal',
            'trigger_price': '150.00',
            'target_price': None,
            'stop_loss': None,
            'risk_reward_ratio': None,
            'signal_id': 'test-123',
            'correlation_id': None
        }
        
        mock_cache.get.return_value = mock_signal_data
        
        signal = self.service.get_cached_signal("AAPL")
        
        self.assertIsNotNone(signal)
        self.assertEqual(signal.symbol, "AAPL")
        self.assertEqual(signal.signal_type, SignalType.BUY)
    
    def test_analysis_frequency_throttling(self):
        """Test that analysis is properly throttled"""
        symbol = "AAPL"
        
        # Record first analysis time
        now = timezone.now()
        self.service.last_analysis[symbol] = now
        
        # Create mock market data point
        mock_data_point = MarketDataPoint(
            symbol=symbol,
            timestamp=now,
            price=Decimal("150.00"),
            volume=1000
        )
        
        # Analysis should be throttled (returning None)
        with patch.object(self.service, '_get_historical_data') as mock_get_data:
            result = self.loop.run_until_complete(
                self.service.analyze_streaming_data(symbol, mock_data_point)
            )
            
            self.assertIsNone(result)
            mock_get_data.assert_not_called()
