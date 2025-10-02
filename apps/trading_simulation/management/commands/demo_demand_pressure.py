# apps/trading_simulation/management/commands/demo_demand_pressure.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.trading_simulation.models import SimulatedInstrument
from apps.order_management.models import SimulatedOrder, OrderBookLevel, OrderQueue
from apps.order_management.services import OrderMatchingService
from decimal import Decimal
import time

User = get_user_model()

class Command(BaseCommand):
    help = 'Demonstrate demand pressure without supply'
    
    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='TSLA')
        parser.add_argument('--buy-orders', type=int, default=8)
    
    def handle(self, *args, **options):
        symbol = options['symbol']
        num_orders = options['buy_orders']
        
        self.stdout.write(self.style.SUCCESS('=== DEMAND PRESSURE DEMO ==='))
        self.stdout.write(f"Testing: {symbol}")
        self.stdout.write(f"Creating {num_orders} BUY orders with NO SELLERS\n")
        
        # Get instrument and users
        instrument = SimulatedInstrument.objects.get(real_ticker__symbol=symbol)
        users = User.objects.filter(username__startswith='demo_trader_')
        matching_service = OrderMatchingService()
        
        # Clear existing order book
        self.stdout.write("Clearing existing order book...")
        OrderBookLevel.objects.filter(order_book=instrument.order_book).delete()
        
        # Show initial state
        self.show_order_book_state(instrument, "INITIAL")
        
        # Create multiple buy orders at different prices
        base_price = Decimal('300.00')
        
        for i in range(1, num_orders + 1):
            user = users[(i-1) % len(users)]
            
            # Create buy orders at incrementally higher prices
            price = base_price + Decimal(str(i * 2))  # $302, $304, $306, etc.
            quantity = 25 + (i * 10)  # Increasing quantities
            
            self.stdout.write(f"--- Buy Order {i}/{num_orders} ---")
            self.stdout.write(f"User: {user.username}")
            self.stdout.write(f"BUY {quantity} @ ${price}")
            
            # Create the order
            order = SimulatedOrder.objects.create(
                user=user,
                exchange=instrument.exchange,
                instrument=instrument,
                side='BUY',
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
            self.show_order_book_state(instrument, f"AFTER ORDER {i}")
            
            time.sleep(0.5)
        
        # Now add ONE sell order and watch the fireworks
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.WARNING("NOW ADDING ONE MARKET SELL ORDER..."))
        self.stdout.write("="*50)
        
        sell_order = SimulatedOrder.objects.create(
            user=users[0],
            exchange=instrument.exchange,
            instrument=instrument,
            side='SELL',
            order_type='MARKET',
            quantity=50,  # Will match against highest bid
            time_in_force='GTC'
        )
        
        success, message, _ = matching_service.submit_order(sell_order)
        
        if success:
            self.stdout.write(self.style.SUCCESS("✓ MARKET SELL EXECUTED!"))
        
        # Show final state
        self.show_order_book_state(instrument, "FINAL - AFTER SELL")
        self.show_trade_results(instrument)
    
    def show_order_book_state(self, instrument, stage):
        order_book = instrument.order_book
        
        self.stdout.write(f"\n--- ORDER BOOK STATE: {stage} ---")
        self.stdout.write(f"Last Trade: ${order_book.last_trade_price or 'None'}")
        self.stdout.write(f"Best Bid: ${order_book.best_bid_price or 'None'} x {order_book.best_bid_quantity}")
        self.stdout.write(f"Best Ask: ${order_book.best_ask_price or 'None'} x {order_book.best_ask_quantity}")
        self.stdout.write(f"Daily Volume: {order_book.daily_volume}")
        
        # Show bid side depth
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='BUY'
        ).order_by('-price')[:5]
        
        if bid_levels:
            self.stdout.write("BID DEPTH:")
            for level in bid_levels:
                self.stdout.write(f"  ${level.price} x {level.quantity} ({level.order_count} orders)")
        else:
            self.stdout.write("BID DEPTH: Empty")
        
        # Show ask side depth  
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book,
            side='SELL'
        ).order_by('price')[:5]
        
        if ask_levels:
            self.stdout.write("ASK DEPTH:")
            for level in ask_levels:
                self.stdout.write(f"  ${level.price} x {level.quantity} ({level.order_count} orders)")
        else:
            self.stdout.write("ASK DEPTH: Empty")
        
        self.stdout.write()
    
    def show_trade_results(self, instrument):
        from apps.order_management.models import SimulatedTrade
        
        recent_trades = SimulatedTrade.objects.filter(
            instrument=instrument
        ).order_by('-trade_timestamp')[:3]
        
        if recent_trades:
            self.stdout.write(self.style.SUCCESS("RECENT TRADES:"))
            for trade in recent_trades:
                buyer = trade.buy_order.user.username
                seller = trade.sell_order.user.username
                self.stdout.write(f"  {trade.quantity} @ ${trade.price} ({buyer} ← {seller})")
        else:
            self.stdout.write("No recent trades")
