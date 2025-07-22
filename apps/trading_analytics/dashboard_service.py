# apps/trading_analytics/dashboard_service.py
"""
Market Dashboard Service
======================

Service layer for the Integrated Market Dashboard that handles:
- Data aggregation from multiple sources
- Real-time data correlation and analysis
- Dashboard-specific business logic
- Performance optimization for dashboard updates
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from channels.db import database_sync_to_async

from .portfolio_analytics import portfolio_analytics_service
from apps.market_data.streaming import streaming_engine
from apps.market_data.analysis import enhanced_ta_service

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Centralized service for market dashboard data aggregation and correlation
    """
    
    def __init__(self):
        self.cache_ttl = {
            'market_overview': 60,    # 1 minute
            'portfolio_summary': 30,  # 30 seconds
            'risk_summary': 300,      # 5 minutes
            'performance': 300,       # 5 minutes
        }
    
    async def get_unified_dashboard_data(self, user_id: int, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Get unified dashboard data combining all real-time sources
        """
        try:
            # Start all data requests concurrently
            tasks = {
                'portfolio': self.get_portfolio_analytics(user_id),
                'market': self.get_market_analytics(symbols or []),
                'risk': self.get_risk_analytics(user_id),
                'performance': self.get_performance_analytics(user_id),
                'alerts': self.get_active_alerts(user_id),
                'execution': self.get_execution_summary(user_id)
            }
            
            # Wait for all data
            results = {}
            for key, task in tasks.items():
                try:
                    results[key] = await task
                except Exception as e:
                    logger.error(f"Error getting {key} data: {e}")
                    results[key] = {}
            
            # Add correlation analysis
            results['correlations'] = await self.analyze_correlations(user_id, symbols or [])
            
            # Add market context
            results['market_context'] = await self.get_market_context()
            
            # Add data freshness metrics
            results['data_quality'] = await self.calculate_data_quality(results)
            
            return {
                'dashboard_data': results,
                'timestamp': timezone.now().isoformat(),
                'user_id': user_id,
                'symbols_tracked': len(symbols or [])
            }
            
        except Exception as e:
            logger.error(f"Error getting unified dashboard data for user {user_id}: {e}")
            return {}
    
    async def get_portfolio_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive portfolio analytics"""
        try:
            # Try cache first
            cache_key = f"dashboard_portfolio:{user_id}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            # Get analytics from service
            analytics = await portfolio_analytics_service.calculate_comprehensive_analytics(user_id)
            
            if analytics:
                portfolio_data = {
                    'summary': {
                        'total_value': analytics.total_value,
                        'cash_balance': analytics.cash_balance,
                        'invested_value': analytics.invested_value,
                        'total_return_pct': analytics.total_return_pct,
                        'daily_pnl': analytics.daily_pnl,
                        'unrealized_pnl': analytics.unrealized_pnl
                    },
                    'risk_metrics': {
                        'portfolio_var': analytics.portfolio_var_1day,
                        'volatility': analytics.portfolio_volatility,
                        'beta': analytics.portfolio_beta,
                        'max_drawdown': analytics.max_drawdown
                    },
                    'performance_metrics': {
                        'sharpe_ratio': analytics.sharpe_ratio,
                        'alpha': analytics.alpha,
                        'tracking_error': analytics.tracking_error
                    },
                    'position_metrics': {
                        'position_count': analytics.position_count,
                        'largest_position_pct': analytics.largest_position_pct,
                        'top5_concentration': analytics.top5_concentration,
                        'sector_count': analytics.sector_count
                    }
                }
                
                # Cache the data
                cache.set(cache_key, portfolio_data, self.cache_ttl['portfolio_summary'])
                return portfolio_data
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting portfolio analytics: {e}")
            return {}
    
    async def get_market_analytics(self, symbols: List[str]) -> Dict[str, Any]:
        """Get market analytics for tracked symbols"""
        try:
            cache_key = f"dashboard_market:{hash(tuple(sorted(symbols)))}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            market_data = {}
            technical_signals = {}
            
            # Get data for each symbol
            for symbol in symbols:
                try:
                    # Get current quote
                    quote = await streaming_engine.get_current_quote(symbol)
                    if quote:
                        market_data[symbol] = {
                            'price': float(quote.price),
                            'volume': quote.volume,
                            'change_24h': float(quote.change_24h) if quote.change_24h else None,
                            'change_pct_24h': quote.change_pct_24h,
                            'bid': float(quote.bid) if quote.bid else None,
                            'ask': float(quote.ask) if quote.ask else None,
                            'timestamp': quote.timestamp.isoformat()
                        }
                    
                    # Get technical signal
                    signal = enhanced_ta_service.get_cached_signal(symbol)
                    if signal:
                        technical_signals[symbol] = {
                            'signal_type': signal.signal_type.value,
                            'strength': signal.strength,
                            'confidence': signal.confidence.value,
                            'trend_direction': signal.trend_direction.value
                        }
                
                except Exception as e:
                    logger.error(f"Error getting market data for {symbol}: {e}")
            
            # Calculate market overview
            overview = await self._calculate_market_overview(market_data)
            
            result = {
                'quotes': market_data,
                'technical_signals': technical_signals,
                'overview': overview,
                'symbols_count': len(symbols),
                'data_completeness': len(market_data) / len(symbols) if symbols else 0
            }
            
            cache.set(cache_key, result, self.cache_ttl['market_overview'])
            return result
            
        except Exception as e:
            logger.error(f"Error getting market analytics: {e}")
            return {}
    
    async def get_risk_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get risk analytics and alerts"""
        try:
            cache_key = f"dashboard_risk:{user_id}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            # Get portfolio value for risk calculations
            portfolio_value = await self._get_portfolio_value(user_id)
            positions_count = await self._get_positions_count(user_id)
            
            # Get risk alerts
            active_alerts = await self._get_active_risk_alerts(user_id)
            
            # Calculate basic risk metrics
            risk_score = await self._calculate_risk_score(user_id)
            
            risk_data = {
                'portfolio_var_1d': portfolio_value * 0.02,  # Simplified 2% VaR
                'positions_count': positions_count,
                'risk_score': risk_score,
                'alerts': {
                    'active_count': len(active_alerts),
                    'high_severity_count': len([a for a in active_alerts if a.get('severity') == 'HIGH']),
                    'recent_alerts': active_alerts[:5]  # Last 5 alerts
                },
                'concentration_risk': {
                    'largest_position_pct': await self._get_largest_position_pct(user_id),
                    'top_5_concentration': await self._get_top5_concentration(user_id)
                },
                'limits_status': {
                    'position_limits_ok': True,  # Would check actual limits
                    'concentration_limits_ok': True,
                    'daily_loss_limits_ok': True
                }
            }
            
            cache.set(cache_key, risk_data, self.cache_ttl['risk_summary'])
            return risk_data
            
        except Exception as e:
            logger.error(f"Error getting risk analytics: {e}")
            return {}
    
    async def get_performance_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get performance analytics"""
        try:
            cache_key = f"dashboard_performance:{user_id}"
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            # Get user performance data
            user_profile = await self._get_user_profile(user_id)
            
            if not user_profile:
                return {}
            
            # Calculate performance metrics
            total_return_pct = user_profile.calculate_total_return_percentage()
            win_rate = user_profile.get_win_rate()
            
            performance_data = {
                'current_performance': {
                    'total_return_pct': total_return_pct,
                    'portfolio_value': float(user_profile.current_portfolio_value),
                    'initial_balance': float(user_profile.initial_virtual_balance),
                    'trades_executed': user_profile.total_trades_executed,
                    'profitable_trades': user_profile.profitable_trades,
                    'win_rate': win_rate
                },
                'timeframe_returns': {
                    'daily': 0,    # Would calculate from historical data
                    'weekly': 0,
                    'monthly': 0,
                    'ytd': total_return_pct
                },
                'risk_adjusted': {
                    'sharpe_ratio': None,   # Would calculate with historical data
                    'max_drawdown': None,
                    'volatility': None
                },
                'benchmark_comparison': {
                    'benchmark_return': 0,  # Would get benchmark data
                    'excess_return': 0,
                    'tracking_error': None
                }
            }
            
            cache.set(cache_key, performance_data, self.cache_ttl['performance'])
            return performance_data
            
        except Exception as e:
            logger.error(f"Error getting performance analytics: {e}")
            return {}
    
    async def get_active_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Get active alerts for the user"""
        try:
            alerts = await self._get_active_risk_alerts(user_id)
            
            return [{
                'id': alert.get('id'),
                'type': alert.get('alert_type', 'UNKNOWN'),
                'severity': alert.get('severity', 'MEDIUM'),
                'title': alert.get('title', 'Alert'),
                'message': alert.get('message', ''),
                'triggered_at': alert.get('triggered_at'),
                'status': alert.get('status', 'ACTIVE')
            } for alert in alerts]
            
        except Exception as e:
            logger.error(f"Error getting active alerts: {e}")
            return []
    
    async def get_execution_summary(self, user_id: int) -> Dict[str, Any]:
        """Get execution summary (orders, algorithms)"""
        try:
            # Get active orders count
            active_orders_count = await self._get_active_orders_count(user_id)
            
            # Get active algorithms count
            active_algorithms_count = await self._get_active_algorithms_count(user_id)
            
            # Get recent execution activity
            recent_activity = await self._get_recent_execution_activity(user_id)
            
            return {
                'active_orders': active_orders_count,
                'active_algorithms': active_algorithms_count,
                'recent_activity': recent_activity,
                'execution_quality': {
                    'avg_slippage_bps': 0,  # Would calculate
                    'fill_rate_pct': 100,   # Would calculate
                    'avg_execution_time_ms': 50  # Would calculate
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting execution summary: {e}")
            return {}
    
    async def analyze_correlations(self, user_id: int, symbols: List[str]) -> Dict[str, Any]:
        """Analyze correlations between portfolio positions and market"""
        try:
            if len(symbols) < 2:
                return {}
            
            # Get correlation matrix from cache (calculated by background task)
            correlation_matrix = cache.get('market_correlation_matrix', {})
            
            # Extract relevant correlations for user's symbols
            relevant_correlations = {}
            for symbol1 in symbols:
                if symbol1 in correlation_matrix:
                    relevant_correlations[symbol1] = {}
                    for symbol2 in symbols:
                        if symbol2 in correlation_matrix[symbol1]:
                            relevant_correlations[symbol1][symbol2] = correlation_matrix[symbol1][symbol2]
            
            # Calculate average correlation
            all_correlations = []
            for symbol1_corrs in relevant_correlations.values():
                for corr_value in symbol1_corrs.values():
                    if corr_value != 1.0:  # Exclude self-correlation
                        all_correlations.append(corr_value)
            
            avg_correlation = sum(all_correlations) / len(all_correlations) if all_correlations else 0
            
            return {
                'correlation_matrix': relevant_correlations,
                'average_correlation': avg_correlation,
                'max_correlation': max(all_correlations) if all_correlations else 0,
                'min_correlation': min(all_correlations) if all_correlations else 0,
                'diversification_ratio': 1 - avg_correlation,
                'analysis_timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing correlations: {e}")
            return {}
    
    async def get_market_context(self) -> Dict[str, Any]:
        """Get overall market context and conditions"""
        try:
            # Get major market indices
            indices_data = {}
            major_indices = ['SPY', 'QQQ', 'IWM', 'VIX']
            
            for index in major_indices:
                quote = await streaming_engine.get_current_quote(index)
                if quote:
                    indices_data[index] = {
                        'price': float(quote.price),
                        'change_pct': quote.change_pct_24h or 0
                    }
            
            # Determine market sentiment
            market_sentiment = self._determine_market_sentiment(indices_data)
            
            # Get market session info
            session_info = self._get_market_session_info()
            
            return {
                'indices': indices_data,
                'market_sentiment': market_sentiment,
                'session_info': session_info,
                'volatility_regime': self._assess_volatility_regime(indices_data),
                'trend_analysis': self._analyze_market_trend(indices_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting market context: {e}")
            return {}
    
    async def calculate_data_quality(self, dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall data quality metrics"""
        try:
            quality_scores = []
            
            # Check portfolio data quality
            if 'portfolio' in dashboard_data and dashboard_data['portfolio']:
                quality_scores.append(95)  # High quality for portfolio data
            
            # Check market data quality
            market_data = dashboard_data.get('market', {})
            if 'quotes' in market_data:
                completeness = market_data.get('data_completeness', 0)
                quality_scores.append(completeness * 100)
            
            # Check risk data quality
            if 'risk' in dashboard_data and dashboard_data['risk']:
                quality_scores.append(90)
            
            overall_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
            
            return {
                'overall_score': overall_quality,
                'component_scores': {
                    'portfolio': 95 if dashboard_data.get('portfolio') else 0,
                    'market': market_data.get('data_completeness', 0) * 100,
                    'risk': 90 if dashboard_data.get('risk') else 0,
                    'performance': 85 if dashboard_data.get('performance') else 0
                },
                'data_age_seconds': (timezone.now() - timezone.now()).total_seconds(),
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating data quality: {e}")
            return {'overall_score': 0}
    
    # Helper methods with database operations
    @database_sync_to_async
    def _get_portfolio_value(self, user_id: int) -> float:
        """Get user's portfolio value"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return float(user.simulation_profile.current_portfolio_value)
        except Exception:
            return 0.0
    
    @database_sync_to_async
    def _get_positions_count(self, user_id: int) -> int:
        """Get user's positions count"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return user.simulated_positions.count()
        except Exception:
            return 0
    
    @database_sync_to_async
    def _get_user_profile(self, user_id: int):
        """Get user simulation profile"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return user.simulation_profile
        except Exception:
            return None
    
    @database_sync_to_async
    def _get_active_risk_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Get active risk alerts for user"""
        try:
            from apps.trading_analytics.models import RiskAlert
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            user = User.objects.get(id=user_id)
            alerts = user.real_time_risk_alerts.filter(status='ACTIVE').order_by('-triggered_at')[:10]
            
            return [{
                'id': alert.id,
                'alert_type': alert.alert_type,
                'severity': alert.severity,
                'title': alert.title,
                'message': alert.message,
                'triggered_at': alert.triggered_at.isoformat(),
                'status': alert.status
            } for alert in alerts]
        except Exception:
            return []
    
    # Market analysis helper methods
    async def _calculate_market_overview(self, market_data: Dict[str, Dict]) -> Dict[str, Any]:
        """Calculate market overview from quotes"""
        try:
            if not market_data:
                return {}
            
            # Calculate market statistics
            price_changes = [data.get('change_pct_24h', 0) for data in market_data.values() if data.get('change_pct_24h') is not None]
            
            if price_changes:
                avg_change = sum(price_changes) / len(price_changes)
                positive_count = len([change for change in price_changes if change > 0])
                advance_decline_ratio = positive_count / len(price_changes)
            else:
                avg_change = 0
                advance_decline_ratio = 0.5
            
            return {
                'average_change_pct': avg_change,
                'advancing_count': len([change for change in price_changes if change > 0]),
                'declining_count': len([change for change in price_changes if change < 0]),
                'advance_decline_ratio': advance_decline_ratio,
                'market_breadth': 'POSITIVE' if advance_decline_ratio > 0.6 else 'NEGATIVE' if advance_decline_ratio < 0.4 else 'NEUTRAL',
                'symbols_analyzed': len(market_data)
            }
        except Exception as e:
            logger.error(f"Error calculating market overview: {e}")
            return {}
    
    def _determine_market_sentiment(self, indices_data: Dict[str, Dict]) -> Dict[str, Any]:
        """Determine overall market sentiment"""
        try:
            spy_change = indices_data.get('SPY', {}).get('change_pct', 0)
            vix_level = indices_data.get('VIX', {}).get('price', 20)
            
            # Simple sentiment calculation
            if spy_change > 1 and vix_level < 20:
                sentiment = 'BULLISH'
            elif spy_change < -1 or vix_level > 30:
                sentiment = 'BEARISH'
            else:
                sentiment = 'NEUTRAL'
            
            return {
                'overall_sentiment': sentiment,
                'fear_greed_score': max(0, min(100, 50 + spy_change * 10)),  # Simplified
                'volatility_level': 'HIGH' if vix_level > 30 else 'LOW' if vix_level < 15 else 'MEDIUM'
            }
        except Exception:
            return {'overall_sentiment': 'NEUTRAL'}
    
    def _get_market_session_info(self) -> Dict[str, Any]:
        """Get current market session information"""
        now = timezone.now()
        
        # Simplified - would use real market hours
        return {
            'current_session': 'REGULAR',
            'market_open': True,
            'next_open': None,
            'next_close': None,
            'trading_day': now.weekday() < 5
        }
    
    def _assess_volatility_regime(self, indices_data: Dict[str, Dict]) -> str:
        """Assess current volatility regime"""
        vix_level = indices_data.get('VIX', {}).get('price', 20)
        
        if vix_level > 30:
            return 'HIGH_VOLATILITY'
        elif vix_level < 15:
            return 'LOW_VOLATILITY'
        else:
            return 'NORMAL_VOLATILITY'
    
    def _analyze_market_trend(self, indices_data: Dict[str, Dict]) -> Dict[str, str]:
        """Analyze market trend from indices"""
        try:
            trends = {}
            
            for index, data in indices_data.items():
                change_pct = data.get('change_pct', 0)
                
                if change_pct > 1:
                    trends[index] = 'STRONG_UP'
                elif change_pct > 0.25:
                    trends[index] = 'UP'
                elif change_pct < -1:
                    trends[index] = 'STRONG_DOWN'
                elif change_pct < -0.25:
                    trends[index] = 'DOWN'
                else:
                    trends[index] = 'SIDEWAYS'
            
            return trends
        except Exception:
            return {}
    
    # Additional helper methods for execution data
    @database_sync_to_async
    def _get_active_orders_count(self, user_id: int) -> int:
        """Get count of active orders"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return user.simulated_orders.filter(
                status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
            ).count()
        except Exception:
            return 0
    
    @database_sync_to_async
    def _get_active_algorithms_count(self, user_id: int) -> int:
        """Get count of active algorithms"""
        try:
            from apps.order_management.models import AlgorithmicOrder
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return user.algorithmic_orders.filter(
                status__in=['PENDING', 'RUNNING', 'PAUSED']
            ).count()
        except Exception:
            return 0
    
    @database_sync_to_async
    def _get_recent_execution_activity(self, user_id: int) -> List[Dict[str, Any]]:
        """Get recent execution activity"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            # Get recent filled orders
            recent_orders = user.simulated_orders.filter(
                status='FILLED',
                completion_timestamp__gte=timezone.now() - timedelta(hours=24)
            ).order_by('-completion_timestamp')[:10]
            
            return [{
                'type': 'ORDER_FILL',
                'symbol': order.instrument.real_ticker.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'price': float(order.average_fill_price) if order.average_fill_price else None,
                'timestamp': order.completion_timestamp.isoformat() if order.completion_timestamp else None
            } for order in recent_orders]
        except Exception:
            return []
    
    @database_sync_to_async
    def _calculate_risk_score(self, user_id: int) -> str:
        """Calculate overall risk score for user"""
        try:
            # Simplified risk score calculation
            positions_count = self._get_positions_count(user_id)
            
            if positions_count > 20:
                return 'HIGH'
            elif positions_count > 10:
                return 'MEDIUM'
            else:
                return 'LOW'
        except Exception:
            return 'UNKNOWN'
    
    @database_sync_to_async
    def _get_largest_position_pct(self, user_id: int) -> float:
        """Get largest position as percentage of portfolio"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            positions = user.simulated_positions.all()
            portfolio_value = float(user.simulation_profile.current_portfolio_value)
            
            if not positions or portfolio_value == 0:
                return 0
            
            largest_value = max([float(pos.market_value) for pos in positions])
            return (largest_value / portfolio_value) * 100
        except Exception:
            return 0
    
    @database_sync_to_async
    def _get_top5_concentration(self, user_id: int) -> float:
        """Get top 5 positions concentration"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            
            positions = user.simulated_positions.all()
            portfolio_value = float(user.simulation_profile.current_portfolio_value)
            
            if not positions or portfolio_value == 0:
                return 0
            
            position_values = sorted([float(pos.market_value) for pos in positions], reverse=True)
            top_5_value = sum(position_values[:5])
            return (top_5_value / portfolio_value) * 100
        except Exception:
            return 0


# Global dashboard service instance
dashboard_service = DashboardService()
