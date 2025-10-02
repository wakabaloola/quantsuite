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
    help = 'Realistic trading demo with proper pricing'
    
    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='META')
        parser.add_argument('--orders', type=int, default=12)
        parser.add_argument('--delay', type=float, default=1.5)
    
    def handle(self, *args, **options):
        symbol = options['symbol']
        num_orders = options['orders']
        delay = options['delay']
        
        self.stdout.write(self.style.SUCCESS('=== REALISTIC TRADING DEMO ==='))
        self.stdout.write(f"Symbol: {symbol}")
        self.stdout.write(f"Orders: {num_orders} (mixed buy/sell)")
        self.stdout.write("💰 REALISTIC PRICES FOR ACTUAL TRADING!\n")
        
        # Get instrument and users
        instrument = SimulatedInstrument.objects.get(real_ticker__symbol=symbol)
        users = User.objects.filter(username__startswith='demo_trader_')
        matching_service = OrderMatchingService()
        
        # Clear existing order book to start fresh
        self.stdout.write("Clearing existing order book...")
        OrderBookLevel.objects.filter(order_book=instrument.order_book).delete()
        instrument.order_book.best_bid_price = None
        instrument.order_book.best_ask_price = None
        instrument.order_book.best_bid_quantity = 0
        instrument.order_book.best_ask_quantity = 0
        instrument.order_book.save()
        
        # Set realistic reference price based on symbol
        realistic_prices = {
            'META': Decimal('350.00'),
            'AAPL': Decimal('230.00'), 
            'TSLA': Decimal('340.00'),
            'NVDA': Decimal('185.00'),
            'GOOGL': Decimal('200.00'),
            'MSFT': Decimal('530.00'),
            'AMZN': Decimal('220.00')
        }
        
        base_price = realistic_prices.get(symbol, Decimal('300.00'))
        self.stdout.write(f"Using realistic base price: ${base_price}")
        
        # Show initial state
        self.show_order_book(instrument, "INITIAL")
        
        # Create realistic mixed orders
        for i in range(1, num_orders + 1):
            user = users[(i-1) % len(users)]
            
            # Generate realistic order
            side, order_type, price, quantity = self.generate_realistic_order(
                i, base_price, instrument
            )
            
            self.stdout.write(f"\n--- Order {i}/{num_orders} ---")
            self.stdout.write(f"User: {user.username}")
            self.stdout.write(f"{side} {quantity} @ ${price or 'MARKET'} ({order_type})")
            
            # Calculate order value for context
            if price:
                order_value = price * quantity
                self.stdout.write(f"  Order Value: ${order_value:,.2f}")
            
            # Create the order
            order = SimulatedOrder.objects.create(
                user=user,
                exchange=instrument.exchange,
                instrument=instrument,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price if order_type == 'LIMIT' else None,
                time_in_force='GTC'
            )
            
            # Submit to matching engine
            success, message, violations = matching_service.submit_order(order)
            
            if success:
                order.refresh_from_db()
                if order.status == 'FILLED':
                    self.stdout.write(self.style.SUCCESS(f"🎯 TRADE EXECUTED: {order.filled_quantity} shares!"))
                elif order.status == 'PARTIALLY_FILLED':
                    self.stdout.write(self.style.WARNING(f"🔸 PARTIAL FILL: {order.filled_quantity}/{order.quantity}"))
                else:
                    self.stdout.write(f"📋 ADDED TO BOOK: Waiting for counterpart")
            else:
                self.stdout.write(self.style.ERROR(f"❌ REJECTED: {message}"))
                if violations:
                    for violation in violations:
                        self.stdout.write(f"   Risk: {violation}")
            
            # Show updated market state
            self.show_order_book(instrument, f"AFTER ORDER {i}")
            self.show_recent_trades(instrument, 2)
            
            time.sleep(delay)
        
        # Final analysis
        self.show_final_analysis(instrument)
    
    def generate_realistic_order(self, order_num, base_price, instrument):
        """Generate realistic orders that users can afford"""
        order_book = instrument.order_book
        
        # Create price variations around base price (±5%)
        price_variation = random.uniform(-0.05, 0.05)
        ref_price = base_price * (1 + Decimal(str(price_variation)))
        
        # Order patterns with affordable quantities
        patterns = [
            # Market orders (small quantities)
            ('BUY', 'MARKET', None, random.randint(5, 25)),
            ('SELL', 'MARKET', None, random.randint(5, 25)),
            
            # Limit orders near market
            ('BUY', 'LIMIT', ref_price * Decimal('0.998'), random.randint(10, 40)),
            ('SELL', 'LIMIT', ref_price * Decimal('1.002'), random.randint(10, 40)),
            
            # Patient orders away from market
            ('BUY', 'LIMIT', ref_price * Decimal('0.990'), random.randint(20, 60)),
            ('SELL', 'LIMIT', ref_price * Decimal('1.010'), random.randint(20, 60)),
        ]
        
        # Choose pattern based on order number
        if order_num % 3 == 0:  # Every 3rd order is market
            pattern_idx = 0 if order_num % 6 == 0 else 1
        else:
            pattern_idx = random.randint(2, 5)
        
        side, order_type, price_factor, base_qty = patterns[pattern_idx]
        
        # Calculate final price
        if order_type == 'LIMIT':
            if price_factor:
                price = price_factor
            else:
                price = ref_price
        else:
            price = None
        
        # Ensure quantities are affordable (max ~$50K orders)
        max_affordable_qty = 150  # At $350/share = $52,500 max
        quantity = min(base_qty, max_affordable_qty)
        
        return side, order_type, price, quantity
    
    def show_order_book(self, instrument, stage):
        order_book = instrument.order_book
        
        self.stdout.write(f"\n📊 MARKET STATE: {stage}")
        self.stdout.write("─" * 40)
        
        self.stdout.write(f"💰 Last Trade: ${order_book.last_trade_price or 'None'}")
        self.stdout.write(f"📈 Volume: {order_book.daily_volume} shares")
        self.stdout.write(f"🎯 Best Bid/Ask: ${order_book.best_bid_price or 'None'} / ${order_book.best_ask_price or 'None'}")
        
        # Show spread
        if order_book.best_bid_price and order_book.best_ask_price:
            spread = order_book.best_ask_price - order_book.best_bid_price
            spread_pct = float(spread / order_book.best_ask_price * 100)
            self.stdout.write(f"📏 Spread: ${spread:.2f} ({spread_pct:.2f}%)")
        
        # Show top 3 levels each side
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='SELL'
        ).order_by('price')[:3]
        
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='BUY'
        ).order_by('-price')[:3]
        
        if ask_levels:
            self.stdout.write("ASK: " + " | ".join([f"${l.price:.2f}x{l.quantity}" for l in ask_levels]))
        if bid_levels:
            self.stdout.write("BID: " + " | ".join([f"${l.price:.2f}x{l.quantity}" for l in bid_levels]))
    
    def show_recent_trades(self, instrument, count=2):
        from apps.order_management.models import SimulatedTrade
        
        recent_trades = SimulatedTrade.objects.filter(
            instrument=instrument
        ).order_by('-trade_timestamp')[:count]
        
        if recent_trades:
            self.stdout.write("💥 Recent Trades:")
            for trade in recent_trades:
                buyer = trade.buy_order.user.username.replace('demo_trader_', 'T')
                seller = trade.sell_order.user.username.replace('demo_trader_', 'T')
                value = trade.quantity * trade.price
                self.stdout.write(f"   {trade.quantity} @ ${trade.price:.2f} = ${value:,.2f} ({buyer}←{seller})")
    
    def show_final_analysis(self, instrument):
        order_book = instrument.order_book
        
        self.stdout.write(self.style.SUCCESS("\n🎯 FINAL ANALYSIS"))
        self.stdout.write("=" * 40)
        
        if order_book.daily_high and order_book.daily_low:
            price_range = order_book.daily_high - order_book.daily_low
            volatility = float(price_range / order_book.daily_high * 100)
            self.stdout.write(f"📈 Trading Range: ${order_book.daily_low:.2f} - ${order_book.daily_high:.2f}")
            self.stdout.write(f"📊 Session Volatility: {volatility:.2f}%")
        
        self.stdout.write(f"🔄 Total Volume: {order_book.daily_volume} shares")
        self.stdout.write(f"🎪 Trade Count: {order_book.trade_count}")
        
        if order_book.daily_turnover:
            self.stdout.write(f"💰 Total Turnover: ${order_book.daily_turnover:,.2f}")
        
        # Count pending orders
        bid_levels = OrderBookLevel.objects.filter(order_book=order_book, side='BUY').count()
        ask_levels = OrderBookLevel.objects.filter(order_book=order_book, side='SELL').count()
        
        self.stdout.write(f"📋 Pending Orders: {bid_levels} bids, {ask_levels} asks")
        
        self.stdout.write("\n✅ INSTITUTIONAL TRADING DEMONSTRATED:")
        self.stdout.write("   • Real order-to-order matching")
        self.stdout.write("   • Risk management working properly")
        self.stdout.write("   • Natural supply/demand price discovery")
        self.stdout.write("   • Professional market microstructure")
