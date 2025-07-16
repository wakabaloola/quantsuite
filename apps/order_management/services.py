# apps/order_management/services.py
"""
SIMULATED Order Matching Engine
==============================
Handles VIRTUAL order matching, execution, and trade generation.
All matching is for PAPER TRADING - no real money involved.
"""

import logging
from typing import List, Optional, Tuple, Dict
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import (
    SimulatedOrder, SimulatedTrade, OrderBook, OrderBookLevel, 
    Fill, MatchingEngine, OrderStatus, OrderSide
)
from apps.trading_simulation.models import SimulatedInstrument
from apps.risk_management.models import SimulatedPosition
from apps.risk_management.services import RiskManagementService
from apps.trading_simulation.services import SimulatedExchangeService
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class OrderMatchingService:
    """
    SIMULATED Order Matching Engine
    Matches virtual orders and creates simulated trades
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.risk_service = RiskManagementService()
    
    def submit_order(self, order: SimulatedOrder) -> Tuple[bool, str, List[str]]:
        """
        Submit a SIMULATED order for processing
        Returns: (success, message, violations)
        """
        try:
            with transaction.atomic():
                # Pre-trade risk checks
                risk_result = self.risk_service.validate_order(order)
                if not risk_result['approved']:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = '; '.join(risk_result['violations'])
                    order.save()
                    
                    # Broadcast order rejection
                    self.broadcast_order_update(order)
                    
                    return False, "Order rejected by risk management", risk_result['violations']
                
                # Mark order as risk checked
                order.risk_checked = True
                order.compliance_checked = True
                order.status = OrderStatus.SUBMITTED
                order.submission_timestamp = timezone.now()
                order.save()
                
                # Broadcast order submission
                self.broadcast_order_update(order)
                
                # Attempt to match order
                matches = self._match_order(order)
                
                if matches:
                    self.logger.info(f"Order {order.order_id} matched with {len(matches)} counterparts")
                    # Note: Order status updates and broadcasts are handled in _execute_trade method
                else:
                    # No immediate matches - add to order book
                    self._add_to_order_book(order)
                    order.status = OrderStatus.ACKNOWLEDGED
                    order.acknowledgment_timestamp = timezone.now()
                    order.save()
                    
                    # Broadcast order acknowledgment
                    self.broadcast_order_update(order)
                
                return True, "Order submitted successfully", []
                
        except Exception as e:
            self.logger.error(f"Error submitting order {order.order_id}: {e}")
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(e)
            order.save()
            
            # Broadcast order rejection due to error
            self.broadcast_order_update(order)
            
            return False, str(e), []
    
    def _match_order(self, incoming_order: SimulatedOrder) -> List[Dict]:
        """
        Match incoming order against existing orders in the book
        Returns list of match details
        """
        try:
            matches = []
            remaining_quantity = incoming_order.quantity
            
            # Get order book for the instrument
            order_book = incoming_order.instrument.order_book
            
            # Find potential matches based on order type
            if incoming_order.order_type == 'MARKET':
                # Market orders match at any price
                matches = self._match_market_order(incoming_order, remaining_quantity)
            elif incoming_order.order_type == 'LIMIT':
                # Limit orders match at specified price or better
                matches = self._match_limit_order(incoming_order, remaining_quantity)
            
            # Process all matches
            for match in matches:
                self._execute_trade(incoming_order, match)
                remaining_quantity -= match['quantity']
                
                if remaining_quantity <= 0:
                    break
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error matching order {incoming_order.order_id}: {e}")
            return []
    
    def _match_market_order(self, order: SimulatedOrder, quantity: int) -> List[Dict]:
        """Match a market order against the best available prices"""
        try:
            matches = []
            order_book = order.instrument.order_book
            
            if order.side == OrderSide.BUY:
                # Buy market order matches against best ask
                if order_book.best_ask_price and order_book.best_ask_quantity > 0:
                    match_quantity = min(quantity, order_book.best_ask_quantity)
                    matches.append({
                        'price': order_book.best_ask_price,
                        'quantity': match_quantity,
                        'counterpart_type': 'market_maker'
                    })
            else:
                # Sell market order matches against best bid
                if order_book.best_bid_price and order_book.best_bid_quantity > 0:
                    match_quantity = min(quantity, order_book.best_bid_quantity)
                    matches.append({
                        'price': order_book.best_bid_price,
                        'quantity': match_quantity,
                        'counterpart_type': 'market_maker'
                    })
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error matching market order: {e}")
            return []
    
    def _match_limit_order(self, order: SimulatedOrder, quantity: int) -> List[Dict]:
        """Match a limit order if price conditions are met"""
        try:
            matches = []
            order_book = order.instrument.order_book
            
            if order.side == OrderSide.BUY:
                # Buy limit order matches if bid price >= ask price
                if (order_book.best_ask_price and 
                    order.price >= order_book.best_ask_price):
                    match_quantity = min(quantity, order_book.best_ask_quantity)
                    matches.append({
                        'price': order_book.best_ask_price,  # Price improvement
                        'quantity': match_quantity,
                        'counterpart_type': 'market_maker'
                    })
            else:
                # Sell limit order matches if ask price <= bid price
                if (order_book.best_bid_price and 
                    order.price <= order_book.best_bid_price):
                    match_quantity = min(quantity, order_book.best_bid_quantity)
                    matches.append({
                        'price': order_book.best_bid_price,  # Price improvement
                        'quantity': match_quantity,
                        'counterpart_type': 'market_maker'
                    })
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error matching limit order: {e}")
            return []

        
    def _execute_trade(self, order: SimulatedOrder, match: Dict):
        """Execute a trade between matched orders"""
        try:
            with transaction.atomic():
                # Create simulated counterpart order (market maker)
                counterpart_order = self._create_counterpart_order(order, match)
                
                # Create the trade
                trade = SimulatedTrade.objects.create(
                    exchange=order.exchange,
                    instrument=order.instrument,
                    buy_order=order if order.side == OrderSide.BUY else counterpart_order,
                    sell_order=counterpart_order if order.side == OrderSide.BUY else order,
                    quantity=match['quantity'],
                    price=match['price'],
                    is_aggressive=True  # Incoming order is aggressive
                )
                
                # Calculate fees
                fee_rate = order.exchange.trading_fee_percentage
                trade_value = match['quantity'] * match['price']
                fees = trade_value * fee_rate
                
                # Create fills for both orders
                self._create_fill(order, trade, match['quantity'], match['price'], fees)
                self._create_fill(counterpart_order, trade, match['quantity'], match['price'], fees)
                
                # Update order status
                order.filled_quantity += match['quantity']
                if order.filled_quantity >= order.quantity:
                    order.status = OrderStatus.FILLED
                    order.completion_timestamp = timezone.now()
                else:
                    order.status = OrderStatus.PARTIALLY_FILLED
                
                if not order.first_fill_timestamp:
                    order.first_fill_timestamp = timezone.now()
                order.last_fill_timestamp = timezone.now()
                order.save()
                
                # Broadcast order update via WebSocket
                self.broadcast_order_update(order)
                
                # Update positions
                self._update_position(order.user, order.instrument, 
                                    match['quantity'], match['price'], order.side)
                
                # Broadcast portfolio update via WebSocket (only for non-system users)
                if order.user.username != 'system_market_maker':
                    self.broadcast_portfolio_update(order.user)
                
                # Update order book
                self._update_order_book_after_trade(order.instrument, trade)
                
                # Broadcast trade notification via WebSocket
                self.broadcast_trade_notification(trade)
                
                # Broadcast market data update via WebSocket
                from apps.order_management.services import OrderBookService
                book_service = OrderBookService()
                book_service.broadcast_market_data_update(order.instrument)
                
                self.logger.info(f"Executed trade: {match['quantity']}@{match['price']} for {order.order_id}")
                
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
            raise
    

    def _create_counterpart_order(self, original_order: SimulatedOrder, 
                                 match: Dict) -> SimulatedOrder:
        """Create a simulated market maker counterpart order"""
        try:
            counterpart_side = OrderSide.SELL if original_order.side == OrderSide.BUY else OrderSide.BUY
            
            # Create a system user for market makers if needed
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            market_maker_user, _ = User.objects.get_or_create(
                username='system_market_maker',
                defaults={
                    'email': 'mm@simulation.local',
                    'first_name': 'Market',
                    'last_name': 'Maker'
                }
            )
            
            counterpart_order = SimulatedOrder.objects.create(
                user=market_maker_user,
                exchange=original_order.exchange,
                instrument=original_order.instrument,
                side=counterpart_side,
                order_type='LIMIT',
                quantity=match['quantity'],
                price=match['price'],
                status=OrderStatus.FILLED,
                filled_quantity=match['quantity'],
                client_order_id=f"MM_{original_order.order_id}"
            )
            
            return counterpart_order
            
        except Exception as e:
            self.logger.error(f"Error creating counterpart order: {e}")
            raise
    
    def _create_fill(self, order: SimulatedOrder, trade: SimulatedTrade,
                    quantity: int, price: Decimal, fees: Decimal):
        """Create a fill record for an order"""
        try:
            Fill.objects.create(
                order=order,
                trade=trade,
                quantity=quantity,
                price=price,
                fees=fees,
                liquidity_flag='TAKER' if order.status != 'ACKNOWLEDGED' else 'MAKER'
            )
            
        except Exception as e:
            self.logger.error(f"Error creating fill: {e}")
            raise
    
    def _update_position(self, user, instrument: SimulatedInstrument,
                        quantity: int, price: Decimal, side: str):
        """Update user's position after a trade"""
        try:
            # Determine position change
            position_change = quantity if side == OrderSide.BUY else -quantity
            
            # Get or create position
            position, created = SimulatedPosition.objects.get_or_create(
                user=user,
                instrument=instrument,
                defaults={
                    'quantity': Decimal('0'),
                    'average_cost': price,
                    'total_cost': Decimal('0'),
                    'market_value': Decimal('0'),
                    'unrealized_pnl': Decimal('0'),
                    'realized_pnl': Decimal('0')
                }
            )
            
            if created or position.quantity == 0:
                # New position
                position.quantity = Decimal(str(position_change))
                position.average_cost = price
                position.total_cost = abs(position.quantity) * price
            else:
                # Existing position
                old_quantity = position.quantity
                new_quantity = old_quantity + Decimal(str(position_change))
                
                if (old_quantity > 0 and position_change > 0) or (old_quantity < 0 and position_change < 0):
                    # Adding to existing position
                    total_cost = (abs(old_quantity) * position.average_cost + 
                                abs(Decimal(str(position_change))) * price)
                    position.average_cost = total_cost / abs(new_quantity) if new_quantity != 0 else price
                    position.total_cost = abs(new_quantity) * position.average_cost
                else:
                    # Reducing or reversing position - realize P&L
                    if abs(position_change) >= abs(old_quantity):
                        # Full exit or reversal
                        realized_pnl = old_quantity * (price - position.average_cost)
                        position.realized_pnl += realized_pnl
                        
                        if abs(position_change) > abs(old_quantity):
                            # Position reversal
                            remaining = abs(position_change) - abs(old_quantity)
                            position.average_cost = price
                            position.total_cost = remaining * price
                        else:
                            # Full exit
                            position.average_cost = Decimal('0')
                            position.total_cost = Decimal('0')
                    else:
                        # Partial exit
                        exit_quantity = abs(position_change)
                        realized_pnl = exit_quantity * (price - position.average_cost)
                        if old_quantity < 0:  # Short position
                            realized_pnl = -realized_pnl
                        position.realized_pnl += realized_pnl
                
                position.quantity = new_quantity
            
            # Update current market value
            position.current_price = price
            position.market_value = position.quantity * price
            position.unrealized_pnl = position.calculate_unrealized_pnl()
            position.save()
            
            # Update user's cash balance
            user.simulation_profile.virtual_cash_balance -= (Decimal(str(position_change)) * price)
            user.simulation_profile.save()
            
        except Exception as e:
            self.logger.error(f"Error updating position: {e}")
            raise

    
    def _update_order_book_after_trade(self, instrument: SimulatedInstrument, 
                                     trade: SimulatedTrade):
        """Update order book state after a trade"""
        try:
            order_book = instrument.order_book
            
            # Update trade statistics
            order_book.last_trade_price = trade.price
            order_book.last_trade_quantity = trade.quantity
            order_book.last_trade_timestamp = trade.trade_timestamp
            order_book.daily_volume += trade.quantity
            order_book.daily_turnover += trade.notional_value
            order_book.trade_count += 1
            
            # Update daily high/low
            if not order_book.daily_high or trade.price > order_book.daily_high:
                order_book.daily_high = trade.price
            if not order_book.daily_low or trade.price < order_book.daily_low:
                order_book.daily_low = trade.price
            
            order_book.save()
            
            # Regenerate market maker quotes
            self._refresh_market_maker_quotes(instrument)
            
            # Broadcast market data update via WebSocket
            book_service = OrderBookService()
            book_service.broadcast_market_data_update(instrument)
            
        except Exception as e:
            self.logger.error(f"Error updating order book: {e}")

    
    def _refresh_market_maker_quotes(self, instrument: SimulatedInstrument):
        """Refresh market maker quotes after a trade"""
        try:
            from apps.trading_simulation.services import SimulatedExchangeService
            
            exchange_service = SimulatedExchangeService()
            current_price = instrument.order_book.last_trade_price
            
            if current_price:
                exchange_service._update_market_maker_quotes(instrument, current_price)
                
        except Exception as e:
            self.logger.error(f"Error refreshing market maker quotes: {e}")
    
    def _add_to_order_book(self, order: SimulatedOrder):
        """Add order to the order book if it doesn't match immediately"""
        try:
            # For simulation, we'll just acknowledge the order
            # In a full implementation, this would add to order book levels
            self.logger.info(f"Order {order.order_id} added to order book")
            
        except Exception as e:
            self.logger.error(f"Error adding order to book: {e}")
    
    def cancel_order(self, order: SimulatedOrder, reason: str = "User cancellation") -> bool:
        """Cancel a pending order"""
        try:
            if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, 
                              OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED]:
                order.status = OrderStatus.CANCELLED
                order.rejection_reason = reason
                order.completion_timestamp = timezone.now()
                order.save()
                self.broadcast_order_update(order)
                
                self.logger.info(f"Cancelled order {order.order_id}")
                return True
            else:
                self.logger.warning(f"Cannot cancel order {order.order_id} in status {order.status}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error cancelling order {order.order_id}: {e}")
            return False

    def broadcast_order_update(self, order: SimulatedOrder):
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
                            'remaining_quantity': order.remaining_quantity,
                            'timestamp': order.order_timestamp.isoformat()
                        }
                    }
                )
        except Exception as e:
            self.logger.error(f"Error broadcasting order update: {e}")

    def broadcast_trade_notification(self, trade: SimulatedTrade):
        """Broadcast trade notifications to relevant users"""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Notify both buy and sell order users
                for order in [trade.buy_order, trade.sell_order]:
                    if order.user.username != 'system_market_maker':  # Skip system user
                        async_to_sync(channel_layer.group_send)(
                            f'orders_{order.user.id}',
                            {
                                'type': 'order_filled',
                                'order': {
                                    'order_id': str(order.order_id),
                                    'symbol': order.instrument.real_ticker.symbol,
                                    'side': order.side,
                                    'status': order.status,
                                    'filled_quantity': order.filled_quantity
                                },
                                'fill_details': {
                                    'quantity': trade.quantity,
                                    'price': float(trade.price),
                                    'timestamp': trade.trade_timestamp.isoformat(),
                                    'trade_id': str(trade.trade_id)
                                }
                            }
                        )
        except Exception as e:
            self.logger.error(f"Error broadcasting trade notification: {e}")

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


class MarketMakerService:
    """
    Service for managing simulated market makers
    Provides artificial liquidity in the simulation
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def update_market_maker_quotes(self, instrument: SimulatedInstrument):
        """Update market maker quotes for an instrument"""
        try:
            from apps.trading_simulation.models import MarketMaker
            
            # Get active market makers for this exchange
            market_makers = MarketMaker.objects.filter(
                exchange=instrument.exchange,
                is_active=True
            )
            
            order_book = instrument.order_book
            current_price = order_book.last_trade_price
            
            if not current_price:
                return
            
            for mm in market_makers:
                self._update_quotes_for_market_maker(mm, instrument, current_price)
                
        except Exception as e:
            self.logger.error(f"Error updating market maker quotes: {e}")
    
    def _update_quotes_for_market_maker(self, market_maker, instrument, current_price):
        """Update quotes for a specific market maker"""
        try:
            # Calculate spread based on algorithm
            if market_maker.algorithm_type == 'BASIC':
                spread_bps = market_maker.default_spread_bps
            elif market_maker.algorithm_type == 'ADAPTIVE':
                # Adaptive spread based on volatility
                spread_bps = self._calculate_adaptive_spread(instrument)
            else:
                spread_bps = market_maker.default_spread_bps
            
            # Calculate bid/ask prices
            spread = current_price * Decimal(str(spread_bps / 10000))
            bid_price = current_price - (spread / 2)
            ask_price = current_price + (spread / 2)
            
            # Update order book
            order_book = instrument.order_book
            order_book.best_bid_price = bid_price
            order_book.best_bid_quantity = market_maker.quote_size
            order_book.best_ask_price = ask_price
            order_book.best_ask_quantity = market_maker.quote_size
            order_book.save()
            
        except Exception as e:
            self.logger.error(f"Error updating quotes for market maker {market_maker.name}: {e}")
    
    def _calculate_adaptive_spread(self, instrument: SimulatedInstrument) -> int:
        """Calculate adaptive spread based on market conditions"""
        try:
            # Simple adaptive logic - in practice this would be more sophisticated
            base_spread = 10  # 10 bps base
            
            # Adjust based on recent volatility (simplified)
            volatility_multiplier = float(instrument.volatility_multiplier)
            adjusted_spread = int(base_spread * volatility_multiplier)
            
            # Cap the spread
            return min(max(adjusted_spread, 5), 100)  # Between 5 and 100 bps
            
        except Exception as e:
            self.logger.error(f"Error calculating adaptive spread: {e}")
            return 10


class OrderBookService:
    """
    Service for managing order book operations
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def get_order_book_snapshot(self, instrument: SimulatedInstrument) -> Dict:
        """Get current order book snapshot"""
        try:
            order_book = instrument.order_book
            
            snapshot = {
                'instrument': instrument.real_ticker.symbol,
                'timestamp': timezone.now(),
                'last_trade': {
                    'price': float(order_book.last_trade_price) if order_book.last_trade_price else None,
                    'quantity': order_book.last_trade_quantity,
                    'timestamp': order_book.last_trade_timestamp
                },
                'best_bid': {
                    'price': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                    'quantity': order_book.best_bid_quantity
                },
                'best_ask': {
                    'price': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                    'quantity': order_book.best_ask_quantity
                },
                'spread': {
                    'absolute': float(order_book.spread) if order_book.spread else None,
                    'basis_points': order_book.spread_bps
                },
                'daily_stats': {
                    'volume': order_book.daily_volume,
                    'turnover': float(order_book.daily_turnover),
                    'trade_count': order_book.trade_count,
                    'high': float(order_book.daily_high) if order_book.daily_high else None,
                    'low': float(order_book.daily_low) if order_book.daily_low else None,
                    'open': float(order_book.opening_price) if order_book.opening_price else None
                }
            }
            
            return snapshot
            
        except Exception as e:
            self.logger.error(f"Error getting order book snapshot: {e}")
            return {}
    
    def reset_daily_statistics(self, instrument: SimulatedInstrument):
        """Reset daily statistics for a new trading day"""
        try:
            order_book = instrument.order_book
            
            order_book.daily_volume = 0
            order_book.daily_turnover = Decimal('0.00')
            order_book.trade_count = 0
            order_book.daily_high = None
            order_book.daily_low = None
            order_book.opening_price = order_book.last_trade_price
            order_book.save()
            
            self.logger.info(f"Reset daily statistics for {instrument.real_ticker.symbol}")
            
        except Exception as e:
            self.logger.error(f"Error resetting daily statistics: {e}")


    def broadcast_market_data_update(self, instrument: SimulatedInstrument):
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
            self.logger.error(f"Error broadcasting market data update: {e}")
