# apps/order_management/clob_engine.py
"""
Production-Grade Central Limit Order Book (CLOB)
===============================================
Institutional-quality order matching with real supply/demand price discovery
"""

import logging
from typing import List, Tuple, Optional
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from .models import (
    SimulatedOrder, OrderBookLevel, OrderQueue, OrderBook,
    SimulatedTrade, Fill, OrderSide, OrderStatus
)

logger = logging.getLogger(__name__)


class CentralLimitOrderBook:
    """
    Production-grade order book with real supply/demand price discovery

    Features:
    - Order-to-order matching (no artificial market makers)
    - Price-time priority (price first, then FIFO)
    - Real price impact from supply/demand imbalance
    - Full order book depth management
    """

    def __init__(self, instrument):
        self.instrument = instrument
        self.order_book = instrument.order_book
        self.logger = logging.getLogger(f"{__name__}.CLOB.{instrument.real_ticker.symbol}")

    def submit_order(self, order: SimulatedOrder) -> Tuple[List[dict], int]:
        """
        Submit order to CLOB for matching
        Returns: (list_of_trades, remaining_quantity)
        """
        with transaction.atomic():
            if order.order_type == 'MARKET':
                return self._process_market_order(order)
            elif order.order_type == 'LIMIT':
                return self._process_limit_order(order)
            else:
                self.logger.warning(f"Unsupported order type: {order.order_type}")
                return [], order.quantity

    def _process_market_order(self, order: SimulatedOrder) -> Tuple[List[dict], int]:
        """
        Market Order: Aggressively takes liquidity from order book
        Price impact: Consumes order book levels, moving price
        """
        trades = []
        remaining_qty = order.quantity

        # Get opposite side levels ordered by best price
        if order.side == OrderSide.BUY:
            # Buy order: consume ask side (ascending price order)
            target_levels = self.order_book.levels.filter(
                side=OrderSide.SELL
            ).exclude(
                quantity=0
            ).order_by('price')

        else:  # SELL
            # Sell order: consume bid side (descending price order)
            target_levels = self.order_book.levels.filter(
                side=OrderSide.BUY
            ).exclude(
                quantity=0
            ).order_by('-price')

        # Walk through price levels until filled or no more liquidity
        for level in target_levels:
            if remaining_qty <= 0:
                break

            level_trades, remaining_qty = self._match_against_level(
                order, level, remaining_qty
            )
            trades.extend(level_trades)

            # If level is exhausted, it gets removed automatically
            level.refresh_from_db()
            if level.quantity == 0:
                level.delete()

        # Update best bid/ask after consuming liquidity
        self._update_best_quotes()

        self.logger.info(f"Market order {order.order_id}: {len(trades)} trades, {remaining_qty} remaining")
        return trades, remaining_qty

    def _process_limit_order(self, order: SimulatedOrder) -> Tuple[List[dict], int]:
        """
        Limit Order: Match if price allows, otherwise add to book
        Price discovery: Only matches at specified price or better
        """
        trades = []
        remaining_qty = order.quantity

        # First try to match against existing orders
        if order.side == OrderSide.BUY:
            # Buy limit: match against asks at or below our price
            matching_levels = self.order_book.levels.filter(
                side=OrderSide.SELL,
                price__lte=order.price  # Ask price <= our bid price
            ).exclude(
                quantity=0
            ).order_by('price')  # Best prices first

        else:  # SELL
            # Sell limit: match against bids at or above our price
            matching_levels = self.order_book.levels.filter(
                side=OrderSide.BUY,
                price__gte=order.price  # Bid price >= our ask price
            ).exclude(
                quantity=0
            ).order_by('-price')  # Best prices first

        # Execute matches
        for level in matching_levels:
            if remaining_qty <= 0:
                break

            level_trades, remaining_qty = self._match_against_level(
                order, level, remaining_qty
            )
            trades.extend(level_trades)

            # Clean up empty levels
            level.refresh_from_db()
            if level.quantity == 0:
                level.delete()

        # Add remaining quantity to order book
        if remaining_qty > 0:
            self._add_to_order_book(order, remaining_qty)

        # Update best quotes
        self._update_best_quotes()

        self.logger.info(f"Limit order {order.order_id}: {len(trades)} trades, {remaining_qty} added to book")
        return trades, remaining_qty

    def _match_against_level(self, incoming_order: SimulatedOrder,
                           level: OrderBookLevel, quantity: int) -> Tuple[List[dict], int]:
        """
        Match incoming order against orders at specific price level (FIFO)
        This is where order-to-order matching happens
        """
        trades = []
        remaining = quantity

        # Get all orders at this level in FIFO order
        order_queues = level.order_queue.filter(
            remaining_quantity__gt=0
        ).order_by('queue_position')

        for queue_entry in order_queues:
            if remaining <= 0:
                break

            resting_order = queue_entry.order
            available_qty = min(remaining, queue_entry.remaining_quantity)

            # Create trade between orders
            trade_data = self._execute_trade_between_orders(
                incoming_order, resting_order, available_qty, level.price
            )
            trades.append(trade_data)

            # Update queue entry
            queue_entry.remaining_quantity -= available_qty
            remaining -= available_qty

            if queue_entry.remaining_quantity == 0:
                # Order fully filled - remove from queue
                queue_entry.delete()
            else:
                queue_entry.save()

        # Update level totals
        total_quantity = level.order_queue.aggregate(
            total=models.Sum('remaining_quantity')
        )['total'] or 0

        level.quantity = total_quantity
        level.order_count = level.order_queue.count()
        level.save()

        return trades, remaining

    def _execute_trade_between_orders(self, aggressive_order: SimulatedOrder,
                                    passive_order: SimulatedOrder,
                                    quantity: int, price: Decimal) -> dict:
        """
        Execute actual trade between two real orders (no market makers!)
        This creates REAL supply/demand price discovery
        """
        # Determine buy/sell orders
        buy_order = aggressive_order if aggressive_order.side == OrderSide.BUY else passive_order
        sell_order = passive_order if aggressive_order.side == OrderSide.BUY else aggressive_order

        # Create trade record
        trade = SimulatedTrade.objects.create(
            exchange=self.instrument.exchange,
            instrument=self.instrument,
            buy_order=buy_order,
            sell_order=sell_order,
            quantity=quantity,
            price=price,
            is_aggressive=(aggressive_order.side == OrderSide.BUY)
        )

        # Calculate fees
        fee_rate = self.instrument.exchange.trading_fee_percentage
        trade_value = quantity * price
        fees = trade_value * fee_rate

        # Create fills for both orders
        Fill.objects.create(
            order=aggressive_order,
            trade=trade,
            quantity=quantity,
            price=price,
            fees=fees,
            liquidity_flag='TAKER'  # Aggressive order takes liquidity
        )

        Fill.objects.create(
            order=passive_order,
            trade=trade,
            quantity=quantity,
            price=price,
            fees=fees,
            liquidity_flag='MAKER'  # Passive order provides liquidity
        )

        # Update order statuses
        for order in [aggressive_order, passive_order]:
            order.filled_quantity += quantity
            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
                order.completion_timestamp = timezone.now()
            elif order.filled_quantity > 0:
                order.status = OrderStatus.PARTIALLY_FILLED

            if not order.first_fill_timestamp:
                order.first_fill_timestamp = timezone.now()
            order.last_fill_timestamp = timezone.now()
            order.save()

        # Update market price (CRITICAL: This creates real price discovery)
        self.order_book.last_trade_price = price
        self.order_book.last_trade_quantity = quantity
        self.order_book.last_trade_timestamp = timezone.now()
        self.order_book.daily_volume += quantity
        self.order_book.daily_turnover += trade.notional_value
        self.order_book.trade_count += 1

        # Update daily high/low
        if not self.order_book.daily_high or price > self.order_book.daily_high:
            self.order_book.daily_high = price
        if not self.order_book.daily_low or price < self.order_book.daily_low:
            self.order_book.daily_low = price

        self.order_book.save()

        self.logger.info(f"REAL TRADE: {quantity}@{price} between {aggressive_order.user.username} and {passive_order.user.username}")

        return {
            'trade_id': trade.trade_id,
            'quantity': quantity,
            'price': price,
            'aggressive_order': aggressive_order,
            'passive_order': passive_order
        }

    def _add_to_order_book(self, order: SimulatedOrder, quantity: int):
        """
        Add order to appropriate price level in order book
        Creates price levels and manages FIFO queues
        """
        side = order.side

        # Get or create price level
        level, created = OrderBookLevel.objects.get_or_create(
            order_book=self.order_book,
            side=side,
            price=order.price,
            defaults={'quantity': 0, 'order_count': 0}
        )

        # Determine queue position (FIFO)
        max_position = level.order_queue.aggregate(
            max_pos=models.Max('queue_position')
        )['max_pos'] or 0

        # Add to order queue at this level
        OrderQueue.objects.create(
            level=level,
            order=order,
            remaining_quantity=quantity,
            queue_position=max_position + 1
        )

        # Update level totals
        level.quantity += quantity
        level.order_count += 1
        level.save()

        self.logger.info(f"Added order {order.order_id} to book: {quantity}@{order.price}")

    def _update_best_quotes(self):
        """
        Update best bid/ask based on current order book levels
        This is what creates real market quotes from actual orders
        """
        # Best bid: highest price on buy side with quantity > 0
        best_bid_level = self.order_book.levels.filter(
            side=OrderSide.BUY,
            quantity__gt=0
        ).order_by('-price').first()

        if best_bid_level:
            self.order_book.best_bid_price = best_bid_level.price
            self.order_book.best_bid_quantity = best_bid_level.quantity
        else:
            self.order_book.best_bid_price = None
            self.order_book.best_bid_quantity = 0

        # Best ask: lowest price on sell side with quantity > 0
        best_ask_level = self.order_book.levels.filter(
            side=OrderSide.SELL,
            quantity__gt=0
        ).order_by('price').first()

        if best_ask_level:
            self.order_book.best_ask_price = best_ask_level.price
            self.order_book.best_ask_quantity = best_ask_level.quantity
        else:
            self.order_book.best_ask_price = None
            self.order_book.best_ask_quantity = 0

        self.order_book.save()
