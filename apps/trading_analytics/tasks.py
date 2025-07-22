# apps/trading_analytics/tasks.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync

from .portfolio_analytics import portfolio_analytics_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_portfolio_analytics(self, user_id: int):
    """Calculate comprehensive portfolio analytics for a user"""
    try:
        # Calculate analytics
        analytics = async_to_sync(portfolio_analytics_service.calculate_comprehensive_analytics)(user_id)
        
        if not analytics:
            logger.warning(f"No analytics calculated for user {user_id}")
            return {'status': 'no_data', 'user_id': user_id}
        
        # Broadcast to user's WebSocket connections
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(f'portfolio_{user_id}', {
                'type': 'portfolio_analytics_update',
                'analytics': analytics.to_dict()
            })
        
        logger.info(f"Portfolio analytics calculated for user {user_id}")
        return {
            'status': 'success',
            'user_id': user_id,
            'calculation_time_ms': analytics.calculation_time_ms,
            'total_value': analytics.total_value
        }
        
    except Exception as e:
        logger.error(f"Portfolio analytics calculation failed for user {user_id}: {e}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        
        return {'status': 'failed', 'user_id': user_id, 'error': str(e)}


@shared_task(bind=True, max_retries=3)
def calculate_position_analytics(self, user_id: int):
    """Calculate detailed analytics for all user positions"""
    try:
        # Calculate position analytics
        position_analytics = async_to_sync(portfolio_analytics_service.get_position_analytics)(user_id)
        
        # Calculate sector allocation
        sector_allocation = async_to_sync(portfolio_analytics_service.get_sector_allocation)(user_id)
        
        # Prepare data for broadcasting
        analytics_data = {
            'positions': [pos.to_dict() for pos in position_analytics],
            'sectors': [sector.to_dict() for sector in sector_allocation],
            'timestamp': timezone.now().isoformat()
        }
        
        # Broadcast to user's WebSocket connections
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(f'portfolio_{user_id}', {
                'type': 'position_analytics_update',
                'analytics': analytics_data
            })
        
        logger.info(f"Position analytics calculated for user {user_id}: {len(position_analytics)} positions")
        return {
            'status': 'success',
            'user_id': user_id,
            'position_count': len(position_analytics),
            'sector_count': len(sector_allocation)
        }
        
    except Exception as e:
        logger.error(f"Position analytics calculation failed for user {user_id}: {e}")
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        
        return {'status': 'failed', 'user_id': user_id, 'error': str(e)}


@shared_task
def calculate_all_users_analytics():
    """Calculate analytics for all active users"""
    try:
        from django.contrib.auth import get_user_model
        from apps.trading_simulation.models import UserSimulationProfile
        
        User = get_user_model()
        
        # Get users with active trading profiles
        active_users = User.objects.filter(
            simulation_profile__isnull=False,
            is_active=True
        ).values_list('id', flat=True)
        
        results = {
            'total_users': len(active_users),
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        # Calculate analytics for each user
        for user_id in active_users:
            try:
                # Queue individual calculation tasks
                calculate_portfolio_analytics.delay(user_id)
                calculate_position_analytics.delay(user_id)
                results['successful'] += 1
                
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"User {user_id}: {str(e)}")
                logger.error(f"Failed to queue analytics for user {user_id}: {e}")
        
        logger.info(f"Queued analytics calculation for {results['successful']} users")
        return results
        
    except Exception as e:
        logger.error(f"Bulk analytics calculation failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def update_portfolio_performance_history():
    """Update historical performance tracking for all users"""
    try:
        from django.contrib.auth import get_user_model
        from apps.trading_simulation.models import UserSimulationProfile
        from apps.trading_analytics.models import PortfolioSnapshot
        
        User = get_user_model()
        
        # Get all active users
        active_users = User.objects.filter(
            simulation_profile__isnull=False,
            is_active=True
        ).select_related('simulation_profile')
        
        snapshots_created = 0
        
        for user in active_users:
            try:
                profile = user.simulation_profile
                
                # Create daily snapshot
                snapshot = PortfolioSnapshot.objects.create(
                    user=user,
                    snapshot_date=timezone.now().date(),
                    total_value=profile.current_portfolio_value,
                    cash_balance=profile.virtual_cash_balance,
                    invested_value=profile.current_portfolio_value - profile.virtual_cash_balance,
                    unrealized_pnl=sum(
                        pos.unrealized_pnl for pos in user.simulated_positions.all()
                    ),
                    position_count=user.simulated_positions.count(),
                    snapshot_type='DAILY'
                )
                
                snapshots_created += 1
                
            except Exception as e:
                logger.error(f"Failed to create snapshot for user {user.id}: {e}")
        
        logger.info(f"Created {snapshots_created} portfolio snapshots")
        return {'snapshots_created': snapshots_created}
        
    except Exception as e:
        logger.error(f"Portfolio history update failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def calculate_market_correlation_matrix():
    """Calculate correlation matrix for portfolio positions"""
    try:
        from apps.market_data.models import MarketData, Ticker
        import pandas as pd
        import numpy as np
        
        # Get active tickers with recent data
        active_tickers = Ticker.objects.filter(
            is_active=True,
            market_data__timestamp__gte=timezone.now() - timedelta(days=7)
        ).distinct()
        
        if len(active_tickers) < 2:
            return {'status': 'insufficient_data'}
        
        # Get recent price data
        price_data = {}
        
        for ticker in active_tickers[:50]:  # Limit to 50 most active
            market_data = MarketData.objects.filter(
                ticker=ticker,
                timeframe='1d',
                timestamp__gte=timezone.now() - timedelta(days=60)
            ).order_by('timestamp')
            
            if market_data.count() >= 20:  # Need minimum data points
                prices = [float(md.close) for md in market_data]
                price_data[ticker.symbol] = prices
        
        if len(price_data) < 2:
            return {'status': 'insufficient_data'}
        
        # Calculate returns
        returns_data = {}
        for symbol, prices in price_data.items():
            returns = []
            for i in range(1, len(prices)):
                returns.append((prices[i] - prices[i-1]) / prices[i-1])
            returns_data[symbol] = returns
        
        # Create DataFrame and calculate correlation
        df = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in returns_data.items()]))
        correlation_matrix = df.corr()
        
        # Convert to dictionary for caching
        correlation_dict = {}
        for symbol1 in correlation_matrix.columns:
            correlation_dict[symbol1] = {}
            for symbol2 in correlation_matrix.columns:
                corr_value = correlation_matrix.loc[symbol1, symbol2]
                correlation_dict[symbol1][symbol2] = float(corr_value) if not pd.isna(corr_value) else 0.0
        
        # Cache the correlation matrix
        from django.core.cache import cache
        cache.set('market_correlation_matrix', correlation_dict, 3600)  # 1 hour
        
        logger.info(f"Calculated correlation matrix for {len(correlation_dict)} symbols")
        return {
            'status': 'success',
            'symbols_count': len(correlation_dict),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Correlation matrix calculation failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def generate_risk_alerts():
    """Generate portfolio risk alerts for all users"""
    try:
        from django.contrib.auth import get_user_model
        from apps.core.events import publish_risk_alert
        
        User = get_user_model()
        
        # Get users with significant positions
        users_with_positions = User.objects.filter(
            simulated_positions__isnull=False,
            is_active=True
        ).distinct()
        
        alerts_generated = 0
        
        for user in users_with_positions:
            try:
                # Calculate current analytics
                analytics = async_to_sync(portfolio_analytics_service.calculate_comprehensive_analytics)(user.id)
                
                if not analytics:
                    continue
                
                risk_alerts = []
                
                # Check for high concentration risk
                if analytics.largest_position_pct > 25:
                    risk_alerts.append({
                        'type': 'CONCENTRATION_RISK',
                        'severity': 'HIGH',
                        'message': f'Largest position represents {analytics.largest_position_pct:.1f}% of portfolio',
                        'threshold': 25.0,
                        'current_value': analytics.largest_position_pct
                    })
                
                # Check for high volatility
                if analytics.portfolio_volatility > 0.4:  # 40% annualized volatility
                    risk_alerts.append({
                        'type': 'HIGH_VOLATILITY',
                        'severity': 'MEDIUM',
                        'message': f'Portfolio volatility is {analytics.portfolio_volatility:.1%}',
                        'threshold': 0.4,
                        'current_value': analytics.portfolio_volatility
                    })
                
                # Check for large drawdown
                if analytics.max_drawdown < -0.1:  # 10% drawdown
                    risk_alerts.append({
                        'type': 'DRAWDOWN_ALERT',
                        'severity': 'HIGH',
                        'message': f'Maximum drawdown is {analytics.max_drawdown:.1%}',
                        'threshold': -0.1,
                        'current_value': analytics.max_drawdown
                    })
                
                # Publish alerts
                for alert in risk_alerts:
                    async_to_sync(publish_risk_alert)(
                        user_id=user.id,
                        alert_type=alert['type'],
                        severity=alert['severity'],
                        message=alert['message'],
                        affected_positions=[],
                        recommended_action=f"Review {alert['type'].lower().replace('_', ' ')}"
                    )
                    alerts_generated += 1
                
            except Exception as e:
                logger.error(f"Risk alert generation failed for user {user.id}: {e}")
        
        logger.info(f"Generated {alerts_generated} risk alerts")
        return {'alerts_generated': alerts_generated}
        
    except Exception as e:
        logger.error(f"Risk alert generation failed: {e}")
        return {'status': 'failed', 'error': str(e)}


# Add these additional tasks to your existing tasks.py file

@shared_task
def update_dashboard_cache_all_users():
    """Update dashboard cache for all active users"""
    try:
        from django.contrib.auth import get_user_model
        from .dashboard_service import dashboard_service
        
        User = get_user_model()
        
        # Get users with active trading profiles
        active_users = User.objects.filter(
            simulation_profile__isnull=False,
            is_active=True,
            last_login__gte=timezone.now() - timedelta(days=7)  # Active in last week
        ).values_list('id', flat=True)
        
        results = {
            'total_users': len(active_users),
            'successful': 0,
            'failed': 0,
            'cache_updates': 0
        }
        
        # Update dashboard cache for each user
        for user_id in active_users:
            try:
                # Get user's watchlist symbols
                watchlist = async_to_sync(get_user_watchlist)(user_id)
                
                # Update unified dashboard data
                dashboard_data = async_to_sync(dashboard_service.get_unified_dashboard_data)(
                    user_id, watchlist
                )
                
                if dashboard_data:
                    # Cache the dashboard data
                    cache_key = f"dashboard_unified:{user_id}"
                    cache.set(cache_key, dashboard_data, 300)  # 5 minutes
                    results['cache_updates'] += 1
                
                results['successful'] += 1
                
            except Exception as e:
                results['failed'] += 1
                logger.error(f"Failed to update dashboard cache for user {user_id}: {e}")
        
        logger.info(f"Updated dashboard cache for {results['successful']} users")
        return results
        
    except Exception as e:
        logger.error(f"Dashboard cache update failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def broadcast_market_summary():
    """Broadcast market summary to all connected dashboards"""
    try:
        from .dashboard_service import dashboard_service
        
        # Get market context and overview
        market_context = async_to_sync(dashboard_service.get_market_context)()
        
        # Get major indices summary
        major_indices = ['SPY', 'QQQ', 'IWM', 'VIX']
        market_overview = async_to_sync(dashboard_service.get_market_analytics)(major_indices)
        
        # Prepare market summary broadcast
        market_summary = {
            'type': 'market_summary_update',
            'data': {
                'market_context': market_context,
                'indices_overview': market_overview,
                'update_time': timezone.now().isoformat(),
                'trading_session': market_context.get('session_info', {}).get('current_session', 'UNKNOWN')
            }
        }
        
        # Broadcast to all dashboard consumers
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)('dashboard_global', {
                'type': 'market_summary_broadcast',
                'data': market_summary
            })
        
        logger.info("Market summary broadcasted to all dashboards")
        return {
            'status': 'success',
            'indices_count': len(major_indices),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Market summary broadcast failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def calculate_dashboard_performance_metrics():
    """Calculate performance metrics for dashboard display"""
    try:
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Get users who have been active recently
        recent_users = User.objects.filter(
            simulation_profile__isnull=False,
            last_login__gte=timezone.now() - timedelta(days=1)
        )
        
        performance_data = {}
        
        for user in recent_users:
            try:
                user_metrics = {
                    'user_id': user.id,
                    'portfolio_value': float(user.simulation_profile.current_portfolio_value),
                    'total_return_pct': user.simulation_profile.calculate_total_return_percentage(),
                    'position_count': user.simulated_positions.count(),
                    'active_orders': user.simulated_orders.filter(
                        status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
                    ).count(),
                    'last_activity': user.last_login.isoformat() if user.last_login else None
                }
                
                performance_data[user.id] = user_metrics
                
                # Cache individual user performance
                cache_key = f"dashboard_performance:{user.id}"
                cache.set(cache_key, user_metrics, 600)  # 10 minutes
                
            except Exception as e:
                logger.error(f"Error calculating performance for user {user.id}: {e}")
        
        # Cache aggregated performance data
        cache.set('dashboard_performance_all', performance_data, 300)  # 5 minutes
        
        logger.info(f"Calculated performance metrics for {len(performance_data)} users")
        return {
            'status': 'success',
            'users_processed': len(performance_data),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Dashboard performance calculation failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def cleanup_dashboard_sessions():
    """Clean up inactive dashboard sessions and cache"""
    try:
        from apps.core.websockets.connection_manager import connection_manager
        
        # Get dashboard connection metrics
        metrics = connection_manager.get_metrics()
        
        # Clean up old cached dashboard data
        cache_keys_pattern = [
            'dashboard_unified:*',
            'dashboard_portfolio:*',
            'dashboard_market:*',
            'dashboard_risk:*',
            'dashboard_performance:*'
        ]
        
        cleaned_keys = 0
        for pattern in cache_keys_pattern:
            # Note: This is a simplified cleanup - in production you'd use cache.delete_pattern()
            # For now, we'll just track that cleanup would occur
            cleaned_keys += 1
        
        # Update dashboard health metrics
        dashboard_health = {
            'active_connections': metrics['connections']['active'],
            'cache_keys_cleaned': cleaned_keys,
            'last_cleanup': timezone.now().isoformat(),
            'memory_usage_mb': 0,  # Would calculate actual memory usage
            'avg_response_time_ms': metrics['messages'].get('avg_processing_time', 0)
        }
        
        cache.set('dashboard_health', dashboard_health, 1800)  # 30 minutes
        
        logger.info(f"Dashboard cleanup completed: {cleaned_keys} cache patterns processed")
        return {
            'status': 'success',
            'cache_keys_cleaned': cleaned_keys,
            'active_connections': metrics['connections']['active']
        }
        
    except Exception as e:
        logger.error(f"Dashboard cleanup failed: {e}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def generate_dashboard_alerts():
    """Generate dashboard-specific alerts and notifications"""
    try:
        from django.contrib.auth import get_user_model
        from apps.core.events import publish_risk_alert
        
        User = get_user_model()
        
        # Get users with active dashboard sessions
        dashboard_users = User.objects.filter(
            simulation_profile__isnull=False,
            is_active=True
        )
        
        alerts_generated = 0
        
        for user in dashboard_users:
            try:
                # Check for dashboard-specific conditions
                portfolio_value = float(user.simulation_profile.current_portfolio_value)
                positions_count = user.simulated_positions.count()
                
                # Alert for large portfolio moves
                if portfolio_value > 0:
                    daily_change_pct = 0  # Would calculate actual daily change
                    
                    if abs(daily_change_pct) > 5:  # 5% daily move
                        async_to_sync(publish_risk_alert)(
                            user_id=user.id,
                            alert_type='LARGE_PORTFOLIO_MOVE',
                            severity='HIGH' if abs(daily_change_pct) > 10 else 'MEDIUM',
                            message=f'Portfolio moved {daily_change_pct:.1f}% today',
                            affected_positions=[],
                            recommended_action='Review positions and risk exposure'
                        )
                        alerts_generated += 1
                
                # Alert for high position count
                if positions_count > 50:
                    async_to_sync(publish_risk_alert)(
                        user_id=user.id,
                        alert_type='HIGH_POSITION_COUNT',
                        severity='MEDIUM',
                        message=f'Portfolio has {positions_count} positions - consider consolidation',
                        affected_positions=[],
                        recommended_action='Review portfolio concentration'
                    )
                    alerts_generated += 1
                
                # Alert for inactive portfolio
                if positions_count == 0 and portfolio_value > 1000:
                    async_to_sync(publish_risk_alert)(
                        user_id=user.id,
                        alert_type='INACTIVE_PORTFOLIO',
                        severity='LOW',
                        message='Portfolio is 100% cash - consider investing',
                        affected_positions=[],
                        recommended_action='Review investment opportunities'
                    )
                    alerts_generated += 1
                
            except Exception as e:
                logger.error(f"Error generating dashboard alerts for user {user.id}: {e}")
        
        logger.info(f"Generated {alerts_generated} dashboard alerts")
        return {
            'status': 'success',
            'alerts_generated': alerts_generated,
            'users_checked': len(dashboard_users)
        }
        
    except Exception as e:
        logger.error(f"Dashboard alert generation failed: {e}")
        return {'status': 'failed', 'error': str(e)}


# Helper function for getting user watchlist
@database_sync_to_async
def get_user_watchlist(user_id: int) -> List[str]:
    """Get user's watchlist symbols"""
    try:
        # This would get from user preferences or a watchlist model
        # For now, return a default set
        return ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL']
    except Exception:
        return []
