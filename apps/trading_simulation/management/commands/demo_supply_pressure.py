# apps/trading_simulation/management/commands/demo_supply_pressure.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.trading_simulation.models import SimulatedInstrument
from apps.order_management.models import SimulatedOrder, OrderBookLevel, OrderQueue
from apps.order_management.services import OrderMatchingService
from decimal import Decimal
import time

User = get_user_model()

class Command(BaseCommand):
    help = 'Demonstrate supply pressure without demand - selling pressure drives prices down'
    
    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='NVDA')
        parser.add_argument('--sell-orders', type=int, default=7)
    
    def handle(self, *args,clear_existing_orders=True, **options):
        symbol = options['symbol']
        num_orders = options['sell_orders']
        
        self.stdout.write(self.style.SUCCESS('=== SUPPLY PRESSURE DEMO ==='))
        self.stdout.write(f"Testing: {symbol}")
        self.stdout.write(f"Creating {num_orders} SELL orders with NO BUYERS")
        self.stdout.write("Watch prices fall as sellers compete!\n")
        
        # Get instrument and users
        instrument = SimulatedInstrument.objects.get(real_ticker__symbol=symbol)
        users = User.objects.filter(username__startswith='demo_trader_')
        matching_service = OrderMatchingService()
        
        # Clear existing order book
        if clear_existing_orders:
            self.stdout.write("Clearing existing order book...")
            OrderBookLevel.objects.filter(order_book=instrument.order_book).delete()
        else:
            # Show existing state instead of clearing
            self.stdout.write("Checking existing order book...")
            existing_asks = OrderBookLevel.objects.filter(
                order_book=instrument.order_book,
                side='SELL'
            ).count()

            if existing_asks > 0:
                self.stdout.write(f"Found {existing_asks} existing sell levels")
                self.show_order_book_state(instrument, "EXISTING")
            else:
                self.stdout.write("Order book is empty")
        
        # Show initial state
        self.show_order_book_state(instrument, "INITIAL")
        
        # Create multiple SELL orders at progressively LOWER prices
        base_price = Decimal('200.00')  # Start high
        
        for i in range(1, num_orders + 1):
            user = users[(i-1) % len(users)]
            
            # Create sell orders at DECREASING prices (supply pressure!)
            price = base_price - Decimal(str(i * 3))  # $197, $194, $191, etc.
            quantity = 30 + (i * 15)  # Increasing quantities (desperation!)
            
            self.stdout.write(f"--- Sell Order {i}/{num_orders} ---")
            self.stdout.write(f"User: {user.username}")
            self.stdout.write(f"SELL {quantity} @ ${price}")
            self.stdout.write(f"  └─ Price falling: sellers competing for buyers!")
            
            # Create the order
            order = SimulatedOrder.objects.create(
                user=user,
                exchange=instrument.exchange,
                instrument=instrument,
                side='SELL',
                order_type='LIMIT',
                quantity=quantity,
                price=price,
                time_in_force='GTC'
            )
            
            # Submit to matching engine
            success, message, _ = matching_service.submit_order(order)
            
            if success:
                self.stdout.write(f"✓ Order added to book")
            else:
                self.stdout.write(f"✗ Order failed: {message}")
            
            # Show updated order book state
            self.show_order_book_state(instrument, f"AFTER SELL ORDER {i}")
            
            time.sleep(0.7)
        
        # Now add ONE buy order and watch it get the BEST DEAL
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.WARNING("NOW ADDING ONE MARKET BUY ORDER..."))
        self.stdout.write("BUYER GETS THE CHEAPEST AVAILABLE SHARES!")
        self.stdout.write("="*60)
        
        buy_order = SimulatedOrder.objects.create(
            user=users[0],
            exchange=instrument.exchange,
            instrument=instrument,
            side='BUY',
            order_type='MARKET',
            quantity=80,  # Large order - will consume multiple levels
            time_in_force='GTC'
        )
        
        success, message, _ = matching_service.submit_order(buy_order)
        
        if success:
            self.stdout.write(self.style.SUCCESS("✓ MARKET BUY EXECUTED!"))
            self.stdout.write("Buyer got the LOWEST available prices!")
        
        # Show final state
        self.show_order_book_state(instrument, "FINAL - AFTER BUY")
        self.show_trade_results(instrument)
        self.analyze_price_improvement()
    
    def show_order_book_state(self, instrument, stage):
        order_book = instrument.order_book
        
        self.stdout.write(f"\n--- ORDER BOOK STATE: {stage} ---")
        self.stdout.write(f"Last Trade: ${order_book.last_trade_price or 'None'}")
        self.stdout.write(f"Best Bid: ${order_book.best_bid_price or 'None'} x {order_book.best_bid_quantity}")
        self.stdout.write(f"Best Ask: ${order_book.best_ask_price or 'None'} x {order_book.best_ask_quantity}")
        self.stdout.write(f"Daily Volume: {order_book.daily_volume}")
        
        # Show ask side depth (sellers)
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='SELL'
        ).order_by('price')[:6]  # Lowest prices first
        
        if ask_levels:
            self.stdout.write("ASK DEPTH (Sellers):")
            for level in ask_levels:
                self.stdout.write(f"  ${level.price} x {level.quantity} ({level.order_count} orders)")
        else:
            self.stdout.write("ASK DEPTH: Empty")
        
        # Show bid side depth (buyers)
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='BUY'
        ).order_by('-price')[:3]
        
        if bid_levels:
            self.stdout.write("BID DEPTH (Buyers):")
            for level in bid_levels:
                self.stdout.write(f"  ${level.price} x {level.quantity} ({level.order_count} orders)")
        else:
            self.stdout.write("BID DEPTH: Empty")
        
        self.stdout.write()
    
    def show_trade_results(self, instrument):
        from apps.order_management.models import SimulatedTrade
        
        recent_trades = SimulatedTrade.objects.filter(
            instrument=instrument
        ).order_by('-trade_timestamp')[:5]
        
        if recent_trades:
            self.stdout.write(self.style.SUCCESS("RECENT TRADES (Buyer got these prices):"))
            total_value = Decimal('0')
            total_shares = 0
            
            for trade in recent_trades:
                buyer = trade.buy_order.user.username
                seller = trade.sell_order.user.username
                value = trade.quantity * trade.price
                total_value += value
                total_shares += trade.quantity
                
                self.stdout.write(f"  {trade.quantity} @ ${trade.price} = ${value:.2f} ({buyer} ← {seller})")
            
            if total_shares > 0:
                avg_price = total_value / total_shares
                self.stdout.write(f"\nBUYER'S AVERAGE PRICE: ${avg_price:.6f}")
                self.stdout.write(f"TOTAL SHARES: {total_shares}")
                self.stdout.write(f"TOTAL COST: ${total_value:.2f}")
        else:
            self.stdout.write("No recent trades")
    
    def analyze_price_improvement(self):
        self.stdout.write(self.style.SUCCESS("\n=== SUPPLY PRESSURE ANALYSIS ==="))
        self.stdout.write("📉 WHAT HAPPENED:")
        self.stdout.write("  • Multiple sellers created DOWNWARD price pressure")
        self.stdout.write("  • Sellers competed by LOWERING their prices")
        self.stdout.write("  • Buyer got BEST possible execution (lowest prices)")
        self.stdout.write("  • Classic supply/demand: Excess supply = Lower prices")
        self.stdout.write("\n🎯 MARKET MECHANICS:")
        self.stdout.write("  • Price discovery through competitive selling")
        self.stdout.write("  • Buyers have leverage when supply exceeds demand")
        self.stdout.write("  • Market orders consume best available liquidity")
        self.stdout.write("  • No artificial price setting - pure market forces!")
