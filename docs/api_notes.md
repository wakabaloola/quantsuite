# QSuite Quantitative Research Platform - API Documentation

## 🎯 Executive Summary

Comprehensive API documentation for QSuite's quantitative research platform, providing professional-grade endpoints for global market data, technical analysis, portfolio analytics, backtesting, and real-time data streaming. Designed for quantitative researchers, analysts, and algorithmic trading professionals.

## **Key Features Covered:**

### **Global Market Data Integration**
- **yfinance & Alpha Vantage APIs** with on-demand fetching
- **Multi-exchange support** (US, UK, Greece, global markets)
- **Flexible timeframes** (1m to monthly, user-selectable)
- **User-controlled sync** (no automatic downloads)

### **Professional Technical Analysis**
- **Built-in indicators** (RSI, MACD, Bollinger Bands, multiple MA types)
- **Extension framework** for custom indicators with clear examples
- **Real-time calculations** with caching for performance

### **Portfolio Analytics Suite**
- **Professional metrics** (Sharpe, Sortino, VaR, correlation matrices)
- **Risk analytics** (Monte Carlo, drawdown analysis)
- **Custom analytics framework** for researchers to add their own metrics

### **Backtesting Engine**
- **Strategy framework** with clear base classes
- **Walk-forward analysis** and Monte Carlo testing
- **Professional performance metrics** and trade logging

### **Multi-Format Export**
- **JSON, CSV, Pandas-compatible** formats
- **Excel export** for portfolios
- **Real-time streaming** via WebSockets

### **Comprehensive Screening**
- **Technical screening** (RSI, volume, price patterns)
- **Fundamental screening** (P/E, ROE, debt ratios)
- **Custom screening framework** for researchers

## 🚀 **Ready for Implementation:**

The documentation includes:
- ✅ **Complete API specifications** with request/response examples
- ✅ **Python client examples** for immediate use
- ✅ **Jupyter notebook integration** patterns
- ✅ **Extension frameworks** with clear examples for custom development
- ✅ **Professional usage patterns** for quantitative research workflows

## 🔧 **Next Steps:**

1. **Review the API structure** - does this match your vision?
2. **Implementation priority** - which endpoints should we build first?
3. **Custom extensions** - any specific indicators or analytics you want to prioritize?

---
---

## 🏗️ API Architecture Overview

### Base URL
```
Development: http://localhost:8000/api/v1/
Production: https://quantsuite.io/api/v1/
```

### Authentication
All API endpoints require JWT authentication:
```http
Authorization: Bearer <your-jwt-token>
```

### Response Formats
- **JSON** (default): Standard API responses
- **CSV**: Add `?format=csv` to any endpoint
- **Pandas**: Add `?format=pandas` for DataFrame-compatible JSON

### Rate Limits
- **Authenticated users**: 1000 requests/hour
- **Premium tier**: 10,000 requests/hour
- **Data ingestion**: 100 requests/minute

---

## 📊 Market Data APIs

### Core Market Data Models

#### DataSource Management
```http
GET    /api/v1/data-sources/
POST   /api/v1/data-sources/
GET    /api/v1/data-sources/{id}/
PUT    /api/v1/data-sources/{id}/
DELETE /api/v1/data-sources/{id}/
```

**Example Response:**
```json
{
  "id": 1,
  "name": "Yahoo Finance",
  "code": "YAHOO",
  "url": "https://finance.yahoo.com",
  "is_active": true,
  "supported_markets": ["US", "UK", "EU", "ASIA"],
  "supported_timeframes": ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"],
  "rate_limit": 2000
}
```

#### Ticker Management
```http
GET    /api/v1/tickers/
POST   /api/v1/tickers/
GET    /api/v1/tickers/{symbol}/
PUT    /api/v1/tickers/{symbol}/
DELETE /api/v1/tickers/{symbol}/
```

**Enhanced Ticker Response:**
```json
{
  "id": 1,
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "currency": "USD",
  "country": "US",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "market_cap": 3000000000000,
  "data_source": {
    "id": 1,
    "name": "Yahoo Finance",
    "code": "YAHOO"
  },
  "is_active": true,
  "last_updated": "2025-06-09T16:30:00Z"
}
```

#### Advanced Ticker Filtering
```http
# Search by multiple criteria
GET /api/v1/tickers/?search=apple&sector=Technology&country=US

# Filter by market cap range
GET /api/v1/tickers/?market_cap_min=1000000000&market_cap_max=5000000000

# Filter by exchange
GET /api/v1/tickers/?exchange=NASDAQ,NYSE,LSE

# Get all Greek stocks
GET /api/v1/tickers/?country=GR&exchange=ATHEX
```

### Market Data Endpoints

#### Historical Data
```http
GET /api/v1/market-data/{symbol}/
GET /api/v1/market-data/{symbol}/history/
```

**Query Parameters:**
- `period`: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
- `interval`: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
- `start`: YYYY-MM-DD format
- `end`: YYYY-MM-DD format
- `format`: json, csv, pandas

**Example Request:**
```http
GET /api/v1/market-data/AAPL/history/?period=1y&interval=1d&format=json
```

**Example Response:**
```json
{
  "symbol": "AAPL",
  "period": "1y",
  "interval": "1d",
  "data": [
    {
      "timestamp": "2024-06-09T21:00:00Z",
      "open": 150.25,
      "high": 152.80,
      "low": 149.50,
      "close": 151.75,
      "volume": 45234567,
      "adjusted_close": 151.75
    }
  ],
  "total_records": 252,
  "currency": "USD",
  "exchange": "NASDAQ"
}
```

#### Real-time Data
```http
GET /api/v1/market-data/{symbol}/quote/
GET /api/v1/market-data/quotes/?symbols=AAPL,GOOGL,MSFT
```

**Real-time Quote Response:**
```json
{
  "symbol": "AAPL",
  "price": 151.75,
  "change": 2.35,
  "change_percent": 1.57,
  "volume": 45234567,
  "avg_volume": 52000000,
  "market_cap": 3000000000000,
  "pe_ratio": 28.5,
  "timestamp": "2025-06-09T20:59:45Z",
  "market_status": "open",
  "bid": 151.70,
  "ask": 151.80,
  "bid_size": 100,
  "ask_size": 200
}
```

### Global Market Data Integration

#### yfinance Integration
```http
POST /api/v1/integrations/yfinance/fetch/
GET  /api/v1/integrations/yfinance/search/
```

**Fetch Data from yfinance:**
```json
{
  "symbols": ["AAPL", "GOOGL", "0005.HK", "ASML.AS"],
  "period": "1mo",
  "interval": "1d",
  "auto_save": true,
  "update_ticker_info": true
}
```

**Global Symbol Search:**
```http
GET /api/v1/integrations/yfinance/search/?query=apple&country=US
```

**Search Response:**
```json
{
  "results": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "exchange": "NASDAQ",
      "country": "US",
      "currency": "USD"
    },
    {
      "symbol": "AAPL.L",
      "name": "Apple Inc.",
      "exchange": "LSE",
      "country": "UK",
      "currency": "GBP"
    }
  ]
}
```

#### Alpha Vantage Integration
```http
POST /api/v1/integrations/alphavantage/fetch/
GET  /api/v1/integrations/alphavantage/fundamentals/{symbol}/
```

**Fetch with Alpha Vantage:**
```json
{
  "symbol": "AAPL",
  "function": "TIME_SERIES_DAILY",
  "outputsize": "full",
  "auto_save": true
}
```

**Fundamental Data:**
```json
{
  "symbol": "AAPL",
  "overview": {
    "market_cap": 3000000000000,
    "pe_ratio": 28.5,
    "peg_ratio": 2.1,
    "price_to_book": 8.2,
    "return_on_equity": 0.175,
    "debt_to_equity": 1.73
  },
  "income_statement": {...},
  "balance_sheet": {...},
  "cash_flow": {...}
}
```

---

## 📈 Technical Analysis APIs

### Built-in Technical Indicators

#### Moving Averages
```http
GET /api/v1/technical/moving-averages/{symbol}/
```

**Query Parameters:**
- `type`: sma, ema, wma, hull, tema, dema
- `periods`: comma-separated list (e.g., "10,20,50,200")
- `timeframe`: 1d, 1h, 30m, etc.

**Example:**
```http
GET /api/v1/technical/moving-averages/AAPL/?type=sma,ema&periods=20,50,200&timeframe=1d
```

**Response:**
```json
{
  "symbol": "AAPL",
  "timeframe": "1d",
  "indicators": {
    "sma_20": [
      {"date": "2025-06-09", "value": 149.25},
      {"date": "2025-06-08", "value": 148.80}
    ],
    "ema_20": [
      {"date": "2025-06-09", "value": 150.15},
      {"date": "2025-06-08", "value": 149.90}
    ]
  },
  "current_price": 151.75,
  "signals": {
    "price_above_sma_20": true,
    "price_above_ema_50": true,
    "golden_cross": false
  }
}
```

#### Momentum Indicators
```http
GET /api/v1/technical/momentum/{symbol}/
```

**Available Indicators:**
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Stochastic Oscillator
- Williams %R
- CCI (Commodity Channel Index)

**Example:**
```http
GET /api/v1/technical/momentum/AAPL/?indicators=rsi,macd&period=14
```

**Response:**
```json
{
  "symbol": "AAPL",
  "indicators": {
    "rsi": {
      "current_value": 65.2,
      "signal": "neutral",
      "overbought_threshold": 70,
      "oversold_threshold": 30,
      "history": [
        {"date": "2025-06-09", "value": 65.2},
        {"date": "2025-06-08", "value": 63.8}
      ]
    },
    "macd": {
      "macd_line": 2.35,
      "signal_line": 1.98,
      "histogram": 0.37,
      "signal": "bullish",
      "history": [...]
    }
  }
}
```

#### Volatility Indicators
```http
GET /api/v1/technical/volatility/{symbol}/
```

**Available Indicators:**
- Bollinger Bands
- Average True Range (ATR)
- Keltner Channels
- Donchian Channels

**Example Response:**
```json
{
  "symbol": "AAPL",
  "bollinger_bands": {
    "upper_band": 155.20,
    "middle_band": 150.00,
    "lower_band": 144.80,
    "bandwidth": 6.93,
    "percent_b": 0.68,
    "squeeze": false
  },
  "atr": {
    "current_value": 3.45,
    "period": 14,
    "volatility_rating": "medium"
  }
}
```

### Custom Technical Indicators

#### Register Custom Indicator
```http
POST /api/v1/technical/custom-indicators/
```

**Example Custom Indicator:**
```json
{
  "name": "custom_momentum",
  "description": "Custom momentum indicator",
  "formula": "def calculate(prices, period=14): return (prices[-1] - prices[-period]) / prices[-period] * 100",
  "parameters": {
    "period": {"type": "int", "default": 14, "min": 1, "max": 100}
  },
  "output_type": "single_value",
  "category": "momentum"
}
```

#### Calculate Custom Indicator
```http
GET /api/v1/technical/custom-indicators/{name}/{symbol}/
```

**Extension Framework for Quants:**
```python
# apps/technical/custom_indicators.py

class CustomIndicatorBase:
    """Base class for implementing custom technical indicators"""
    
    def __init__(self, name, description, parameters=None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
    
    def calculate(self, data, **kwargs):
        """
        Override this method to implement your indicator logic
        
        Args:
            data: DataFrame with OHLCV data
            **kwargs: Additional parameters
            
        Returns:
            dict: Indicator values with timestamps
        """
        raise NotImplementedError
    
    def validate_parameters(self, **kwargs):
        """Validate input parameters"""
        for param, value in kwargs.items():
            if param in self.parameters:
                param_config = self.parameters[param]
                if 'min' in param_config and value < param_config['min']:
                    raise ValueError(f"{param} must be >= {param_config['min']}")
                if 'max' in param_config and value > param_config['max']:
                    raise ValueError(f"{param} must be <= {param_config['max']}")

# Example implementation
class CustomRSI(CustomIndicatorBase):
    def __init__(self):
        super().__init__(
            name="custom_rsi",
            description="Custom RSI implementation with additional features",
            parameters={
                "period": {"type": "int", "default": 14, "min": 2, "max": 100},
                "overbought": {"type": "float", "default": 70, "min": 50, "max": 95},
                "oversold": {"type": "float", "default": 30, "min": 5, "max": 50}
            }
        )
    
    def calculate(self, data, period=14, overbought=70, oversold=30):
        # Your custom RSI implementation here
        prices = data['close']
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return {
            "values": rsi.to_dict(),
            "current_value": float(rsi.iloc[-1]),
            "signal": "overbought" if rsi.iloc[-1] > overbought else "oversold" if rsi.iloc[-1] < oversold else "neutral",
            "parameters": {"period": period, "overbought": overbought, "oversold": oversold}
        }
```

---

## 💼 Portfolio Analytics APIs

### Portfolio Management
```http
GET    /api/v1/portfolios/
POST   /api/v1/portfolios/
GET    /api/v1/portfolios/{id}/
PUT    /api/v1/portfolios/{id}/
DELETE /api/v1/portfolios/{id}/
```

**Create Portfolio:**
```json
{
  "name": "US Tech Growth",
  "description": "Technology growth stocks portfolio",
  "base_currency": "USD",
  "positions": [
    {"symbol": "AAPL", "quantity": 100, "avg_cost": 150.00},
    {"symbol": "GOOGL", "quantity": 50, "avg_cost": 2800.00},
    {"symbol": "MSFT", "quantity": 75, "avg_cost": 350.00}
  ]
}
```

### Portfolio Analytics
```http
GET /api/v1/portfolios/{id}/analytics/
GET /api/v1/portfolios/{id}/performance/
GET /api/v1/portfolios/{id}/risk-metrics/
```

**Analytics Response:**
```json
{
  "portfolio_id": 1,
  "as_of_date": "2025-06-09",
  "total_value": 475000.00,
  "total_cost": 450000.00,
  "unrealized_pnl": 25000.00,
  "unrealized_pnl_percent": 5.56,
  "day_change": 2350.00,
  "day_change_percent": 0.50,
  
  "performance_metrics": {
    "total_return": 0.0556,
    "annualized_return": 0.1245,
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.12,
    "calmar_ratio": 1.76,
    "max_drawdown": -0.0892,
    "volatility": 0.1456,
    "beta": 1.12,
    "alpha": 0.0234,
    "information_ratio": 0.78
  },
  
  "risk_metrics": {
    "value_at_risk_95": -15250.00,
    "conditional_var_95": -22100.00,
    "expected_shortfall": -19875.00,
    "downside_deviation": 0.0876,
    "tracking_error": 0.0234
  },
  
  "sector_allocation": {
    "Technology": 0.65,
    "Healthcare": 0.20,
    "Financial": 0.15
  },
  
  "geographic_allocation": {
    "US": 0.80,
    "Europe": 0.15,
    "Asia": 0.05
  }
}
```

### Correlation Analysis
```http
GET /api/v1/portfolios/{id}/correlations/
POST /api/v1/analytics/correlation-matrix/
```

**Correlation Matrix Request:**
```json
{
  "symbols": ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
  "period": "1y",
  "method": "pearson"
}
```

**Response:**
```json
{
  "correlation_matrix": {
    "AAPL": {"AAPL": 1.0, "GOOGL": 0.73, "MSFT": 0.81, "AMZN": 0.65, "TSLA": 0.42},
    "GOOGL": {"AAPL": 0.73, "GOOGL": 1.0, "MSFT": 0.78, "AMZN": 0.71, "TSLA": 0.38},
    "MSFT": {"AAPL": 0.81, "GOOGL": 0.78, "MSFT": 1.0, "AMZN": 0.69, "TSLA": 0.35}
  },
  "heatmap_url": "/api/v1/analytics/correlation-matrix/1/heatmap.png"
}
```

### Risk Analysis
```http
POST /api/v1/analytics/var-calculation/
POST /api/v1/analytics/monte-carlo-simulation/
```

**Monte Carlo Simulation:**
```json
{
  "portfolio_id": 1,
  "time_horizon": 252,
  "simulations": 10000,
  "confidence_levels": [0.95, 0.99],
  "method": "geometric_brownian_motion"
}
```

### Custom Portfolio Analytics

**Extension Framework:**
```python
# apps/portfolio/custom_analytics.py

class CustomAnalyticsBase:
    """Base class for custom portfolio analytics"""
    
    def calculate(self, portfolio_data, market_data, **kwargs):
        """
        Override this method to implement custom analytics
        
        Args:
            portfolio_data: Portfolio positions and values
            market_data: Historical price data
            **kwargs: Additional parameters
            
        Returns:
            dict: Analytics results
        """
        raise NotImplementedError

class CustomSharpeRatio(CustomAnalyticsBase):
    """Example: Custom Sharpe ratio with adjustable risk-free rate"""
    
    def calculate(self, portfolio_data, market_data, risk_free_rate=0.02, period=252):
        returns = portfolio_data['returns']
        excess_returns = returns - risk_free_rate/period
        
        return {
            "sharpe_ratio": excess_returns.mean() / excess_returns.std() * (period ** 0.5),
            "annualized_return": returns.mean() * period,
            "annualized_volatility": returns.std() * (period ** 0.5),
            "risk_free_rate": risk_free_rate
        }
```

---

## 🔬 Backtesting Engine

### Backtest Creation
```http
POST /api/v1/backtests/
GET  /api/v1/backtests/
GET  /api/v1/backtests/{id}/
```

**Create Backtest:**
```json
{
  "name": "Golden Cross Strategy",
  "description": "Buy when 50-day MA crosses above 200-day MA",
  "strategy_code": "golden_cross_strategy",
  "parameters": {
    "fast_ma": 50,
    "slow_ma": 200,
    "position_size": 1000
  },
  "universe": ["AAPL", "GOOGL", "MSFT"],
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 100000,
  "commission": 0.001,
  "slippage": 0.0005
}
```

### Strategy Implementation Framework
```python
# apps/backtesting/strategies.py

class StrategyBase:
    """Base class for implementing trading strategies"""
    
    def __init__(self, name, parameters=None):
        self.name = name
        self.parameters = parameters or {}
        self.positions = {}
        self.orders = []
        self.equity_curve = []
    
    def initialize(self, context):
        """Initialize strategy with market data context"""
        pass
    
    def handle_data(self, context, data):
        """
        Main strategy logic - called for each bar
        
        Args:
            context: Strategy context with portfolio, datetime, etc.
            data: Current market data for all symbols
        """
        raise NotImplementedError
    
    def before_trading_start(self, context, data):
        """Called before each trading day"""
        pass
    
    def after_trading_end(self, context, data):
        """Called after each trading day"""
        pass

# Example Strategy Implementation
class GoldenCrossStrategy(StrategyBase):
    def __init__(self, fast_ma=50, slow_ma=200, position_size=1000):
        super().__init__("Golden Cross Strategy", {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "position_size": position_size
        })
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.position_size = position_size
    
    def handle_data(self, context, data):
        for symbol in context.universe:
            # Get price history
            prices = data.history(symbol, 'close', self.slow_ma + 1)
            
            if len(prices) < self.slow_ma:
                continue
            
            # Calculate moving averages
            fast_ma = prices[-self.fast_ma:].mean()
            slow_ma = prices[-self.slow_ma:].mean()
            prev_fast_ma = prices[-(self.fast_ma+1):-1].mean()
            prev_slow_ma = prices[-(self.slow_ma+1):-1].mean()
            
            # Check for golden cross (fast MA crosses above slow MA)
            golden_cross = (fast_ma > slow_ma) and (prev_fast_ma <= prev_slow_ma)
            death_cross = (fast_ma < slow_ma) and (prev_fast_ma >= prev_slow_ma)
            
            current_position = context.portfolio.positions[symbol].amount
            
            if golden_cross and current_position == 0:
                # Buy signal
                shares = self.position_size // data.current(symbol, 'close')
                context.order(symbol, shares)
            
            elif death_cross and current_position > 0:
                # Sell signal
                context.order_target(symbol, 0)
```

### Backtest Execution
```http
POST /api/v1/backtests/{id}/run/
GET  /api/v1/backtests/{id}/status/
GET  /api/v1/backtests/{id}/results/
```

**Backtest Results:**
```json
{
  "backtest_id": 1,
  "status": "completed",
  "execution_time": 23.45,
  "total_return": 0.2567,
  "annualized_return": 0.1234,
  "max_drawdown": -0.0892,
  "sharpe_ratio": 1.85,
  "sortino_ratio": 2.12,
  "calmar_ratio": 1.76,
  "win_rate": 0.67,
  "profit_factor": 1.45,
  "total_trades": 234,
  "winning_trades": 157,
  "losing_trades": 77,
  "avg_win": 0.0234,
  "avg_loss": -0.0156,
  "largest_win": 0.0892,
  "largest_loss": -0.0567,
  
  "monthly_returns": [
    {"month": "2020-01", "return": 0.0234},
    {"month": "2020-02", "return": -0.0145}
  ],
  
  "equity_curve": [
    {"date": "2020-01-01", "value": 100000},
    {"date": "2020-01-02", "value": 100234}
  ],
  
  "trade_log": [
    {
      "date": "2020-01-15",
      "symbol": "AAPL",
      "action": "BUY",
      "quantity": 100,
      "price": 150.25,
      "commission": 1.50
    }
  ]
}
```

### Advanced Backtesting Features
```http
POST /api/v1/backtests/walk-forward-analysis/
POST /api/v1/backtests/monte-carlo-analysis/
POST /api/v1/backtests/sensitivity-analysis/
```

**Walk Forward Analysis:**
```json
{
  "strategy": "golden_cross_strategy",
  "universe": ["AAPL", "GOOGL", "MSFT"],
  "start_date": "2015-01-01",
  "end_date": "2024-12-31",
  "train_period": 252,
  "test_period": 63,
  "step_size": 21,
  "optimization_metric": "sharpe_ratio"
}
```

---

## 🔍 Screening & Filtering APIs

### Stock Screeners

#### Technical Screening
```http
POST /api/v1/screening/technical/
```

**Technical Screen Request:**
```json
{
  "criteria": [
    {
      "indicator": "rsi",
      "period": 14,
      "operator": "<",
      "value": 30,
      "description": "RSI oversold"
    },
    {
      "indicator": "price_vs_sma",
      "period": 50,
      "operator": ">",
      "value": 1.05,
      "description": "Price 5% above 50-day MA"
    },
    {
      "indicator": "volume_ratio",
      "period": 10,
      "operator": ">",
      "value": 1.5,
      "description": "Volume 50% above 10-day average"
    }
  ],
  "universe": "SP500",
  "limit": 50
}
```

#### Fundamental Screening
```http
POST /api/v1/screening/fundamental/
```

**Fundamental Screen Request:**
```json
{
  "criteria": [
    {
      "metric": "pe_ratio",
      "operator": "<",
      "value": 15,
      "description": "P/E ratio less than 15"
    },
    {
      "metric": "debt_to_equity",
      "operator": "<",
      "value": 0.5,
      "description": "Low debt"
    },
    {
      "metric": "roe",
      "operator": ">",
      "value": 0.15,
      "description": "ROE greater than 15%"
    },
    {
      "metric": "revenue_growth_3y",
      "operator": ">",
      "value": 0.10,
      "description": "3-year revenue growth > 10%"
    }
  ],
  "sector": ["Technology", "Healthcare"],
  "market_cap_min": 1000000000,
  "limit": 100
}
```

**Screening Response:**
```json
{
  "total_matches": 23,
  "criteria_summary": {
    "technical_filters": 3,
    "fundamental_filters": 4,
    "universe_size": 500
  },
  "results": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "price": 151.75,
      "market_cap": 3000000000000,
      "sector": "Technology",
      "criteria_scores": {
        "rsi_14": 28.5,
        "price_vs_sma_50": 1.07,
        "volume_ratio_10": 1.8,
        "pe_ratio": 12.5,
        "debt_to_equity": 0.35,
        "roe": 0.18
      },
      "overall_score": 8.5
    }
  ]
}
```

### Custom Screening

#### Create Custom Screen
```http
POST /api/v1/screening/custom/
```

**Custom Screen Framework:**
```python
# apps/screening/custom_screens.py

class CustomScreenBase:
    """Base class for implementing custom screens"""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
    
    def screen(self, universe, market_data, fundamental_data, **kwargs):
        """
        Override this method to implement screening logic
        
        Args:
            universe: List of symbols to screen
            market_data: Historical price/volume data
            fundamental_data: Fundamental metrics
            **kwargs: Additional parameters
            
        Returns:
            list: Filtered symbols with scores
        """
        raise NotImplementedError

class MomentumQualityScreen(CustomScreenBase):
    def __init__(self):
        super().__init__(
            "Momentum Quality Screen",
            "Combines price momentum with fundamental quality metrics"
        )
    
    def screen(self, universe, market_data, fundamental_data, 
               momentum_period=90, quality_threshold=0.7):
        results = []
        
        for symbol in universe:
            # Calculate momentum score
            prices = market_data[symbol]['close']
            momentum_score = (prices[-1] - prices[-momentum_period]) / prices[-momentum_period]
            
            # Calculate quality score
            fundamentals = fundamental_data[symbol]
            quality_score = (
                (fundamentals['roe'] * 0.3) +
                (fundamentals['roic'] * 0.3) +
                ((1 - fundamentals['debt_to_equity']) * 0.2) +
                (fundamentals['profit_margin'] * 0.2)
            )
            
            # Combined score
            if momentum_score > 0.1 and quality_score > quality_threshold:
                combined_score = (momentum_score * 0.6) + (quality_score * 0.4)
                results.append({
                    'symbol': symbol,
                    'momentum_score': momentum_score,
                    'quality_score': quality_score,
                    'combined_score': combined_score
                })
        
        return sorted(results, key=lambda x: x['combined_score'], reverse=True)
```

---

## 📡 Real-time Data & WebSocket APIs

### WebSocket Connections
```javascript
// WebSocket connection for real-time data
const ws = new WebSocket('ws://localhost:8000/ws/market-data/AAPL/');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Real-time data:', data);
};

// Subscribe to multiple symbols
const portfolioWs = new WebSocket('ws://localhost:8000/ws/portfolio/123/');
```

### Streaming Endpoints
```http
GET /api/v1/streaming/market-data/{symbol}/
GET /api/v1/streaming/portfolio/{id}/
GET /api/v1/streaming/watchlist/{id}/
```

### Data Synchronization

#### Manual Data Sync
```http
POST /api/v1/sync/manual/
```

**Sync Request:**
```json
{
  "symbols": ["AAPL", "GOOGL", "MSFT"],
  "data_source": "yfinance",
  "period": "1d",
  "interval": "1m",
  "update_fundamentals": true
}
```

#### Scheduled Sync Management
```http
GET    /api/v1/sync/schedules/
POST   /api/v1/sync/schedules/
PUT    /api/v1/sync/schedules/{id}/
DELETE /api/v1/sync/schedules/{id}/
```

**Create Sync Schedule:**
```json
{
  "name": "Daily US Market Close",
  "symbols": ["AAPL", "GOOGL", "MSFT", "AMZN"],
  "data_source": "yfinance",
  "frequency": "daily",
  "time": "21:30:00",
  "timezone": "UTC",
  "active": true,
  "notification_on_failure": true
}
```

---

## 📤 Data Export APIs

### Export Formats

#### CSV Export
```http
GET /api/v1/export/csv/{symbol}/?start=2024-01-01&end=2024-12-31
```

#### Pandas-Compatible JSON
```http
GET /api/v1/export/pandas/{symbol}/?format=records
```

**Pandas Response:**
```json
{
  "data": [
    {"Date": "2024-01-01", "Open": 150.0, "High": 152.0, "Low": 149.0, "Close": 151.0, "Volume": 1000000},
    {"Date": "2024-01-02", "Open": 151.0, "High": 153.0, "Low": 150.0, "Close": 152.0, "Volume": 1100000}
  ],
  "columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
  "index": [0, 1],
  "pandas_version": "2.0.0"
}
```

#### Excel Export
```http
GET /api/v1/export/excel/portfolio/{id}/
```

---

## 🔧 API Client Examples

### Python Client
```python
import requests
import pandas as pd
from datetime import datetime, timedelta

class QSuiteClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {'Authorization': f'Bearer {token}'}
    
    def get_market_data(self, symbol, period='1y', interval='1d'):
        """Get historical market data"""
        response = requests.get(
            f"{self.base_url}/market-data/{symbol}/history/",
            params={'period': period, 'interval': interval},
            headers=self.headers
        )
        return response.json()
    
    def get_technical_indicators(self, symbol, indicators=['rsi', 'macd']):
        """Get technical indicators"""
        response = requests.get(
            f"{self.base_url}/technical/momentum/{symbol}/",
            params={'indicators': ','.join(indicators)},
            headers=self.headers
        )
        return response.json()
    
    def run_backtest(self, strategy_config):
        """Run a backtest"""
        response = requests.post(
            f"{self.base_url}/backtests/",
            json=strategy_config,
            headers=self.headers
        )
        return response.json()
    
    def screen_stocks(self, criteria, screen_type='technical'):
        """Screen stocks based on criteria"""
        response = requests.post(
            f"{self.base_url}/screening/{screen_type}/",
            json={'criteria': criteria},
            headers=self.headers
        )
        return response.json()

# Usage example
client = QSuiteClient('http://localhost:8000/api/v1', 'your-jwt-token')

# Get Apple's data
aapl_data = client.get_market_data('AAPL', period='6mo', interval='1d')
df = pd.DataFrame(aapl_data['data'])

# Get technical indicators
indicators = client.get_technical_indicators('AAPL', ['rsi', 'macd', 'bollinger_bands'])

# Run a simple backtest
backtest_config = {
    "name": "Simple MA Crossover",
    "strategy_code": "ma_crossover",
    "parameters": {"fast_ma": 20, "slow_ma": 50},
    "universe": ["AAPL"],
    "start_date": "2023-01-01",
    "end_date": "2024-01-01",
    "initial_capital": 100000
}
backtest_result = client.run_backtest(backtest_config)
```

### Jupyter Notebook Integration
```python
# Jupyter notebook helper functions
import matplotlib.pyplot as plt
import seaborn as sns

def plot_price_with_indicators(symbol, period='1y'):
    """Plot price chart with technical indicators"""
    # Get data
    data = client.get_market_data(symbol, period=period)
    indicators = client.get_technical_indicators(symbol, ['sma', 'bollinger_bands', 'rsi'])
    
    # Create subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Price chart
    df = pd.DataFrame(data['data'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    ax1.plot(df['timestamp'], df['close'], label='Close Price')
    
    # Add Bollinger Bands if available
    if 'bollinger_bands' in indicators['indicators']:
        bb = indicators['indicators']['bollinger_bands']
        ax1.fill_between(df['timestamp'], bb['upper_band'], bb['lower_band'], alpha=0.2)
    
    ax1.set_title(f'{symbol} Price Chart')
    ax1.legend()
    
    # RSI
    if 'rsi' in indicators['indicators']:
        rsi_data = indicators['indicators']['rsi']['history']
        rsi_df = pd.DataFrame(rsi_data)
        rsi_df['date'] = pd.to_datetime(rsi_df['date'])
        ax2.plot(rsi_df['date'], rsi_df['value'], label='RSI')
        ax2.axhline(y=70, color='r', linestyle='--', alpha=0.7)
        ax2.axhline(y=30, color='g', linestyle='--', alpha=0.7)
        ax2.set_title('RSI')
        ax2.set_ylim(0, 100)
    
    plt.tight_layout()
    plt.show()

# Usage in notebook
plot_price_with_indicators('AAPL', '6mo')
```

---

## 🚀 Getting Started Guide

### 1. Authentication Setup
```python
# Get your API token
import requests

response = requests.post('http://localhost:8000/api/auth/login/', {
    'username': 'your_username',
    'password': 'your_password'
})
token = response.json()['access']
```

### 2. Basic Data Retrieval
```python
# Fetch Apple's recent data
aapl_data = client.get_market_data('AAPL', period='1mo', interval='1d')

# Get real-time quote
quote = requests.get(
    'http://localhost:8000/api/v1/market-data/AAPL/quote/',
    headers={'Authorization': f'Bearer {token}'}
).json()
```

### 3. Technical Analysis
```python
# Calculate RSI and MACD
indicators = client.get_technical_indicators('AAPL', ['rsi', 'macd'])
print(f"Current RSI: {indicators['indicators']['rsi']['current_value']}")
```

### 4. Portfolio Analysis
```python
# Create and analyze a portfolio
portfolio_config = {
    "name": "Tech Portfolio",
    "positions": [
        {"symbol": "AAPL", "quantity": 100, "avg_cost": 150.00},
        {"symbol": "GOOGL", "quantity": 50, "avg_cost": 2800.00}
    ]
}

portfolio = requests.post(
    'http://localhost:8000/api/v1/portfolios/',
    json=portfolio_config,
    headers={'Authorization': f'Bearer {token}'}
).json()

# Get analytics
analytics = requests.get(
    f'http://localhost:8000/api/v1/portfolios/{portfolio["id"]}/analytics/',
    headers={'Authorization': f'Bearer {token}'}
).json()
```

### 5. Stock Screening
```python
# Screen for oversold stocks
screen_criteria = [
    {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
    {"indicator": "volume_ratio", "period": 10, "operator": ">", "value": 1.5}
]

results = client.screen_stocks(screen_criteria, 'technical')
```

---

## 🔐 Security & Rate Limits

### API Security
- **JWT Authentication**: Required for all endpoints
- **Rate Limiting**: 1000 requests/hour for standard users
- **IP Whitelisting**: Available for enterprise users
- **API Key Management**: Secondary authentication method

### Error Handling
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 3600 seconds.",
    "details": {
      "limit": 1000,
      "remaining": 0,
      "reset_time": "2025-06-09T17:00:00Z"
    }
  }
}
```

### Rate Limit Headers
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1623267600
```

---

## 📚 Advanced Usage Patterns

### Batch Operations
```python
# Batch fetch multiple symbols
symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']
batch_data = {}

for symbol in symbols:
    batch_data[symbol] = client.get_market_data(symbol, period='1y')
```

### Strategy Research Workflow
```python
def research_momentum_strategy():
    """Complete research workflow for momentum strategy"""
    
    # 1. Screen for momentum stocks
    momentum_criteria = [
        {"indicator": "price_change", "period": 90, "operator": ">", "value": 0.20},
        {"indicator": "rsi", "period": 14, "operator": ">", "value": 50},
        {"indicator": "volume_ratio", "period": 20, "operator": ">", "value": 1.2}
    ]
    
    candidates = client.screen_stocks(momentum_criteria, 'technical')
    top_stocks = [stock['symbol'] for stock in candidates['results'][:20]]
    
    # 2. Analyze correlations
    correlation_matrix = requests.post(
        f"{client.base_url}/analytics/correlation-matrix/",
        json={"symbols": top_stocks, "period": "1y"},
        headers=client.headers
    ).json()
    
    # 3. Backtest strategy
    backtest_config = {
        "name": "Momentum Strategy Research",
        "strategy_code": "momentum_strategy",
        "parameters": {"lookback": 90, "holding_period": 30},
        "universe": top_stocks,
        "start_date": "2020-01-01",
        "end_date": "2024-01-01",
        "initial_capital": 100000
    }
    
    backtest_result = client.run_backtest(backtest_config)
    
    return {
        "candidates": candidates,
        "correlations": correlation_matrix,
        "backtest": backtest_result
    }
```

---

## 🆘 Support & Documentation

### API Status
```http
GET /api/v1/status/
```

### Health Check
```http
GET /api/v1/health/
```

### API Schema
```http
GET /api/v1/schema/
```

### Rate Limit Status
```http
GET /api/v1/user/rate-limits/
```

This comprehensive API documentation provides quantitative researchers with professional-grade tools for market analysis, portfolio management, backtesting, and real-time data access, while maintaining the flexibility to extend and customize functionality for specific research needs.
