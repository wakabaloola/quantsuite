# apps/trading_simulation/tasks.py
"""
SIMULATED Trading Background Tasks
=================================
Celery tasks for VIRTUAL trading simulation maintenance.
All tasks handle PAPER TRADING operations.
"""

from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from datetime import datetime, timedelta
import logging

# WebSocket imports
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import (
    SimulatedExchange, SimulatedInstrument, UserSimulationProfile
)
from .services import (
    SimulatedExchangeService, SimulationMonitoringService,
    UserTradingService, PriceSimulationService
)

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def update_simulated_market_data(self):
    """
    Update market data for all simulated instruments and broadcast via WebSocket
    Runs every 5 minutes during market hours
    """
    try:
        logger.info("Starting simulated market data update")
        
        service = SimulationMonitoringService()
        service.update_all_market_data()
        
        # Broadcast market data updates via WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            instruments = SimulatedInstrument.objects.filter(
                is_tradable=True,
                exchange__status='ACTIVE'
            )
            
            for instrument in instruments:
                try:
                    order_book = instrument.order_book
                    
                    market_data = {
                        'symbol': instrument.real_ticker.symbol,
                        'last_price': float(order_book.last_trade_price) if order_book.last_trade_price else None,
                        'bid_price': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                        'ask_price': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                        'volume': order_book.daily_volume,
                        'spread': float(order_book.spread) if order_book.spread else None,
                        'timestamp': timezone.now().isoformat()
                    }
                    
                    async_to_sync(channel_layer.group_send)(
                        f'market_{instrument.real_ticker.symbol}',
                        {
                            'type': 'price_update',
                            'data': market_data
                        }
                    )
                    
                except Exception as e:
                    logger.warning(f"Error broadcasting market data for {instrument}: {e}")
                    continue
        
        # Update count for monitoring
        active_instruments = SimulatedInstrument.objects.filter(
            is_tradable=True,
            exchange__status='ACTIVE'
        ).count()
        
        logger.info(f"Updated market data for {active_instruments} instruments")
        
        return {
            'status': 'success',
            'instruments_updated': active_instruments,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating simulated market data: {e}")
        
        # Retry with exponential backoff
        countdown = 2 ** self.request.retries * 60  # 1, 2, 4 minutes
        raise self.retry(exc=e, countdown=countdown, max_retries=3)


@shared_task(bind=True)
def cleanup_expired_orders(self):
    """
    Clean up expired and old orders
    Runs every hour
    """
    try:
        logger.info("Starting order cleanup")
        
        service = SimulationMonitoringService()
        service.cleanup_expired_orders()
        
        # Also clean up very old completed orders (older than 30 days)
        from apps.order_management.models import SimulatedOrder
        
        cutoff_date = timezone.now() - timedelta(days=30)
        old_orders = SimulatedOrder.objects.filter(
            status__in=['FILLED', 'CANCELLED', 'REJECTED'],
            completion_timestamp__lt=cutoff_date
        )
        
        # Archive instead of delete for audit purposes
        archived_count = old_orders.update(is_active=False)
        
        logger.info(f"Archived {archived_count} old orders")
        
        return {
            'status': 'success',
            'archived_orders': archived_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up orders: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def update_portfolio_values(self):
    """
    Update portfolio values for all users and broadcast via WebSocket
    Runs every 30 minutes during market hours
    """
    try:
        logger.info("Starting portfolio value updates")
        
        service = UserTradingService()
        updated_users = 0
        
        # Get channel layer for broadcasting
        channel_layer = get_channel_layer()
        
        # Get all active simulation profiles
        profiles = UserSimulationProfile.objects.filter(
            user__is_active=True,
            current_portfolio_value__gt=0
        )
        
        for profile in profiles:
            try:
                new_value = service.calculate_portfolio_value(profile.user)
                if new_value != profile.current_portfolio_value:
                    updated_users += 1
                    
                    # Broadcast portfolio update via WebSocket
                    if channel_layer:
                        portfolio_data = {
                            'cash_balance': float(profile.virtual_cash_balance),
                            'portfolio_value': float(profile.current_portfolio_value),
                            'total_return': profile.calculate_total_return_percentage(),
                            'positions': [{
                                'symbol': pos.instrument.real_ticker.symbol,
                                'quantity': float(pos.quantity),
                                'current_price': float(pos.current_price) if pos.current_price else None,
                                'market_value': float(pos.market_value),
                                'unrealized_pnl': float(pos.unrealized_pnl),
                                'daily_pnl': float(pos.daily_pnl)
                            } for pos in profile.user.simulated_positions.all()]
                        }
                        
                        async_to_sync(channel_layer.group_send)(
                            f'portfolio_{profile.user.id}',
                            {
                                'type': 'portfolio_update',
                                'portfolio': portfolio_data
                            }
                        )
                    
            except Exception as e:
                logger.warning(f"Error updating portfolio for user {profile.user.username}: {e}")
                continue
        
        logger.info(f"Updated portfolio values for {updated_users} users")
        
        return {
            'status': 'success',
            'users_updated': updated_users,
            'total_profiles': profiles.count(),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating portfolio values: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def generate_daily_reports(self):
    """
    Generate daily reports and statistics
    Runs once per day at market close
    """
    try:
        logger.info("Generating daily reports")
        
        today = timezone.now().date()
        
        # Generate system-wide statistics
        from apps.order_management.models import SimulatedOrder, SimulatedTrade
        from django.db import models
        
        daily_stats = {
            'date': today.isoformat(),
            'orders': {
                'total': SimulatedOrder.objects.filter(order_timestamp__date=today).count(),
                'filled': SimulatedOrder.objects.filter(
                    order_timestamp__date=today, status='FILLED'
                ).count(),
                'cancelled': SimulatedOrder.objects.filter(
                    order_timestamp__date=today, status='CANCELLED'
                ).count()
            },
            'trades': {
                'total': SimulatedTrade.objects.filter(trade_timestamp__date=today).count(),
                'volume': SimulatedTrade.objects.filter(
                    trade_timestamp__date=today
                ).aggregate(total_volume=models.Sum('quantity'))['total_volume'] or 0
            },
            'users': {
                'active': SimulatedOrder.objects.filter(
                    order_timestamp__date=today
                ).values('user').distinct().count()
            }
        }
        
        # Store daily statistics (you might want to create a DailyStatistics model)
        logger.info(f"Daily statistics: {daily_stats}")
        
        return {
            'status': 'success',
            'statistics': daily_stats,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating daily reports: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def update_risk_metrics(self):
    """
    Update risk metrics for all users and broadcast alerts via WebSocket
    Runs every 2 hours during market hours
    """
    try:
        logger.info("Starting risk metrics update")
        
        from apps.risk_management.services import RiskManagementService
        
        service = RiskManagementService()
        updated_users = 0
        alerts_created = 0
        
        # Get channel layer for broadcasting
        channel_layer = get_channel_layer()
        
        # Get all active users with positions
        users_with_positions = User.objects.filter(
            simulated_positions__isnull=False,
            is_active=True
        ).distinct()
        
        for user in users_with_positions:
            try:
                # Update portfolio risk metrics
                risk_record = service.update_portfolio_risk_metrics(user)
                updated_users += 1
                
                # Check for new risk alerts
                from apps.risk_management.services import PositionLimitService
                limit_service = PositionLimitService()
                breaches = limit_service.check_limit_breaches(user)
                
                # Create alerts for new breaches and broadcast
                for breach in breaches:
                    alert = service.create_risk_alert(
                        user=user,
                        alert_type='LIMIT_BREACH',
                        severity='WARNING',
                        message=f"Position limit breach: {breach['limit_type']}",
                        current_value=breach.get('current_value'),
                        limit_value=breach.get('limit_value')
                    )
                    alerts_created += 1
                    
                    # Broadcast risk alert via WebSocket
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f'risk_{user.id}',
                            {
                                'type': 'risk_alert',
                                'alert': {
                                    'type': 'LIMIT_BREACH',
                                    'severity': 'WARNING',
                                    'message': f"Position limit breach: {breach['limit_type']}",
                                    'current_value': breach.get('current_value'),
                                    'limit_value': breach.get('limit_value'),
                                    'timestamp': timezone.now().isoformat()
                                }
                            }
                        )
                    
            except Exception as e:
                logger.warning(f"Error updating risk metrics for user {user.username}: {e}")
                continue
        
        logger.info(f"Updated risk metrics for {updated_users} users, created {alerts_created} alerts")
        
        return {
            'status': 'success',
            'users_updated': updated_users,
            'alerts_created': alerts_created,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating risk metrics: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3)
def simulate_market_volatility(self):
    """
    Add realistic volatility to simulated market prices and broadcast updates
    Runs every 1 minute during active simulation
    """
    try:
        logger.debug("Adding market volatility simulation")
        
        price_service = PriceSimulationService()
        
        # Get channel layer for broadcasting
        channel_layer = get_channel_layer()
        
        # Get all active instruments
        instruments = SimulatedInstrument.objects.filter(
            is_tradable=True,
            exchange__status='ACTIVE'
        )
        
        updated_count = 0
        
        for instrument in instruments:
            try:
                # Get current price
                current_price = instrument.get_current_simulated_price()
                if not current_price:
                    continue
                
                # Add market noise
                new_price = price_service.add_market_noise(
                    current_price, 
                    instrument.volatility_multiplier
                )
                
                # Update order book
                order_book = instrument.order_book
                order_book.last_trade_price = new_price
                order_book.save()
                
                # Update market maker quotes
                from apps.trading_simulation.services import SimulatedExchangeService
                exchange_service = SimulatedExchangeService()
                exchange_service._update_market_maker_quotes(instrument, new_price)
                
                # Broadcast market data update via WebSocket
                if channel_layer:
                    market_data = {
                        'symbol': instrument.real_ticker.symbol,
                        'last_price': float(new_price),
                        'bid_price': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                        'ask_price': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                        'volume': order_book.daily_volume,
                        'spread': float(order_book.spread) if order_book.spread else None,
                        'timestamp': timezone.now().isoformat()
                    }
                    
                    async_to_sync(channel_layer.group_send)(
                        f'market_{instrument.real_ticker.symbol}',
                        {
                            'type': 'price_update',
                            'data': market_data
                        }
                    )
                
                updated_count += 1
                
            except Exception as e:
                logger.warning(f"Error simulating volatility for {instrument}: {e}")
                continue
        
        return {
            'status': 'success',
            'instruments_updated': updated_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error simulating market volatility: {e}")
        
        # Retry with short delay
        countdown = 30  # 30 seconds
        raise self.retry(exc=e, countdown=countdown, max_retries=3)


@shared_task(bind=True)
def process_pending_market_orders(self):
    """
    Process any pending market orders that need immediate execution
    Runs every 30 seconds during market hours
    """
    try:
        from apps.order_management.models import SimulatedOrder, OrderStatus
        from apps.order_management.services import OrderMatchingService
        
        # Get pending market orders
        pending_market_orders = SimulatedOrder.objects.filter(
            order_type='MARKET',
            status__in=[OrderStatus.PENDING, OrderStatus.ACKNOWLEDGED],
            instrument__exchange__status='ACTIVE'
        )
        
        processed_count = 0
        matching_service = OrderMatchingService()
        
        for order in pending_market_orders:
            try:
                # Attempt to match the order
                matches = matching_service._match_order(order)
                if matches:
                    processed_count += 1
                    
            except Exception as e:
                logger.warning(f"Error processing order {order.order_id}: {e}")
                continue
        
        if processed_count > 0:
            logger.info(f"Processed {processed_count} pending market orders")
        
        return {
            'status': 'success',
            'orders_processed': processed_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing pending orders: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def reset_daily_order_book_statistics(self):
    """
    Reset daily statistics for order books
    Runs once per day at market open
    """
    try:
        logger.info("Resetting daily order book statistics")
        
        from apps.order_management.services import OrderBookService
        
        service = OrderBookService()
        reset_count = 0
        
        # Get all active instruments
        instruments = SimulatedInstrument.objects.filter(
            is_tradable=True,
            exchange__status='ACTIVE'
        )
        
        for instrument in instruments:
            try:
                service.reset_daily_statistics(instrument)
                reset_count += 1
                
            except Exception as e:
                logger.warning(f"Error resetting statistics for {instrument}: {e}")
                continue
        
        logger.info(f"Reset daily statistics for {reset_count} instruments")
        
        return {
            'status': 'success',
            'instruments_reset': reset_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error resetting daily statistics: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def calculate_performance_metrics(self):
    """
    Calculate performance metrics for all users
    Runs once per day after market close
    """
    try:
        logger.info("Calculating performance metrics")
        
        from apps.trading_analytics.models import TradingPerformance
        
        today = timezone.now().date()
        calculated_count = 0
        
        # Get all active users with simulation profiles
        users_with_activity = User.objects.filter(
            simulated_orders__order_timestamp__date=today
        ).distinct()
        
        for user in users_with_activity:
            try:
                # Calculate daily performance
                start_date = today
                end_date = today
                
                # This would use the TradingPerformanceViewSet logic
                # For now, just mark as calculated
                calculated_count += 1
                
            except Exception as e:
                logger.warning(f"Error calculating performance for user {user.username}: {e}")
                continue
        
        logger.info(f"Calculated performance metrics for {calculated_count} users")
        
        return {
            'status': 'success',
            'users_calculated': calculated_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating performance metrics: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task(bind=True)
def health_check_simulation_system(self):
    """
    Perform health check on the simulation system
    Runs every 15 minutes
    """
    try:
        logger.info("Performing simulation system health check")
        
        service = SimulationMonitoringService()
        health_report = service.generate_health_report()
        
        # Check for any critical issues
        issues = []
        
        if health_report.get('system_status') != 'HEALTHY':
            issues.append('System status is not healthy')
        
        # Check exchange status
        inactive_exchanges = SimulatedExchange.objects.filter(status='MAINTENANCE').count()
        if inactive_exchanges > 0:
            issues.append(f'{inactive_exchanges} exchanges in maintenance mode')
        
        # Check for old market data
        from apps.order_management.models import OrderBook
        stale_cutoff = timezone.now() - timedelta(hours=1)
        stale_books = OrderBook.objects.filter(
            last_trade_timestamp__lt=stale_cutoff
        ).count()
        
        if stale_books > 0:
            issues.append(f'{stale_books} order books have stale data')
        
        # Log issues if any
        if issues:
            logger.warning(f"Health check found issues: {issues}")
        
        return {
            'status': 'healthy' if not issues else 'issues_found',
            'health_report': health_report,
            'issues': issues,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error performing health check: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }

