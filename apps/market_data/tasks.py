# apps/market_data/tasks.py
"""
Celery tasks for background processing of market data and analytics

These tasks handle:
- Automated data ingestion from external sources
- Technical indicator calculations
- Portfolio analytics updates
- Data cleanup and maintenance
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal
import time

from .models import (
    Ticker, MarketData, DataIngestionLog, TechnicalIndicator,
    DataSource, Portfolio, Position
)
from .services import DataIngestionService, YFinanceService, AlphaVantageService
from .technical_analysis import TechnicalAnalysisCalculator

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_market_data_async(self, symbols, data_source='yfinance', period='1y', 
                           interval='1d', update_fundamentals=False):
    """
    Asynchronous market data ingestion task
    
    Args:
        symbols: List of symbols to fetch
        data_source: 'yfinance' or 'alpha_vantage'
        period: Data period to fetch
        interval: Data interval
        update_fundamentals: Whether to fetch fundamental data
    """
    try:
        logger.info(f"Starting data ingestion for {len(symbols)} symbols from {data_source}")
        
        ingestion_service = DataIngestionService()
        log = ingestion_service.ingest_market_data(
            symbols=symbols,
            data_source=data_source,
            period=period,
            interval=interval
        )
        
        logger.info(f"Ingestion completed: {log.status}, {log.records_inserted} records")
        
        # Trigger technical indicator calculations for successful symbols
        if log.symbols_successful:
            calculate_technical_indicators_batch.delay(
                log.symbols_successful, 
                timeframe=interval
            )
        
        return {
            'task_id': self.request.id,
            'status': log.status,
            'symbols_processed': len(log.symbols_successful),
            'records_inserted': log.records_inserted,
            'execution_time': float(log.execution_time_seconds) if log.execution_time_seconds else 0
        }
        
    except Exception as exc:
        logger.error(f"Data ingestion failed: {exc}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** self.request.retries, exc=exc)
        
        return {
            'task_id': self.request.id,
            'status': 'FAILED',
            'error': str(exc)
        }


@shared_task
def calculate_technical_indicators_batch(symbols, timeframe='1d', 
                                       indicators=['rsi', 'macd', 'sma_20', 'sma_50', 'bollinger_bands']):
    """
    Calculate technical indicators for multiple symbols
    
    Args:
        symbols: List of symbols to process
        timeframe: Data timeframe to use
        indicators: List of indicators to calculate
    """
    results = []
    
    for symbol in symbols:
        try:
            result = calculate_technical_indicators_single.delay(symbol, timeframe, indicators)
            results.append({
                'symbol': symbol,
                'task_id': result.id,
                'status': 'submitted'
            })
        except Exception as e:
            logger.error(f"Error submitting indicator calculation for {symbol}: {e}")
            results.append({
                'symbol': symbol,
                'status': 'error',
                'error': str(e)
            })
    
    return {
        'submitted_tasks': len(results),
        'symbols_processed': symbols,
        'results': results
    }


@shared_task(bind=True, max_retries=2)
def calculate_technical_indicators_single(self, symbol, timeframe='1d', 
                                        indicators=['rsi', 'macd', 'sma_20', 'sma_50']):
    """
    Calculate technical indicators for a single symbol
    
    Args:
        symbol: Symbol to process
        timeframe: Data timeframe
        indicators: List of indicators to calculate
    """
    try:
        logger.info(f"Calculating technical indicators for {symbol}")
        
        calculator = TechnicalAnalysisCalculator(symbol)
        
        # Calculate all requested indicators
        results = calculator.calculate_indicators(indicators, timeframe)
        
        # Save to database for caching
        calculator.save_indicators_to_db(results)
        
        logger.info(f"Technical indicators calculated for {symbol}: {list(results['indicators'].keys())}")
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'indicators_calculated': list(results['indicators'].keys()),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Technical indicator calculation failed for {symbol}: {exc}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30, exc=exc)
        
        return {
            'symbol': symbol,
            'status': 'FAILED',
            'error': str(exc)
        }


@shared_task
def update_portfolio_analytics(portfolio_id, calculate_risk_metrics=True):
    """
    Update portfolio analytics and performance metrics
    
    Args:
        portfolio_id: Portfolio ID to update
        calculate_risk_metrics: Whether to calculate detailed risk metrics
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
        logger.info(f"Updating analytics for portfolio {portfolio.name}")
        
        # Get all positions
        positions = Position.objects.filter(portfolio=portfolio)
        
        if not positions.exists():
            return {
                'portfolio_id': portfolio_id,
                'status': 'NO_POSITIONS',
                'message': 'Portfolio has no positions'
            }
        
        # Update current prices for all positions
        updated_positions = 0
        for position in positions:
            try:
                # Get latest market data
                latest_data = MarketData.objects.filter(
                    ticker=position.ticker
                ).latest('timestamp')
                
                position.current_price = latest_data.close
                position.save(update_fields=['current_price', 'last_updated'])
                updated_positions += 1
                
            except MarketData.DoesNotExist:
                logger.warning(f"No market data for {position.ticker.symbol}")
                continue
        
        # Calculate portfolio metrics
        total_value = Decimal('0')
        total_cost = Decimal('0')
        
        for position in positions:
            if position.current_price:
                position_value = position.quantity * position.current_price
                total_value += position_value
                total_cost += position.quantity * position.avg_cost
        
        # Update portfolio
        portfolio.current_cash = portfolio.initial_cash - total_cost
        portfolio.save(update_fields=['current_cash'])
        
        # Calculate performance metrics
        total_return = float((total_value - total_cost) / total_cost) if total_cost > 0 else 0
        
        analytics = {
            'total_value': float(total_value),
            'total_cost': float(total_cost),
            'unrealized_pnl': float(total_value - total_cost),
            'total_return_percent': total_return * 100,
            'positions_count': positions.count(),
            'updated_positions': updated_positions
        }
        
        if calculate_risk_metrics:
            # Calculate additional risk metrics (simplified)
            analytics['risk_metrics'] = calculate_portfolio_risk_metrics(portfolio_id)
        
        logger.info(f"Portfolio analytics updated for {portfolio.name}")
        
        return {
            'portfolio_id': portfolio_id,
            'status': 'SUCCESS',
            'analytics': analytics,
            'timestamp': timezone.now().isoformat()
        }
        
    except Portfolio.DoesNotExist:
        return {
            'portfolio_id': portfolio_id,
            'status': 'NOT_FOUND',
            'error': 'Portfolio not found'
        }
    except Exception as e:
        logger.error(f"Portfolio analytics update failed for {portfolio_id}: {e}")
        return {
            'portfolio_id': portfolio_id,
            'status': 'ERROR',
            'error': str(e)
        }


def calculate_portfolio_risk_metrics(portfolio_id):
    """Calculate portfolio risk metrics (simplified implementation)"""
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
        positions = Position.objects.filter(portfolio=portfolio)
        
        if not positions.exists():
            return {}
        
        # Get historical returns for portfolio positions
        symbols = [pos.ticker.symbol for pos in positions]
        
        # This would implement proper portfolio risk calculations
        # For now, return basic metrics
        return {
            'portfolio_beta': 1.0,  # Would calculate against benchmark
            'sharpe_ratio': 0.0,    # Would calculate using returns
            'max_drawdown': 0.0,    # Would calculate from historical performance
            'volatility': 0.0,      # Would calculate from returns
            'var_95': 0.0,          # Value at Risk
        }
        
    except Exception as e:
        logger.error(f"Risk metrics calculation failed: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_old_data():
    """
    Cleanup old data to maintain database performance
    
    This task removes:
    - Old technical indicator calculations (> 1 year)
    - Old ingestion logs (> 6 months)
    - Orphaned data
    """
    logger.info("Starting data cleanup task")
    
    cleanup_results = {}
    
    # Cleanup old technical indicators
    try:
        old_indicators_date = timezone.now() - timedelta(days=365)
        deleted_indicators = TechnicalIndicator.objects.filter(
            timestamp__lt=old_indicators_date
        ).delete()
        cleanup_results['technical_indicators'] = deleted_indicators[0]
        logger.info(f"Deleted {deleted_indicators[0]} old technical indicators")
    except Exception as e:
        logger.error(f"Error cleaning up technical indicators: {e}")
        cleanup_results['technical_indicators'] = f'Error: {e}'
    
    # Cleanup old ingestion logs
    try:
        old_logs_date = timezone.now() - timedelta(days=180)
        deleted_logs = DataIngestionLog.objects.filter(
            start_time__lt=old_logs_date
        ).delete()
        cleanup_results['ingestion_logs'] = deleted_logs[0]
        logger.info(f"Deleted {deleted_logs[0]} old ingestion logs")
    except Exception as e:
        logger.error(f"Error cleaning up ingestion logs: {e}")
        cleanup_results['ingestion_logs'] = f'Error: {e}'
    
    # Cleanup inactive tickers with no market data
    try:
        inactive_tickers = Ticker.objects.filter(
            is_active=False,
            market_data__isnull=True
        )
        deleted_tickers = inactive_tickers.delete()
        cleanup_results['inactive_tickers'] = deleted_tickers[0]
        logger.info(f"Deleted {deleted_tickers[0]} inactive tickers with no data")
    except Exception as e:
        logger.error(f"Error cleaning up inactive tickers: {e}")
        cleanup_results['inactive_tickers'] = f'Error: {e}'
    
    return {
        'status': 'COMPLETED',
        'timestamp': timezone.now().isoformat(),
        'cleanup_results': cleanup_results
    }


@shared_task
def refresh_real_time_quotes(symbols):
    """
    Refresh real-time quotes for specified symbols
    
    Args:
        symbols: List of symbols to refresh
    """
    logger.info(f"Refreshing real-time quotes for {len(symbols)} symbols")
    
    yfinance_service = YFinanceService()
    results = []
    
    for symbol in symbols:
        try:
            quote_data = yfinance_service.get_real_time_quote(symbol)
            
            if quote_data:
                results.append({
                    'symbol': symbol,
                    'price': quote_data['price'],
                    'change': quote_data.get('change'),
                    'timestamp': quote_data['timestamp'].isoformat(),
                    'status': 'SUCCESS'
                })
            else:
                results.append({
                    'symbol': symbol,
                    'status': 'NO_DATA'
                })
                
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            results.append({
                'symbol': symbol,
                'status': 'ERROR',
                'error': str(e)
            })
    
    return {
        'symbols_processed': len(symbols),
        'successful_quotes': len([r for r in results if r['status'] == 'SUCCESS']),
        'results': results,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def calculate_correlation_matrix(symbols, period_days=365):
    """
    Calculate correlation matrix for a set of symbols
    
    Args:
        symbols: List of symbols
        period_days: Number of days of data to use
    """
    try:
        import pandas as pd
        import numpy as np
        
        logger.info(f"Calculating correlation matrix for {len(symbols)} symbols")
        
        # Get market data for all symbols
        start_date = timezone.now() - timedelta(days=period_days)
        
        price_data = {}
        for symbol in symbols:
            try:
                ticker = Ticker.objects.get(symbol=symbol, is_active=True)
                market_data = MarketData.objects.filter(
                    ticker=ticker,
                    timestamp__gte=start_date,
                    timeframe='1d'
                ).order_by('timestamp').values('timestamp', 'close')
                
                if market_data:
                    df = pd.DataFrame(market_data)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    price_data[symbol] = df['close']
                
            except Ticker.DoesNotExist:
                logger.warning(f"Ticker {symbol} not found")
                continue
        
        if len(price_data) < 2:
            return {
                'status': 'INSUFFICIENT_DATA',
                'message': 'Need at least 2 symbols with data'
            }
        
        # Create aligned DataFrame
        combined_df = pd.DataFrame(price_data)
        combined_df = combined_df.dropna()
        
        if len(combined_df) < 30:
            return {
                'status': 'INSUFFICIENT_DATA',
                'message': 'Need at least 30 days of overlapping data'
            }
        
        # Calculate correlation matrix
        correlation_matrix = combined_df.corr()
        
        # Convert to dictionary
        correlation_dict = {}
        for symbol1 in correlation_matrix.index:
            correlation_dict[symbol1] = {}
            for symbol2 in correlation_matrix.columns:
                correlation_dict[symbol1][symbol2] = float(correlation_matrix.loc[symbol1, symbol2])
        
        logger.info(f"Correlation matrix calculated successfully")
        
        return {
            'status': 'SUCCESS',
            'correlation_matrix': correlation_dict,
            'data_points': len(combined_df),
            'symbols': list(correlation_matrix.index),
            'period_days': period_days,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Correlation matrix calculation failed: {e}")
        return {
            'status': 'ERROR',
            'error': str(e)
        }


@shared_task
def run_daily_market_analysis():
    """
    Daily market analysis task
    
    This runs comprehensive analysis across all active tickers
    """
    logger.info("Starting daily market analysis")
    
    # Get all active tickers
    active_tickers = Ticker.objects.filter(is_active=True)
    symbols = [ticker.symbol for ticker in active_tickers]
    
    if not symbols:
        return {
            'status': 'NO_SYMBOLS',
            'message': 'No active tickers found'
        }
    
    results = {
        'total_symbols': len(symbols),
        'tasks_submitted': 0,
        'timestamp': timezone.now().isoformat()
    }
    
    # Submit technical indicator calculations for all symbols
    batch_size = 50  # Process in batches to avoid overwhelming the system
    
    for i in range(0, len(symbols), batch_size):
        batch_symbols = symbols[i:i + batch_size]
        
        try:
            calculate_technical_indicators_batch.delay(
                batch_symbols,
                timeframe='1d',
                indicators=['rsi', 'macd', 'sma_20', 'sma_50', 'bollinger_bands', 'atr']
            )
            results['tasks_submitted'] += 1
        except Exception as e:
            logger.error(f"Error submitting batch {i//batch_size + 1}: {e}")
    
    # Update portfolio analytics for all portfolios
    portfolios = Portfolio.objects.filter(is_active=True)
    for portfolio in portfolios:
        try:
            update_portfolio_analytics.delay(portfolio.id)
        except Exception as e:
            logger.error(f"Error submitting portfolio analytics for {portfolio.id}: {e}")
    
    results['portfolios_submitted'] = portfolios.count()
    
    logger.info(f"Daily market analysis completed: {results['tasks_submitted']} batches submitted")
    
    return results


@shared_task
def monitor_system_health():
    """
    Monitor system health and performance
    
    This task checks:
    - Database performance
    - Cache performance
    - External service availability
    - Data freshness
    """
    logger.info("Starting system health monitoring")
    
    health_status = {
        'timestamp': timezone.now().isoformat(),
        'overall_status': 'healthy',
        'checks': {}
    }
    
    # Check database performance
    try:
        start_time = time.time()
        ticker_count = Ticker.objects.count()
        market_data_count = MarketData.objects.count()
        db_response_time = (time.time() - start_time) * 1000
        
        health_status['checks']['database'] = {
            'status': 'healthy',
            'response_time_ms': round(db_response_time, 2),
            'ticker_count': ticker_count,
            'market_data_count': market_data_count
        }
        
    except Exception as e:
        health_status['checks']['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        health_status['overall_status'] = 'degraded'
    
    # Check data freshness
    try:
        recent_data_count = MarketData.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=1)
        ).count()
        
        stale_data_count = MarketData.objects.filter(
            timestamp__lt=timezone.now() - timedelta(days=7)
        ).count()
        
        health_status['checks']['data_freshness'] = {
            'status': 'healthy' if recent_data_count > 0 else 'warning',
            'recent_data_count': recent_data_count,
            'stale_data_count': stale_data_count
        }
        
    except Exception as e:
        health_status['checks']['data_freshness'] = {
            'status': 'error',
            'error': str(e)
        }
    
    # Check external services
    try:
        yfinance_service = YFinanceService()
        test_quote = yfinance_service.get_real_time_quote('AAPL')
        
        health_status['checks']['yfinance'] = {
            'status': 'healthy' if test_quote else 'degraded',
            'test_symbol': 'AAPL'
        }
        
    except Exception as e:
        health_status['checks']['yfinance'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        health_status['overall_status'] = 'degraded'
    
    return health_status


# Periodic task definitions (to be added to CELERY_BEAT_SCHEDULE)
CELERY_BEAT_SCHEDULE = {
    # Update technical indicators every hour during market hours
    'calculate-indicators-hourly': {
        'task': 'apps.market_data.tasks.run_daily_market_analysis',
        'schedule': 3600.0,  # Every hour
    },
    
    # Daily cleanup at midnight
    'cleanup-old-data': {
        'task': 'apps.market_data.tasks.cleanup_old_data',
        'schedule': 86400.0,  # Every day
    },
    
    # System health monitoring every 5 minutes
    'monitor-system-health': {
        'task': 'apps.market_data.tasks.monitor_system_health',
        'schedule': 300.0,  # Every 5 minutes
    },
    
    # Refresh real-time quotes every 30 seconds (for popular symbols)
    'refresh-popular-quotes': {
        'task': 'apps.market_data.tasks.refresh_real_time_quotes',
        'schedule': 30.0,
        'args': (['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA'],)
    },
}
