# apps/trading_analytics/portfolio_analytics.py
"""
Advanced Real-Time Portfolio Analytics Service
============================================

Provides comprehensive portfolio analytics including:
- Real-time P&L calculations across multiple timeframes
- Risk metrics (VaR, volatility, correlation, beta)
- Performance analytics (Sharpe, alpha, tracking error)
- Position-level analytics and concentration risk
- Sector allocation and diversification metrics
- Historical performance tracking with benchmarks
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from django.db import models
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


@dataclass
class PortfolioMetrics:
    """Comprehensive portfolio performance metrics"""
    # Basic metrics
    total_value: float
    cash_balance: float
    invested_value: float
    total_return_pct: float
    
    # P&L across timeframes
    unrealized_pnl: float
    realized_pnl: float
    intraday_pnl: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    ytd_pnl: float
    
    # Risk metrics
    portfolio_var_1day: float  # 1-day Value at Risk (95%)
    portfolio_volatility: float  # Annualized volatility
    portfolio_beta: float  # Beta vs benchmark
    max_drawdown: float
    
    # Performance metrics
    sharpe_ratio: Optional[float]
    alpha: Optional[float]  # Alpha vs benchmark
    tracking_error: Optional[float]
    information_ratio: Optional[float]
    
    # Position metrics
    position_count: int
    largest_position_pct: float
    top5_concentration: float
    sector_count: int
    
    # Timestamps
    last_updated: datetime
    calculation_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['last_updated'] = self.last_updated.isoformat()
        return data


@dataclass
class PositionAnalytics:
    """Advanced analytics for individual positions"""
    symbol: str
    quantity: float
    market_value: float
    weight_pct: float
    
    # P&L metrics
    unrealized_pnl: float
    unrealized_pnl_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    
    # Risk metrics
    position_var: float
    volatility: float
    beta: float
    correlation_to_portfolio: float
    
    # Performance
    return_1d: float
    return_7d: float
    return_30d: float
    return_ytd: float
    
    # Metadata
    sector: str
    market_cap_category: str
    last_price: float
    avg_cost: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SectorAllocation:
    """Portfolio sector allocation analytics"""
    sector: str
    market_value: float
    weight_pct: float
    position_count: int
    pnl_contribution: float
    avg_return: float
    volatility: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioAnalyticsService:
    """
    Advanced portfolio analytics engine for real-time calculations
    """
    
    def __init__(self):
        self.cache_ttl = 300  # 5 minutes
        self.risk_free_rate = getattr(settings, 'PORTFOLIO_SETTINGS', {}).get('RISK_FREE_RATE', 0.02)
        self.benchmark_symbol = getattr(settings, 'PORTFOLIO_SETTINGS', {}).get('BENCHMARK_SYMBOL', '^GSPC')
        
        # Performance tracking
        self.calculation_cache: Dict[int, Dict[str, Any]] = {}
        self.last_calculation_time: Dict[int, datetime] = {}
    
    async def calculate_comprehensive_analytics(self, user_id: int) -> Optional[PortfolioMetrics]:
        """Calculate comprehensive portfolio analytics"""
        start_time = timezone.now()
        
        try:
            # Get user's portfolio data
            portfolio_data = await self._get_portfolio_data(user_id)
            if not portfolio_data:
                return None
            
            # Calculate all metrics
            metrics = await self._calculate_all_metrics(user_id, portfolio_data)
            
            # Calculate processing time
            processing_time = (timezone.now() - start_time).total_seconds() * 1000
            metrics.calculation_time_ms = processing_time
            
            # Cache results
            await self._cache_analytics(user_id, metrics)
            
            logger.debug(f"Portfolio analytics calculated for user {user_id} in {processing_time:.2f}ms")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating portfolio analytics for user {user_id}: {e}")
            return None
    
    async def get_position_analytics(self, user_id: int) -> List[PositionAnalytics]:
        """Get detailed analytics for all positions"""
        try:
            positions_data = await self._get_positions_data(user_id)
            portfolio_value = await self._get_portfolio_total_value(user_id)
            
            position_analytics = []
            
            for position in positions_data:
                analytics = await self._calculate_position_analytics(
                    position, portfolio_value
                )
                if analytics:
                    position_analytics.append(analytics)
            
            return position_analytics
            
        except Exception as e:
            logger.error(f"Error calculating position analytics for user {user_id}: {e}")
            return []
    
    async def get_sector_allocation(self, user_id: int) -> List[SectorAllocation]:
        """Calculate portfolio sector allocation"""
        try:
            positions_data = await self._get_positions_data(user_id)
            portfolio_value = await self._get_portfolio_total_value(user_id)
            
            # Group by sector
            sector_data = defaultdict(lambda: {
                'market_value': 0.0,
                'position_count': 0,
                'pnl_contribution': 0.0,
                'returns': []
            })
            
            for position in positions_data:
                sector = await self._get_position_sector(position['symbol'])
                sector_data[sector]['market_value'] += position['market_value']
                sector_data[sector]['position_count'] += 1
                sector_data[sector]['pnl_contribution'] += position['unrealized_pnl']
                
                # Calculate daily return
                if position['current_price'] and position['avg_cost']:
                    daily_return = (position['current_price'] - position['avg_cost']) / position['avg_cost']
                    sector_data[sector]['returns'].append(daily_return)
            
            # Convert to SectorAllocation objects
            sector_allocations = []
            for sector, data in sector_data.items():
                weight_pct = (data['market_value'] / portfolio_value * 100) if portfolio_value > 0 else 0
                avg_return = np.mean(data['returns']) if data['returns'] else 0
                volatility = np.std(data['returns']) * np.sqrt(252) if len(data['returns']) > 1 else 0
                
                allocation = SectorAllocation(
                    sector=sector,
                    market_value=data['market_value'],
                    weight_pct=weight_pct,
                    position_count=data['position_count'],
                    pnl_contribution=data['pnl_contribution'],
                    avg_return=avg_return,
                    volatility=volatility
                )
                sector_allocations.append(allocation)
            
            # Sort by market value descending
            sector_allocations.sort(key=lambda x: x.market_value, reverse=True)
            return sector_allocations
            
        except Exception as e:
            logger.error(f"Error calculating sector allocation for user {user_id}: {e}")
            return []
    
    async def _calculate_all_metrics(self, user_id: int, portfolio_data: Dict[str, Any]) -> PortfolioMetrics:
        """Calculate all portfolio metrics"""
        
        # Basic metrics
        total_value = portfolio_data['total_value']
        cash_balance = portfolio_data['cash_balance']
        invested_value = total_value - cash_balance
        
        # P&L calculations
        pnl_metrics = await self._calculate_pnl_metrics(user_id, portfolio_data)
        
        # Risk metrics
        risk_metrics = await self._calculate_risk_metrics(user_id, portfolio_data)
        
        # Performance metrics
        performance_metrics = await self._calculate_performance_metrics(user_id, portfolio_data)
        
        # Position metrics
        position_metrics = await self._calculate_position_metrics(user_id)
        
        return PortfolioMetrics(
            # Basic
            total_value=total_value,
            cash_balance=cash_balance,
            invested_value=invested_value,
            total_return_pct=portfolio_data.get('total_return_pct', 0.0),
            
            # P&L
            unrealized_pnl=pnl_metrics['unrealized_pnl'],
            realized_pnl=pnl_metrics['realized_pnl'],
            intraday_pnl=pnl_metrics['intraday_pnl'],
            daily_pnl=pnl_metrics['daily_pnl'],
            weekly_pnl=pnl_metrics['weekly_pnl'],
            monthly_pnl=pnl_metrics['monthly_pnl'],
            ytd_pnl=pnl_metrics['ytd_pnl'],
            
            # Risk
            portfolio_var_1day=risk_metrics['var_1day'],
            portfolio_volatility=risk_metrics['volatility'],
            portfolio_beta=risk_metrics['beta'],
            max_drawdown=risk_metrics['max_drawdown'],
            
            # Performance
            sharpe_ratio=performance_metrics['sharpe_ratio'],
            alpha=performance_metrics['alpha'],
            tracking_error=performance_metrics['tracking_error'],
            information_ratio=performance_metrics['information_ratio'],
            
            # Positions
            position_count=position_metrics['count'],
            largest_position_pct=position_metrics['largest_pct'],
            top5_concentration=position_metrics['top5_pct'],
            sector_count=position_metrics['sector_count'],
            
            # Meta
            last_updated=timezone.now(),
            calculation_time_ms=0.0  # Will be set by caller
        )
    
    async def _calculate_pnl_metrics(self, user_id: int, portfolio_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate P&L across different timeframes"""
        try:
            # Get historical portfolio values
            historical_values = await self._get_historical_portfolio_values(user_id)
            current_value = portfolio_data['total_value']
            
            # Calculate unrealized P&L from positions
            unrealized_pnl = sum(pos['unrealized_pnl'] for pos in portfolio_data['positions'])
            
            # Get realized P&L from completed trades
            realized_pnl = await self._get_realized_pnl(user_id)
            
            # Calculate timeframe P&L
            intraday_pnl = current_value - historical_values.get('market_open', current_value)
            daily_pnl = current_value - historical_values.get('1d_ago', current_value)
            weekly_pnl = current_value - historical_values.get('7d_ago', current_value)
            monthly_pnl = current_value - historical_values.get('30d_ago', current_value)
            ytd_pnl = current_value - historical_values.get('ytd_start', current_value)
            
            return {
                'unrealized_pnl': unrealized_pnl,
                'realized_pnl': realized_pnl,
                'intraday_pnl': intraday_pnl,
                'daily_pnl': daily_pnl,
                'weekly_pnl': weekly_pnl,
                'monthly_pnl': monthly_pnl,
                'ytd_pnl': ytd_pnl
            }
            
        except Exception as e:
            logger.error(f"Error calculating P&L metrics: {e}")
            return {key: 0.0 for key in ['unrealized_pnl', 'realized_pnl', 'intraday_pnl', 
                                       'daily_pnl', 'weekly_pnl', 'monthly_pnl', 'ytd_pnl']}
    
    async def _calculate_risk_metrics(self, user_id: int, portfolio_data: Dict[str, Any]) -> Dict[str, float]:
        """Calculate portfolio risk metrics"""
        try:
            # Get historical returns
            returns = await self._get_portfolio_returns(user_id, days=252)  # 1 year
            
            if len(returns) < 30:  # Need minimum data
                return {
                    'var_1day': 0.0,
                    'volatility': 0.0,
                    'beta': 1.0,
                    'max_drawdown': 0.0
                }
            
            returns_array = np.array(returns)
            
            # Calculate VaR (5th percentile)
            var_1day = float(np.percentile(returns_array, 5)) * portfolio_data['total_value']
            
            # Calculate volatility (annualized)
            volatility = float(np.std(returns_array) * np.sqrt(252))
            
            # Calculate beta vs benchmark
            beta = await self._calculate_beta(user_id, returns)
            
            # Calculate maximum drawdown
            max_drawdown = await self._calculate_max_drawdown(user_id)
            
            return {
                'var_1day': var_1day,
                'volatility': volatility,
                'beta': beta,
                'max_drawdown': max_drawdown
            }
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
            return {'var_1day': 0.0, 'volatility': 0.0, 'beta': 1.0, 'max_drawdown': 0.0}
    
    async def _calculate_performance_metrics(self, user_id: int, portfolio_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
        """Calculate performance metrics"""
        try:
            # Get portfolio and benchmark returns
            portfolio_returns = await self._get_portfolio_returns(user_id, days=252)
            benchmark_returns = await self._get_benchmark_returns(days=252)
            
            if len(portfolio_returns) < 30:
                return {
                    'sharpe_ratio': None,
                    'alpha': None,
                    'tracking_error': None,
                    'information_ratio': None
                }
            
            portfolio_returns = np.array(portfolio_returns)
            
            # Calculate Sharpe ratio
            excess_returns = portfolio_returns - (self.risk_free_rate / 252)  # Daily risk-free rate
            sharpe_ratio = float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252))
            
            # Calculate metrics vs benchmark if available
            alpha = None
            tracking_error = None
            information_ratio = None
            
            if len(benchmark_returns) == len(portfolio_returns):
                benchmark_returns = np.array(benchmark_returns)
                
                # Alpha (excess return vs benchmark)
                portfolio_mean = np.mean(portfolio_returns) * 252
                benchmark_mean = np.mean(benchmark_returns) * 252
                alpha = float(portfolio_mean - benchmark_mean)
                
                # Tracking error (standard deviation of excess returns)
                excess_returns_vs_benchmark = portfolio_returns - benchmark_returns
                tracking_error = float(np.std(excess_returns_vs_benchmark) * np.sqrt(252))
                
                # Information ratio (alpha / tracking error)
                if tracking_error > 0:
                    information_ratio = float(alpha / tracking_error)
            
            return {
                'sharpe_ratio': sharpe_ratio if not np.isnan(sharpe_ratio) else None,
                'alpha': alpha,
                'tracking_error': tracking_error,
                'information_ratio': information_ratio
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {key: None for key in ['sharpe_ratio', 'alpha', 'tracking_error', 'information_ratio']}
    
    # Helper methods continue...
    @database_sync_to_async
    def _get_portfolio_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get comprehensive portfolio data"""
        try:
            from apps.trading_simulation.models import UserSimulationProfile
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            user = User.objects.get(id=user_id)
            profile = user.simulation_profile
            positions = user.simulated_positions.all()
            
            positions_data = []
            for pos in positions:
                positions_data.append({
                    'symbol': pos.instrument.real_ticker.symbol,
                    'quantity': float(pos.quantity),
                    'current_price': float(pos.current_price) if pos.current_price else 0.0,
                    'market_value': float(pos.market_value),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'daily_pnl': float(pos.daily_pnl),
                    'avg_cost': float(pos.average_cost) if pos.average_cost else 0.0
                })
            
            return {
                'total_value': float(profile.current_portfolio_value),
                'cash_balance': float(profile.virtual_cash_balance),
                'total_return_pct': profile.calculate_total_return_percentage(),
                'positions': positions_data
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio data for user {user_id}: {e}")
            return None
    
    async def _cache_analytics(self, user_id: int, metrics: PortfolioMetrics):
        """Cache analytics results"""
        try:
            cache_key = f"portfolio_analytics:{user_id}"
            cache.set(cache_key, metrics.to_dict(), self.cache_ttl)
        except Exception as e:
            logger.error(f"Error caching analytics: {e}")


# Global analytics service instance
portfolio_analytics_service = PortfolioAnalyticsService()
