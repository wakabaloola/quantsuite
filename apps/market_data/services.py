# apps/market_data/services.py
"""Data ingestion services for yfinance and Alpha Vantage"""

import yfinance as yf
import requests
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from .models import (
    DataSource, Exchange, Ticker, MarketData, 
    FundamentalData, DataIngestionLog, Sector, Industry
)
import logging

logger = logging.getLogger(__name__)


class YFinanceService:
    """Service for fetching data from Yahoo Finance via yfinance"""
    
    def __init__(self):
        self.data_source, _ = DataSource.objects.get_or_create(
            code='YFINANCE',
            defaults={
                'name': 'Yahoo Finance',
                'url': 'https://finance.yahoo.com',
                'requires_api_key': False,
                'rate_limit_per_minute': 2000,
                'supported_markets': ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'IT', 'ES', 'NL', 'CH', 'JP', 'HK', 'IN', 'BR', 'MX'],
                'supported_timeframes': ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
            }
        )
    
    def search_ticker(self, query: str, country: str = None) -> List[Dict]:
        """Search for tickers using yfinance"""
        try:
            # yfinance doesn't have a direct search API, but we can try common patterns
            results = []
            
            # Try the query as-is
            ticker = yf.Ticker(query)
            info = ticker.info
            
            if info and 'symbol' in info:
                results.append({
                    'symbol': info.get('symbol', query),
                    'name': info.get('longName', ''),
                    'exchange': info.get('exchange', ''),
                    'currency': info.get('currency', 'USD'),
                    'country': info.get('country', ''),
                    'sector': info.get('sector', ''),
                    'industry': info.get('industry', '')
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching ticker {query}: {e}")
            return []
    
    def get_ticker_info(self, symbol: str) -> Optional[Dict]:
        """Get comprehensive ticker information"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or 'symbol' not in info:
                return None
            
            return {
                'symbol': info.get('symbol', symbol),
                'name': info.get('longName', ''),
                'description': info.get('longBusinessSummary', ''),
                'exchange': info.get('exchange', ''),
                'currency': info.get('currency', 'USD'),
                'country': info.get('country', ''),
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'market_cap': info.get('marketCap'),
                'shares_outstanding': info.get('sharesOutstanding'),
                'website': info.get('website', ''),
                'employees': info.get('fullTimeEmployees'),
            }
            
        except Exception as e:
            logger.error(f"Error getting ticker info for {symbol}: {e}")
            return None
    
    def fetch_market_data(self, symbol: str, period: str = '1y', 
                         interval: str = '1d') -> List[Dict]:
        """Fetch historical market data"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Get historical data
            hist = ticker.history(period=period, interval=interval)
            
            if hist.empty:
                logger.warning(f"No data returned for {symbol}")
                return []
            
            data = []
            for timestamp, row in hist.iterrows():
                # Convert pandas timestamp to datetime
                dt = timestamp.to_pydatetime()
                if dt.tzinfo is None:
                    dt = timezone.make_aware(dt)
                
                data.append({
                    'timestamp': dt,
                    'timeframe': interval,
                    'open': Decimal(str(row['Open'])) if not pd.isna(row['Open']) else None,
                    'high': Decimal(str(row['High'])) if not pd.isna(row['High']) else None,
                    'low': Decimal(str(row['Low'])) if not pd.isna(row['Low']) else None,
                    'close': Decimal(str(row['Close'])) if not pd.isna(row['Close']) else None,
                    'volume': Decimal(str(row['Volume'])) if not pd.isna(row['Volume']) else None,
                })
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            return []
    
    def get_real_time_quote(self, symbol: str) -> Optional[Dict]:
        """Get real-time quote data"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info:
                return None
            
            return {
                'symbol': symbol,
                'price': info.get('currentPrice') or info.get('regularMarketPrice'),
                'change': info.get('regularMarketChange'),
                'change_percent': info.get('regularMarketChangePercent'),
                'volume': info.get('regularMarketVolume'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'timestamp': timezone.now(),
                'market_status': 'open' if info.get('marketState') == 'REGULAR' else 'closed',
                'bid': info.get('bid'),
                'ask': info.get('ask'),
                'bid_size': info.get('bidSize'),
                'ask_size': info.get('askSize'),
            }
            
        except Exception as e:
            logger.error(f"Error getting real-time quote for {symbol}: {e}")
            return None


class AlphaVantageService:
    """Service for fetching data from Alpha Vantage"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', None)
        self.base_url = 'https://www.alphavantage.co/query'
        self.data_source, _ = DataSource.objects.get_or_create(
            code='ALPHA_VANTAGE',
            defaults={
                'name': 'Alpha Vantage',
                'url': 'https://www.alphavantage.co',
                'api_endpoint': self.base_url,
                'requires_api_key': True,
                'rate_limit_per_minute': 5,  # Free tier limit
                'supported_markets': ['US'],
                'supported_timeframes': ['1min', '5min', '15min', '30min', '60min', 'daily', 'weekly', 'monthly']
            }
        )
    
    def _make_request(self, params: Dict) -> Optional[Dict]:
        """Make API request to Alpha Vantage"""
        if not self.api_key:
            logger.error("Alpha Vantage API key not configured")
            return None
        
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Alpha Vantage API request failed: {e}")
            return None
    
    def fetch_daily_data(self, symbol: str, outputsize: str = 'compact') -> List[Dict]:
        """Fetch daily time series data"""
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': symbol,
            'outputsize': outputsize
        }
        
        response = self._make_request(params)
        if not response or 'Time Series (Daily)' not in response:
            logger.error(f"Invalid response for {symbol}: {response}")
            return []
        
        data = []
        time_series = response['Time Series (Daily)']
        
        for date_str, values in time_series.items():
            try:
                # Parse date
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                dt = timezone.make_aware(dt)
                
                data.append({
                    'timestamp': dt,
                    'timeframe': '1d',
                    'open': Decimal(values['1. open']),
                    'high': Decimal(values['2. high']),
                    'low': Decimal(values['3. low']),
                    'close': Decimal(values['4. close']),
                    'volume': Decimal(values['5. volume']),
                })
                
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing data for {symbol} on {date_str}: {e}")
                continue
        
        return data
    
    def fetch_intraday_data(self, symbol: str, interval: str = '5min') -> List[Dict]:
        """Fetch intraday time series data"""
        params = {
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': symbol,
            'interval': interval,
            'outputsize': 'full'
        }
        
        response = self._make_request(params)
        time_series_key = f'Time Series ({interval})'
        
        if not response or time_series_key not in response:
            logger.error(f"Invalid intraday response for {symbol}: {response}")
            return []
        
        data = []
        time_series = response[time_series_key]
        
        for datetime_str, values in time_series.items():
            try:
                # Parse datetime
                dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                dt = timezone.make_aware(dt)
                
                data.append({
                    'timestamp': dt,
                    'timeframe': interval,
                    'open': Decimal(values['1. open']),
                    'high': Decimal(values['2. high']),
                    'low': Decimal(values['3. low']),
                    'close': Decimal(values['4. close']),
                    'volume': Decimal(values['5. volume']),
                })
                
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing intraday data for {symbol}: {e}")
                continue
        
        return data
    
    def fetch_company_overview(self, symbol: str) -> Optional[Dict]:
        """Fetch company fundamental data"""
        params = {
            'function': 'OVERVIEW',
            'symbol': symbol
        }
        
        response = self._make_request(params)
        if not response or 'Symbol' not in response:
            return None
        
        try:
            return {
                'symbol': response.get('Symbol'),
                'name': response.get('Name'),
                'description': response.get('Description'),
                'exchange': response.get('Exchange'),
                'currency': response.get('Currency'),
                'country': response.get('Country'),
                'sector': response.get('Sector'),
                'industry': response.get('Industry'),
                'market_cap': int(response.get('MarketCapitalization', 0)) if response.get('MarketCapitalization') != 'None' else None,
                'pe_ratio': float(response.get('PERatio', 0)) if response.get('PERatio') != 'None' else None,
                'peg_ratio': float(response.get('PEGRatio', 0)) if response.get('PEGRatio') != 'None' else None,
                'pb_ratio': float(response.get('PriceToBookRatio', 0)) if response.get('PriceToBookRatio') != 'None' else None,
                'dividend_yield': float(response.get('DividendYield', 0)) if response.get('DividendYield') != 'None' else None,
                'eps': float(response.get('EPS', 0)) if response.get('EPS') != 'None' else None,
                'revenue_ttm': int(response.get('RevenueTTM', 0)) if response.get('RevenueTTM') != 'None' else None,
                'profit_margin': float(response.get('ProfitMargin', 0)) if response.get('ProfitMargin') != 'None' else None,
                'beta': float(response.get('Beta', 0)) if response.get('Beta') != 'None' else None,
                'week_52_high': float(response.get('52WeekHigh', 0)) if response.get('52WeekHigh') != 'None' else None,
                'week_52_low': float(response.get('52WeekLow', 0)) if response.get('52WeekLow') != 'None' else None,
            }
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing company overview for {symbol}: {e}")
            return None


class DataIngestionService:
    """Main service for coordinating data ingestion"""
    
    def __init__(self):
        self.yfinance = YFinanceService()
        self.alpha_vantage = AlphaVantageService()
    
    def create_or_update_ticker(self, symbol: str, data_source: str = 'yfinance') -> Optional[Ticker]:
        """Create or update ticker with comprehensive information"""
        try:
            with transaction.atomic():
                # Get ticker info
                if data_source == 'yfinance':
                    info = self.yfinance.get_ticker_info(symbol)
                    source_obj = self.yfinance.data_source
                elif data_source == 'alpha_vantage':
                    info = self.alpha_vantage.fetch_company_overview(symbol)
                    source_obj = self.alpha_vantage.data_source
                else:
                    raise ValueError(f"Unknown data source: {data_source}")
                
                if not info:
                    logger.error(f"Could not get info for symbol {symbol}")
                    return None
                
                # Get or create exchange
                exchange_name = info.get('exchange', 'Unknown')
                exchange, _ = Exchange.objects.get_or_create(
                    code=exchange_name,
                    defaults={
                        'name': exchange_name,
                        'country': info.get('country', 'US')[:2],
                        'currency': info.get('currency', 'USD'),
                    }
                )
                
                # Get or create sector and industry
                sector = None
                industry = None
                if info.get('sector'):
                    sector, _ = Sector.objects.get_or_create(
                        name=info['sector'],
                        defaults={'code': info['sector'][:20].upper()}
                    )
                    
                    if info.get('industry'):
                        industry, _ = Industry.objects.get_or_create(
                            name=info['industry'],
                            sector=sector
                        )
                
                # Create or update ticker
                ticker, created = Ticker.objects.update_or_create(
                    symbol=symbol,
                    exchange=exchange,
                    defaults={
                        'name': info.get('name', symbol),
                        'description': info.get('description', ''),
                        'currency': info.get('currency', 'USD'),
                        'country': info.get('country', 'US')[:2],
                        'data_source': source_obj,
                        'sector': sector,
                        'industry': industry,
                        'market_cap': info.get('market_cap'),
                        'shares_outstanding': info.get('shares_outstanding'),
                        'yfinance_symbol': symbol if data_source == 'yfinance' else '',
                        'alpha_vantage_symbol': symbol if data_source == 'alpha_vantage' else '',
                        'last_updated': timezone.now(),
                    }
                )
                
                logger.info(f"{'Created' if created else 'Updated'} ticker {symbol}")
                return ticker
                
        except Exception as e:
            logger.error(f"Error creating/updating ticker {symbol}: {e}")
            return None
    
    def ingest_market_data(self, symbols: List[str], data_source: str = 'yfinance',
                          period: str = '1y', interval: str = '1d') -> DataIngestionLog:
        """Ingest market data for multiple symbols"""
        # Create ingestion log
        source_obj = (self.yfinance.data_source if data_source == 'yfinance' 
                     else self.alpha_vantage.data_source)
        
        log = DataIngestionLog.objects.create(
            data_source=source_obj,
            symbols_requested=symbols,
            start_time=timezone.now(),
            status='RUNNING'
        )
        
        successful_symbols = []
        failed_symbols = []
        total_records = 0
        
        try:
            for symbol in symbols:
                try:
                    logger.info(f"Processing {symbol}...")
                    
                    # Create/update ticker
                    ticker = self.create_or_update_ticker(symbol, data_source)
                    if not ticker:
                        failed_symbols.append(symbol)
                        continue
                    
                    # Fetch market data
                    if data_source == 'yfinance':
                        market_data = self.yfinance.fetch_market_data(symbol, period, interval)
                    elif data_source == 'alpha_vantage':
                        if interval == '1d':
                            market_data = self.alpha_vantage.fetch_daily_data(symbol)
                        else:
                            market_data = self.alpha_vantage.fetch_intraday_data(symbol, interval)
                    else:
                        raise ValueError(f"Unknown data source: {data_source}")
                    
                    if not market_data:
                        failed_symbols.append(symbol)
                        continue
                    
                    # Save market data
                    records_created = 0
                    with transaction.atomic():
                        for data_point in market_data:
                            if not all([data_point.get('open'), data_point.get('high'), 
                                      data_point.get('low'), data_point.get('close')]):
                                continue
                            
                            market_data_obj, created = MarketData.objects.update_or_create(
                                ticker=ticker,
                                timestamp=data_point['timestamp'],
                                timeframe=data_point['timeframe'],
                                data_source=source_obj,
                                defaults={
                                    'open': data_point['open'],
                                    'high': data_point['high'],
                                    'low': data_point['low'],
                                    'close': data_point['close'],
                                    'volume': data_point.get('volume', 0),
                                    'adjusted_close': data_point.get('adjusted_close'),
                                }
                            )
                            if created:
                                records_created += 1
                    
                    successful_symbols.append(symbol)
                    total_records += records_created
                    logger.info(f"Saved {records_created} records for {symbol}")
                    
                    # Rate limiting for Alpha Vantage
                    if data_source == 'alpha_vantage':
                        time.sleep(12)  # 5 calls per minute limit
                
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                    failed_symbols.append(symbol)
                    continue
            
            # Update log
            end_time = timezone.now()
            execution_time = (end_time - log.start_time).total_seconds()
            
            log.end_time = end_time
            log.symbols_successful = successful_symbols
            log.symbols_failed = failed_symbols
            log.records_inserted = total_records
            log.execution_time_seconds = Decimal(str(execution_time))
            log.status = 'COMPLETED' if not failed_symbols else 'PARTIAL'
            log.save()
            
            logger.info(f"Ingestion completed: {len(successful_symbols)} successful, {len(failed_symbols)} failed, {total_records} records")
            
        except Exception as e:
            log.status = 'FAILED'
            log.error_message = str(e)
            log.end_time = timezone.now()
            log.save()
            logger.error(f"Ingestion failed: {e}")
        
        return log


# Import pandas here to avoid issues if not installed
try:
    import pandas as pd
except ImportError:
    pd = None
    logger.warning("pandas not installed - some functionality may be limited")
