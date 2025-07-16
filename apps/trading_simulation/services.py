# apps/trading_simulation/services.py
"""
SIMULATED Trading Engine Services
================================
Core business logic for VIRTUAL trading simulation.
Uses REAL market data but all trading is PAPER TRADING.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.market_data.models import MarketData, Ticker
from .models import (
    SimulatedExchange, SimulatedInstrument, TradingSession, 
    MarketMaker, UserSimulationProfile, SimulationScenario
)
from apps.order_management.models import (
    SimulatedOrder, OrderBook, OrderBookLevel, MatchingEngine
)
from apps.risk_management.models import (
    PositionLimit, SimulatedPosition, ComplianceRule
)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class SimulatedExchangeService:
    """
    Service for managing SIMULATED exchanges and instruments
    Creates virtual trading environments using real market data
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_simulated_exchange(self, real_exchange, **kwargs) -> SimulatedExchange:
        """Create a simulated exchange based on a real exchange"""
        try:
            sim_exchange = SimulatedExchange.objects.create(
                name=f"Simulated {real_exchange.name}",
                code=f"SIM_{real_exchange.code}",
                real_exchange=real_exchange,
                **kwargs
            )
            
            # Create matching engine for the exchange
            MatchingEngine.objects.create(
                exchange=sim_exchange,
                matching_algorithm='PRICE_TIME'
            )
            
            self.logger.info(f"Created simulated exchange: {sim_exchange.code}")
            return sim_exchange
            
        except Exception as e:
            self.logger.error(f"Error creating simulated exchange: {e}")
            raise
    
    def add_instrument_to_exchange(self, sim_exchange: SimulatedExchange, 
                                 real_ticker: Ticker, **kwargs) -> SimulatedInstrument:
        """Add a real ticker as a simulated instrument to the exchange"""
        try:
            sim_instrument = SimulatedInstrument.objects.create(
                real_ticker=real_ticker,
                exchange=sim_exchange,
                **kwargs
            )
            
            # Create order book for the instrument
            OrderBook.objects.create(instrument=sim_instrument)
            
            # Initialize market data if available
            self._initialize_instrument_pricing(sim_instrument)
            
            self.logger.info(f"Added instrument {real_ticker.symbol} to {sim_exchange.code}")
            return sim_instrument
            
        except Exception as e:
            self.logger.error(f"Error adding instrument {real_ticker.symbol}: {e}")
            raise
    
    def _initialize_instrument_pricing(self, sim_instrument: SimulatedInstrument):
        """Initialize order book with current market data"""
        try:
            # Get latest real market data
            latest_data = sim_instrument.real_ticker.market_data.first()
            if not latest_data:
                self.logger.warning(f"No market data for {sim_instrument.real_ticker.symbol}")
                return
            
            # Apply simulation multipliers
            simulated_price = latest_data.close * sim_instrument.price_multiplier
            
            # Update order book with current price
            order_book = sim_instrument.order_book
            order_book.last_trade_price = simulated_price
            order_book.opening_price = simulated_price
            order_book.save()
            
            # Add some initial market maker quotes
            self._add_initial_quotes(sim_instrument, simulated_price)
            
        except Exception as e:
            self.logger.error(f"Error initializing pricing for {sim_instrument}: {e}")
    
    def _add_initial_quotes(self, sim_instrument: SimulatedInstrument, 
                          current_price: Decimal):
        """Add initial market maker quotes to the order book"""
        try:
            order_book = sim_instrument.order_book
            
            # Calculate bid/ask spread (default 10 bps)
            spread_bps = 10
            spread = current_price * Decimal(str(spread_bps / 10000))
            
            bid_price = current_price - (spread / 2)
            ask_price = current_price + (spread / 2)
            
            # Update order book best bid/offer
            order_book.best_bid_price = bid_price
            order_book.best_bid_quantity = 100
            order_book.best_ask_price = ask_price
            order_book.best_ask_quantity = 100
            order_book.save()
            
            # Add order book levels
            OrderBookLevel.objects.bulk_create([
                OrderBookLevel(
                    order_book=order_book,
                    side='BUY',
                    price=bid_price,
                    quantity=100
                ),
                OrderBookLevel(
                    order_book=order_book,
                    side='SELL',
                    price=ask_price,
                    quantity=100
                )
            ])
            
        except Exception as e:
            self.logger.error(f"Error adding initial quotes: {e}")
    
    def create_trading_session(self, exchange: SimulatedExchange, 
                             session_type: str = 'CONTINUOUS',
                             duration_hours: int = 8) -> TradingSession:
        """Create a new trading session"""
        try:
            start_time = timezone.now()
            end_time = start_time + timedelta(hours=duration_hours)
            
            session = TradingSession.objects.create(
                exchange=exchange,
                session_type=session_type,
                start_time=start_time,
                end_time=end_time
            )
            
            self.logger.info(f"Created trading session for {exchange.code}")
            return session
            
        except Exception as e:
            self.logger.error(f"Error creating trading session: {e}")
            raise
    
    def update_market_data(self, sim_instrument: SimulatedInstrument):
        """Update simulated instrument pricing with latest real market data"""
        try:
            # Get latest real market data
            latest_data = sim_instrument.real_ticker.market_data.first()
            if not latest_data:
                return
            
            # Apply simulation adjustments
            simulated_price = latest_data.close * sim_instrument.price_multiplier
            
            # Update order book
            order_book = sim_instrument.order_book
            old_price = order_book.last_trade_price or simulated_price
            
            # Calculate price change for market making
            price_change = simulated_price - old_price if old_price else Decimal('0')
            
            # Update order book prices
            order_book.last_trade_price = simulated_price
            
            # Update daily high/low
            if not order_book.daily_high or simulated_price > order_book.daily_high:
                order_book.daily_high = simulated_price
            if not order_book.daily_low or simulated_price < order_book.daily_low:
                order_book.daily_low = simulated_price
            
            order_book.save()
            
            # Update market maker quotes
            self._update_market_maker_quotes(sim_instrument, simulated_price)
            
            self.logger.debug(f"Updated pricing for {sim_instrument.real_ticker.symbol}: {simulated_price}")
            
        except Exception as e:
            self.logger.error(f"Error updating market data for {sim_instrument}: {e}")
    
    def _update_market_maker_quotes(self, sim_instrument: SimulatedInstrument, 
                                  current_price: Decimal):
        """Update market maker quotes based on new price"""
        try:
            order_book = sim_instrument.order_book
            
            # Get market makers for this exchange
            market_makers = sim_instrument.exchange.market_makers.filter(is_active=True)
            
            for mm in market_makers:
                # Calculate spread based on market maker algorithm
                spread_bps = mm.default_spread_bps
                spread = current_price * Decimal(str(spread_bps / 10000))
                
                # Update quotes
                bid_price = current_price - (spread / 2)
                ask_price = current_price + (spread / 2)
                
                # Update order book best quotes
                if not order_book.best_bid_price or bid_price > order_book.best_bid_price:
                    order_book.best_bid_price = bid_price
                    order_book.best_bid_quantity = mm.quote_size
                
                if not order_book.best_ask_price or ask_price < order_book.best_ask_price:
                    order_book.best_ask_price = ask_price
                    order_book.best_ask_quantity = mm.quote_size
            
            order_book.save()
            
        except Exception as e:
            self.logger.error(f"Error updating market maker quotes: {e}")

    def broadcast_order_update(self, order):
        """Broadcast order updates to WebSocket clients"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'orders_{order.user.id}',
                    {
                        'type': 'order_update',
                        'order': {
                            'order_id': str(order.order_id),
                            'symbol': order.instrument.real_ticker.symbol,
                            'side': order.side,
                            'quantity': order.quantity,
                            'price': float(order.price) if order.price else None,
                            'status': order.status,
                            'filled_quantity': order.filled_quantity,
                            'timestamp': order.order_timestamp.isoformat()
                        }
                    }
                )
        except Exception as e:
            self.logger.error(f"Error broadcasting order update: {e}")

    def broadcast_portfolio_update(self, user):
        """Broadcast portfolio updates to WebSocket clients"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                profile = user.simulation_profile
                positions = user.simulated_positions.all()

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
                    } for pos in positions]
                }

                async_to_sync(channel_layer.group_send)(
                    f'portfolio_{user.id}',
                    {
                        'type': 'portfolio_update',
                        'portfolio': portfolio_data
                    }
                )
        except Exception as e:
            self.logger.error(f"Error broadcasting portfolio update: {e}")

    def broadcast_market_data_update(self, instrument):
        """Broadcast market data updates to WebSocket clients"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                order_book = instrument.order_book

                market_data = {
                    'symbol': instrument.real_ticker.symbol,
                    'last_price': float(order_book.last_trade_price) if order_book.last_trade_price else None,
                    'bid_price': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                    'ask_price': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                    'volume': order_book.daily_volume,
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
            self.logger.error(f"Error broadcasting market data update: {e}")


class MarketSimulationService:
    """
    Service for applying market scenarios and simulations
    Modifies real market data to create different market conditions
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def apply_scenario(self, exchange: SimulatedExchange, 
                      scenario: SimulationScenario):
        """Apply a market scenario to all instruments in an exchange"""
        try:
            instruments = exchange.instruments.all()
            
            for instrument in instruments:
                self._apply_scenario_to_instrument(instrument, scenario)
            
            self.logger.info(f"Applied scenario '{scenario.name}' to {exchange.code}")
            
        except Exception as e:
            self.logger.error(f"Error applying scenario: {e}")
            raise
    
    def _apply_scenario_to_instrument(self, instrument: SimulatedInstrument,
                                    scenario: SimulationScenario):
        """Apply scenario effects to a specific instrument"""
        try:
            # Adjust price multiplier based on scenario
            if scenario.scenario_type == 'VOLATILE':
                instrument.volatility_multiplier = scenario.volatility_factor
            elif scenario.scenario_type == 'CRASH':
                # Apply immediate price drop
                instrument.price_multiplier = Decimal('0.8')  # 20% drop
            elif scenario.scenario_type == 'RECOVERY':
                # Apply gradual price recovery
                instrument.price_multiplier = Decimal('1.1')  # 10% boost
            
            instrument.save()
            
            # Update market data with new scenario
            self._update_scenario_pricing(instrument, scenario)
            
        except Exception as e:
            self.logger.error(f"Error applying scenario to {instrument}: {e}")
    
    def _update_scenario_pricing(self, instrument: SimulatedInstrument,
                               scenario: SimulationScenario):
        """Update pricing based on scenario parameters"""
        try:
            order_book = instrument.order_book
            current_price = order_book.last_trade_price
            
            if not current_price:
                return
            
            # Apply daily drift
            drift = scenario.daily_drift_percentage / 100
            new_price = current_price * (1 + drift)
            
            # Apply volatility adjustment
            volatility_adj = scenario.volatility_factor
            
            # Update order book
            order_book.last_trade_price = new_price
            order_book.save()
            
            # Recalculate market maker quotes
            exchange_service = SimulatedExchangeService()
            exchange_service._update_market_maker_quotes(instrument, new_price)
            
        except Exception as e:
            self.logger.error(f"Error updating scenario pricing: {e}")


class UserTradingService:
    """
    Service for managing user simulation profiles and preferences
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def initialize_user_profile(self, user, 
                              initial_balance: Decimal = Decimal('100000.00'),
                              **kwargs) -> UserSimulationProfile:
        """Initialize a user's simulation profile"""
        try:
            profile, created = UserSimulationProfile.objects.get_or_create(
                user=user,
                defaults={
                    'virtual_cash_balance': initial_balance,
                    'initial_virtual_balance': initial_balance,
                    'current_portfolio_value': initial_balance,
                    **kwargs
                }
            )
            
            if created:
                self.logger.info(f"Created simulation profile for {user.username}")
            
            return profile
            
        except Exception as e:
            self.logger.error(f"Error initializing user profile for {user.username}: {e}")
            raise
    
    def reset_user_simulation(self, user, 
                            new_balance: Decimal = Decimal('100000.00')) -> UserSimulationProfile:
        """Reset user's simulation to start fresh"""
        try:
            with transaction.atomic():
                # Get or create profile
                profile = self.initialize_user_profile(user, new_balance)
                
                # Reset financial values
                profile.virtual_cash_balance = new_balance
                profile.initial_virtual_balance = new_balance
                profile.current_portfolio_value = new_balance
                profile.total_trades_executed = 0
                profile.profitable_trades = 0
                profile.save()
                
                # Clear existing positions
                user.simulated_positions.all().delete()
                
                # Cancel pending orders
                user.simulated_orders.filter(
                    status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
                ).update(status='CANCELLED')
                
                self.logger.info(f"Reset simulation for {user.username}")
                return profile
                
        except Exception as e:
            self.logger.error(f"Error resetting simulation for {user.username}: {e}")
            raise
    
    def calculate_portfolio_value(self, user) -> Decimal:
        """Calculate current total portfolio value"""
        try:
            profile = user.simulation_profile
            total_value = profile.virtual_cash_balance
            
            # Add value of all positions
            positions = user.simulated_positions.all()
            for position in positions:
                if position.current_price:
                    position_value = position.quantity * position.current_price
                    total_value += position_value
            
            # Update profile
            profile.current_portfolio_value = total_value
            profile.save()
            
            return total_value
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio value for {user.username}: {e}")
            return Decimal('0.00')
    
    def get_user_statistics(self, user) -> Dict:
        """Get comprehensive user trading statistics"""
        try:
            profile = user.simulation_profile
            
            # Calculate returns
            total_return = profile.calculate_total_return_percentage()
            win_rate = profile.get_win_rate()
            
            # Get position summary
            positions = user.simulated_positions.all()
            total_positions = positions.count()
            long_positions = positions.filter(quantity__gt=0).count()
            short_positions = positions.filter(quantity__lt=0).count()
            
            # Calculate unrealized P&L
            total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
            
            return {
                'total_return_percentage': total_return,
                'win_rate_percentage': win_rate,
                'total_trades': profile.total_trades_executed,
                'profitable_trades': profile.profitable_trades,
                'current_portfolio_value': float(profile.current_portfolio_value),
                'cash_balance': float(profile.virtual_cash_balance),
                'total_positions': total_positions,
                'long_positions': long_positions,
                'short_positions': short_positions,
                'total_unrealized_pnl': float(total_unrealized_pnl),
            }
            
        except Exception as e:
            self.logger.error(f"Error getting statistics for {user.username}: {e}")
            return {}


class PriceSimulationService:
    """
    Service for simulating realistic price movements
    Adds randomness and market behavior to real market data
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def simulate_intraday_prices(self, instrument: SimulatedInstrument,
                               minutes: int = 60) -> List[Dict]:
        """Generate simulated intraday price movements"""
        try:
            import random
            import math
            
            # Get current price
            current_price = instrument.get_current_simulated_price()
            if not current_price:
                return []
            
            prices = []
            price = float(current_price)
            
            # Parameters for price simulation
            annual_volatility = 0.25 * float(instrument.volatility_multiplier)
            dt = 1 / (252 * 24 * 60)  # One minute in years
            vol_per_minute = annual_volatility * math.sqrt(dt)
            
            for minute in range(minutes):
                # Random walk with drift
                random_shock = random.gauss(0, vol_per_minute)
                price_change = price * random_shock
                price += price_change
                
                # Ensure price doesn't go negative
                price = max(price, float(current_price) * 0.5)
                
                timestamp = timezone.now() + timedelta(minutes=minute)
                
                prices.append({
                    'timestamp': timestamp,
                    'price': Decimal(str(round(price, 2))),
                    'volume': random.randint(100, 1000)
                })
            
            return prices
            
        except Exception as e:
            self.logger.error(f"Error simulating prices for {instrument}: {e}")
            return []
    
    def add_market_noise(self, base_price: Decimal, 
                        volatility_factor: Decimal = Decimal('1.0')) -> Decimal:
        """Add realistic market noise to a base price"""
        try:
            import random
            
            # Add small random movements (0.01% to 0.1%)
            noise_percentage = random.uniform(-0.001, 0.001) * float(volatility_factor)
            noise = base_price * Decimal(str(noise_percentage))
            
            return base_price + noise
            
        except Exception as e:
            self.logger.error(f"Error adding market noise: {e}")
            return base_price


class SimulationMonitoringService:
    """
    Service for monitoring and maintaining simulation health
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def update_all_market_data(self):
        """Update market data for all active simulated instruments"""
        try:
            exchanges = SimulatedExchange.objects.filter(
                status='ACTIVE'
            )
            
            exchange_service = SimulatedExchangeService()
            
            for exchange in exchanges:
                instruments = exchange.instruments.filter(is_tradable=True)
                
                for instrument in instruments:
                    exchange_service.update_market_data(instrument)
            
            self.logger.info("Updated market data for all instruments")
            
        except Exception as e:
            self.logger.error(f"Error updating all market data: {e}")
    
    def cleanup_expired_orders(self):
        """Clean up expired and cancelled orders"""
        try:
            from apps.order_management.models import SimulatedOrder
            
            # Find day orders that should expire
            cutoff_time = timezone.now() - timedelta(hours=16)  # Market close
            
            expired_orders = SimulatedOrder.objects.filter(
                time_in_force='DAY',
                status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED'],
                order_timestamp__lt=cutoff_time
            )
            
            count = expired_orders.update(status='EXPIRED')
            
            if count > 0:
                self.logger.info(f"Expired {count} day orders")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up expired orders: {e}")
    
    def generate_health_report(self) -> Dict:
        """Generate a health report for the simulation system"""
        try:
            from apps.order_management.models import SimulatedOrder, SimulatedTrade
            
            # Count active components
            active_exchanges = SimulatedExchange.objects.filter(status='ACTIVE').count()
            total_instruments = SimulatedInstrument.objects.filter(is_tradable=True).count()
            active_users = UserSimulationProfile.objects.count()
            
            # Trading activity
            today = timezone.now().date()
            today_orders = SimulatedOrder.objects.filter(
                order_timestamp__date=today
            ).count()
            today_trades = SimulatedTrade.objects.filter(
                trade_timestamp__date=today
            ).count()
            
            return {
                'timestamp': timezone.now(),
                'active_exchanges': active_exchanges,
                'total_instruments': total_instruments,
                'active_users': active_users,
                'orders_today': today_orders,
                'trades_today': today_trades,
                'system_status': 'HEALTHY'
            }
            
        except Exception as e:
            self.logger.error(f"Error generating health report: {e}")
            return {'system_status': 'ERROR', 'error': str(e)}
