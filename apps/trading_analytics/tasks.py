# apps/trading_analytics/tasks.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
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
