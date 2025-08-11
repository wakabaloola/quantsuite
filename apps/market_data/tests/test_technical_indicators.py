"""
Tests for technical indicators in market_data app
"""

import pytest
import pandas as pd
import numpy as np
from decimal import Decimal
from apps.market_data.technical_analysis import (
    MovingAverageIndicator,
    MomentumIndicator,
    VolatilityIndicator
)

@pytest.fixture
def sample_data():
    return pd.DataFrame({
        'open': [100, 101, 102, 101, 100, 99, 98, 97, 98, 99],
        'high': [101, 102, 103, 102, 101, 100, 99, 98, 99, 100],
        'low': [99, 100, 101, 100, 99, 98, 97, 96, 97, 98],
        'close': [100.5, 101.2, 102.0, 101.5, 100.2, 99.5, 98.8, 97.5, 98.2, 99.0],
        'volume': [10000, 12000, 15000, 11000, 9000, 8000, 7000, 7500, 8500, 9000]
    })

def test_sma_calculation(sample_data):
    indicator = MovingAverageIndicator()
    result = indicator.calculate(sample_data, periods=[3], ma_types=['sma'])
    sma = result['sma_3']['current_value']
    assert isinstance(sma, Decimal)
    assert 99.0 < float(sma) < 101.0

def test_rsi_calculation(sample_data):
    indicator = MomentumIndicator()
    result = indicator.calculate(sample_data, indicators=['rsi'])
    rsi = result['rsi']['current_value']
    assert isinstance(rsi, Decimal)
    assert 0 <= float(rsi) <= 100

def test_bollinger_bands(sample_data):
    indicator = VolatilityIndicator()
    result = indicator.calculate(sample_data, indicators=['bollinger_bands'])
    assert 'upper_band' in result['bollinger_bands']
    assert 'lower_band' in result['bollinger_bands']
    assert 'middle_band' in result['bollinger_bands']

def test_macd_calculation(sample_data):
    indicator = MomentumIndicator()
    result = indicator.calculate(sample_data, indicators=['macd'])
    assert 'macd_line' in result['macd']
    assert 'signal_line' in result['macd']

def test_indicator_with_insufficient_data(sample_data):
    indicator = MovingAverageIndicator()
    with pytest.raises(ValueError):
        indicator.calculate(sample_data[:2], periods=[20])

def test_indicator_with_invalid_data():
    indicator = MomentumIndicator()
    with pytest.raises(ValueError):
        indicator.calculate(pd.DataFrame(), indicators=['rsi'])

def test_custom_momentum_indicator(sample_data):
    from apps.market_data.technical_analysis import CustomMomentumIndicator
    indicator = CustomMomentumIndicator()
    result = indicator.calculate(sample_data, period=10, volume_factor=0.5)
    assert 'current_value' in result
    assert 'signal' in result
    assert result['signal'] in ['neutral', 'bullish', 'bearish']
