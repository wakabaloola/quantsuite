# apps/trading_simulation/management/commands/demo_mixed_pressure.py 
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.trading_simulation.models import SimulatedInstrument
from apps.order_management.models import SimulatedOrder, OrderBookLevel, OrderQueue
from apps.order_management.services import OrderMatchingService
from decimal import Decimal
import time
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Demonstrate mixed buy/sell pressure using real market prices from yfinance'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='AAPL')
        parser.add_argument('--orders', type=int, default=12)
        parser.add_argument('--clear-book', action='store_true',
                          help='Clear existing order book first')

    def handle(self, *args, **options):
        symbol = options['symbol']
        num_orders = options['orders']
        clear_book = options['clear_book']

        self.stdout.write(self.style.SUCCESS('%=====###===###=== MIXED PRESSURE DEMO ===###===###=====%'))
        self.stdout.write(f"Symbol: {symbol}")
        self.stdout.write(f"Orders: {num_orders}")
        #self.stdout.write("Using REAL market prices from Yahoo Finance!")
        #self.stdout.write("Watch realistic bid/ask competition!\n")

        # Get instrument and real market price
        instrument = SimulatedInstrument.objects.get(real_ticker__symbol=symbol)
        users = User.objects.filter(username__startswith='demo_trader_')
        matching_service = OrderMatchingService()

        # Get real current market price
        real_price = self.get_real_market_price(instrument)
        if not real_price:
            self.stdout.write(self.style.ERROR("Could not get real market price"))
            return

        self.stdout.write(f"📊 REAL MARKET PRICE: ${real_price}")
        self.stdout.write(f"Creating realistic orders around this price...\n")

        # Optionally clear existing order book
        if clear_book:
            self.stdout.write("Clearing existing order book...")
            OrderBookLevel.objects.filter(order_book=instrument.order_book).delete()

        # Show initial state
        self.show_order_book_state(instrument, "INITIAL")

        # Create realistic mixed orders
        for i in range(1, num_orders + 1):
            user = users[(i-1) % len(users)]

            # Randomly choose buy or sell (60% buy, 40% sell for slight buying pressure)
            is_buy = random.random() < 0.6 # (In the future, rather than random, this could be based on strategies, algorithms, news, volatility, and the trader's own trading goals)

            if is_buy:
                self.create_buy_order(user, instrument, real_price, i, matching_service)
            else:
                self.create_sell_order(user, instrument, real_price, i, matching_service)

            # Show state after each order
            self.show_order_book_state(instrument, f"AFTER ORDER {i}")

            # Small delay to show progression
            time.sleep(1.0)

        # Final analysis
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("FINAL MARKET ANALYSIS"))
        self.stdout.write("="*60)
        self.show_final_analysis(instrument, real_price)

    def get_real_market_price(self, instrument):
        """Get the real current market price from our market data"""
        try:
            # Get the latest market data record
            latest_data = instrument.real_ticker.market_data.first()
            if latest_data:
                return latest_data.close

            # Fallback: get current order book price
            if instrument.order_book.last_trade_price:
                return instrument.order_book.last_trade_price

            return None

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error getting market price: {e}"))
            return None

    def create_buy_order(self, user, instrument, market_price, order_num, matching_service):
        """Create realistic buy order below market price"""
        # Realistic buy order pricing (below market)
        price_discount_bps = random.randint(5, 200)  # 0.05% to 2% below market. (In the future, rather than random, this could be based on strategies, algorithms, news, volatility, and the trader's own trading goals)
        price_discount = market_price * Decimal(str(price_discount_bps / 10000))
        order_price = market_price - price_discount

        # Realistic quantity (odd lots, round lots, etc.)
        quantity_options = [25, 50, 75, 100, 150, 200, 250, 500]
        quantity = random.choice(quantity_options)

        # Realistic order types
        order_type = random.choice(['LIMIT', 'LIMIT', 'LIMIT', 'MARKET'])  # Favor limits

        self.stdout.write(f"%==========%%%%%%%%%% Order {order_num} %%%%%%%%%%==========%")
        self.stdout.write(f"👤 {user.username}")
        self.stdout.write(f"📈 BUY {quantity} @ ${order_price:.2f} ({order_type})")
        self.stdout.write(f"   Market: ${market_price:.2f} | Discount: {price_discount_bps} bps")

        # Create order
        order = SimulatedOrder.objects.create(
            user=user,
            exchange=instrument.exchange,
            instrument=instrument,
            side='BUY',
            order_type=order_type,
            quantity=quantity,
            price=order_price if order_type == 'LIMIT' else None,
            time_in_force='GTC'
        )

        # Submit order
        success, message, _ = matching_service.submit_order(order) # OrderMatchingService contains the core logic of the market

        if success:
            if 'FILLED' in message or order.status == 'FILLED':
                self.stdout.write(self.style.SUCCESS(f"   ✅ EXECUTED: {order.status}"))
            elif 'PARTIALLY_FILLED' in message:
                self.stdout.write(self.style.WARNING(f"   ◐ PARTIAL: {order.filled_quantity}/{order.quantity}"))
            else:
                self.stdout.write(f"   📋 ADDED TO BOOK")
        else:
            self.stdout.write(self.style.ERROR(f"   ❌ FAILED: {message}"))

    def create_sell_order(self, user, instrument, market_price, order_num, matching_service):
        """Create realistic sell order above market price"""
        # Realistic sell order pricing (above market)
        price_premium_bps = random.randint(5, 150)  # 0.05% to 1.5% above market (In the future, rather than random, this could be based on strategies, algorithms, news, volatility, and the trader's own trading goals)
        price_premium = market_price * Decimal(str(price_premium_bps / 10000))
        order_price = market_price + price_premium

        # Realistic quantity
        quantity_options = [25, 50, 75, 100, 150, 200, 300]
        quantity = random.choice(quantity_options)

        # Realistic order types
        order_type = random.choice(['LIMIT', 'LIMIT', 'LIMIT', 'MARKET'])  # Favor limits

        self.stdout.write(f"%==========%%%%%%%%%% Order {order_num} %%%%%%%%%%==========%")
        self.stdout.write(f"👤 {user.username}")
        self.stdout.write(f"📉 SELL {quantity} @ ${order_price:.2f} ({order_type})")
        self.stdout.write(f"   Market: ${market_price:.2f} | Premium: {price_premium_bps} bps")

        # Create order
        order = SimulatedOrder.objects.create(
            user=user,
            exchange=instrument.exchange,
            instrument=instrument,
            side='SELL',
            order_type=order_type,
            quantity=quantity,
            price=order_price if order_type == 'LIMIT' else None,
            time_in_force='GTC'
        )

        # Submit order
        success, message, _ = matching_service.submit_order(order)

        if success:
            if 'FILLED' in message or order.status == 'FILLED':
                self.stdout.write(self.style.SUCCESS(f"   ✅ EXECUTED: {order.status}"))
            elif 'PARTIALLY_FILLED' in message:
                self.stdout.write(self.style.WARNING(f"   ◐ PARTIAL: {order.filled_quantity}/{order.quantity}"))
            else:
                self.stdout.write(f"   📋 ADDED TO BOOK")
        else:
            self.stdout.write(self.style.ERROR(f"   ❌ FAILED: {message}"))

    def show_order_book_state(self, instrument, stage):
        """Show current order book with realistic market context"""
        order_book = instrument.order_book

        self.stdout.write(f"\n💹 ORDER BOOK: {stage}")
        self.stdout.write(f"Last Trade: ${order_book.last_trade_price or 'None'}")

        # Calculate spread
        if order_book.best_bid_price and order_book.best_ask_price:
            spread = order_book.best_ask_price - order_book.best_bid_price
            spread_bps = (spread / order_book.best_ask_price) * 10000
            self.stdout.write(f"Spread: ${spread:.2f} ({spread_bps:.1f} bps)")

        self.stdout.write(f"Volume: {order_book.daily_volume} shares")

        # Show top 3 levels each side
        self.stdout.write("📋 BOOK DEPTH:")

        # Bids (buyers) - highest prices first
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='BUY',
            quantity__gt=0
        ).order_by('-price')[:3]

        # Asks (sellers) - lowest prices first
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='SELL',
            quantity__gt=0
        ).order_by('price')[:3]

        # Display side by side
        self.stdout.write("   BIDS (Buyers)              ASKS (Sellers)")
        self.stdout.write("   ──────────────              ──────────────")

        max_levels = max(len(bid_levels), len(ask_levels))
        for i in range(max_levels):
            bid_str = ""
            ask_str = ""

            if i < len(bid_levels):
                bid = bid_levels[i]
                bid_str = f"   ${bid.price:7.2f} x {bid.quantity:4d}"
            else:
                bid_str = " " * 20

            if i < len(ask_levels):
                ask = ask_levels[i]
                ask_str = f"${ask.price:7.2f} x {ask.quantity:4d}"
            else:
                ask_str = ""

            self.stdout.write(f"{bid_str}              {ask_str}")

        self.stdout.write()

    def show_final_analysis(self, instrument, original_price):
        """Analyze final market state vs original price"""
        order_book = instrument.order_book

        # Price movement analysis
        if order_book.last_trade_price:
            price_change = order_book.last_trade_price - original_price
            price_change_pct = (price_change / original_price) * 100

            if price_change > 0:
                direction = "📈 UP"
                color = self.style.SUCCESS
            elif price_change < 0:
                direction = "📉 DOWN"
                color = self.style.ERROR
            else:
                direction = "➡️ FLAT"
                color = self.style.WARNING

            self.stdout.write(color(f"PRICE MOVEMENT: {direction}"))
            self.stdout.write(f"Original: ${original_price:.2f}")
            self.stdout.write(f"Current:  ${order_book.last_trade_price:.2f}")
            self.stdout.write(f"Change:   ${price_change:+.2f} ({price_change_pct:+.2f}%)")

        # Order book analysis
        bid_count = OrderBookLevel.objects.filter(
            order_book=order_book, side='BUY', quantity__gt=0
        ).count()
        ask_count = OrderBookLevel.objects.filter(
            order_book=order_book, side='SELL', quantity__gt=0
        ).count()

        self.stdout.write(f"\n📊 FINAL ORDER BOOK:")
        self.stdout.write(f"Bid Levels: {bid_count}")
        self.stdout.write(f"Ask Levels: {ask_count}")

        if bid_count > ask_count:
            self.stdout.write(self.style.SUCCESS("💪 BUYING PRESSURE dominates"))
        elif ask_count > bid_count:
            self.stdout.write(self.style.ERROR("💰 SELLING PRESSURE dominates"))
        else:
            self.stdout.write(self.style.WARNING("⚖️ BALANCED order book"))

        # Volume analysis
        if order_book.daily_volume > 0:
            self.stdout.write(f"Total Volume: {order_book.daily_volume:,} shares")
            avg_trade_size = order_book.daily_volume / max(order_book.trade_count, 1)
            self.stdout.write(f"Average Trade: {avg_trade_size:.0f} shares")

        # Market quality metrics
        if order_book.best_bid_price and order_book.best_ask_price:
            spread = order_book.best_ask_price - order_book.best_bid_price
            spread_bps = (spread / order_book.last_trade_price) * 10000 if order_book.last_trade_price else 0

            self.stdout.write(f"\n📏 MARKET QUALITY:")
            self.stdout.write(f"Spread: ${spread:.2f} ({spread_bps:.1f} bps)")

            if spread_bps < 10:
                self.stdout.write(self.style.SUCCESS("✅ TIGHT SPREAD - High liquidity"))
            elif spread_bps < 50:
                self.stdout.write(self.style.WARNING("⚠️ MODERATE SPREAD"))
            else:
                self.stdout.write(self.style.ERROR("❌ WIDE SPREAD - Low liquidity"))
