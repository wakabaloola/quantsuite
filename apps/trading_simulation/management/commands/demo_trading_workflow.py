# apps/trading_simulation/management/commands/demo_trading_workflow.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from apps.trading_simulation.models import SimulatedInstrument, SimulatedExchange
from apps.trading_simulation.services import SimulatedExchangeService
from apps.order_management.models import SimulatedOrder, OrderBook, SimulatedTrade
from apps.order_management.services import OrderMatchingService
from apps.market_data.models import Ticker
from decimal import Decimal
import time
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Demonstrate live trading workflow with real order matching'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            default='AAPL',
            help='Symbol to trade (default: AAPL)'
        )
        parser.add_argument(
            '--trades',
            type=int,
            default=5,
            help='Number of trades to execute (default: 5)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=2.0,
            help='Delay between trades in seconds (default: 2.0)'
        )


    def handle(self, *args, **options):
        symbol = options['symbol'].upper()
        num_trades = options['trades']
        delay = options['delay']
        
        self.stdout.write(self.style.SUCCESS('=== LIVE TRADING WORKFLOW DEMO ===\n'))
        self.stdout.write(f"Symbol: {symbol}")
        self.stdout.write(f"Number of trades: {num_trades}")
        self.stdout.write(f"Delay between trades: {delay}s\n")
        
        # Get the simulated instrument
        instrument = self.get_instrument(symbol)
        if not instrument:
            self.stdout.write(self.style.ERROR(f"Symbol {symbol} not found in simulation"))
            return
        
        # Initialize order book pricing
        self.initialize_order_book(instrument)
        
        # Get demo users
        users = self.get_demo_users()
        if len(users) < 2:
            self.stdout.write(self.style.ERROR("Need at least 2 demo users"))
            return
        
        # Show initial state
        self.show_portfolio_state(users, instrument)
        
        # Execute trading workflow
        self.execute_trading_workflow(instrument, users, num_trades, delay)
        
        # Show final state
        self.show_final_results(users, instrument)


    def get_instrument(self, symbol):
        """Get simulated instrument by symbol"""
        try:
            return SimulatedInstrument.objects.select_related(
                'real_ticker', 'exchange', 'order_book'
            ).get(real_ticker__symbol=symbol)
        except SimulatedInstrument.DoesNotExist:
            return None


    def get_demo_users(self):
        """Get demo trader users"""
        return list(User.objects.filter(username__startswith='demo_trader_'))


    def initialize_order_book(self, instrument):
        """Initialize order book with current market price"""
        self.stdout.write(self.style.WARNING('Initializing order book...'))
        
        # Get latest market data
        latest_data = instrument.real_ticker.market_data.first()
        if not latest_data:
            self.stdout.write(self.style.ERROR('No market data available'))
            return
        
        current_price = latest_data.close
        order_book = instrument.order_book
        
        # Set current pricing
        spread_bps = 10  # 10 basis points spread
        spread = current_price * Decimal('0.001')  # 0.1% spread
        
        order_book.last_trade_price = current_price
        order_book.opening_price = current_price
        order_book.best_bid_price = current_price - (spread / 2)
        order_book.best_bid_quantity = 100
        order_book.best_ask_price = current_price + (spread / 2)
        order_book.best_ask_quantity = 100
        order_book.daily_high = current_price
        order_book.daily_low = current_price
        order_book.save()
        
        self.stdout.write(f"✓ Order book initialized:")
        self.stdout.write(f"  Current Price: ${current_price}")
        self.stdout.write(f"  Bid: ${order_book.best_bid_price} x {order_book.best_bid_quantity}")
        self.stdout.write(f"  Ask: ${order_book.best_ask_price} x {order_book.best_ask_quantity}")
        self.stdout.write(f"  Spread: {order_book.spread_bps:.1f} bps\n")


    def show_portfolio_state(self, users, instrument):
        """Show current portfolio state for all users"""
        self.stdout.write(self.style.HTTP_INFO('--- Initial Portfolio State ---'))
        
        for user in users:
            profile = user.simulation_profile
            positions = user.simulated_positions.filter(instrument=instrument)
            
            self.stdout.write(f"{user.username}:")
            self.stdout.write(f"  Cash: ${profile.virtual_cash_balance}")
            self.stdout.write(f"  Portfolio Value: ${profile.current_portfolio_value}")
            
            if positions.exists():
                for pos in positions:
                    self.stdout.write(f"  {instrument.real_ticker.symbol}: {pos.quantity} shares @ ${pos.average_cost}")
            else:
                self.stdout.write(f"  {instrument.real_ticker.symbol}: No position")
        
        self.stdout.write()

    def show_final_results(self, users, instrument):
        """Show final trading results"""
        self.stdout.write(self.style.SUCCESS('--- Final Trading Results ---'))
        
        # Show order book state
        order_book = instrument.order_book
        self.stdout.write(f"Final Order Book State:")
        self.stdout.write(f"  Last Price: ${order_book.last_trade_price}")
        self.stdout.write(f"  Daily Volume: {order_book.daily_volume}")
        self.stdout.write(f"  Trade Count: {order_book.trade_count}")
        self.stdout.write(f"  Daily Range: ${order_book.daily_low} - ${order_book.daily_high}\n")
        
        # Show portfolio changes
        for user in users:
            profile = user.simulation_profile
            positions = user.simulated_positions.filter(instrument=instrument)
            
            self.stdout.write(f"{user.username} Final State:")
            self.stdout.write(f"  Cash: ${profile.virtual_cash_balance}")
            self.stdout.write(f"  Portfolio Value: ${profile.current_portfolio_value}")
            
            if positions.exists():
                for pos in positions:
                    unrealized = pos.unrealized_pnl
                    self.stdout.write(f"  {instrument.real_ticker.symbol}: {pos.quantity} shares @ ${pos.average_cost}")
                    self.stdout.write(f"    Market Value: ${pos.market_value}")
                    self.stdout.write(f"    Unrealized P&L: ${unrealized}")
            
            # Show recent orders
            recent_orders = user.simulated_orders.filter(
                instrument=instrument
            ).order_by('-order_timestamp')[:3]
            
            if recent_orders:
                self.stdout.write(f"  Recent Orders:")
                for order in recent_orders:
                    status_color = self.style.SUCCESS if order.status == 'FILLED' else self.style.WARNING
                    self.stdout.write(f"    {status_color(order.side)} {order.quantity} @ ${order.price or 'MARKET'} - {order.status}")
            
            self.stdout.write()


    def execute_trading_workflow(self, instrument, users, num_trades, delay):
        """Execute the main trading workflow"""
        self.stdout.write(self.style.WARNING('=== EXECUTING LIVE TRADES ===\n'))
        
        matching_service = OrderMatchingService()
        
        for trade_num in range(1, num_trades + 1):
            self.stdout.write(f"--- Trade {trade_num}/{num_trades} ---")
            
            # Random order parameters
            user = random.choice(users)
            side = random.choice(['BUY', 'SELL'])
            quantity = random.randint(10, 100)
            order_type = random.choice(['MARKET', 'LIMIT'])
            
            # Get current market price for limit orders
            current_price = instrument.order_book.last_trade_price
            if order_type == 'LIMIT':
                # Add some price variation for limit orders
                price_variation = random.uniform(-0.02, 0.02)  # ±2%
                limit_price = current_price * (1 + Decimal(str(price_variation)))
            else:
                limit_price = None
            
            self.stdout.write(f"Creating {side} order for {user.username}:")
            self.stdout.write(f"  Type: {order_type}")
            self.stdout.write(f"  Quantity: {quantity}")
            if limit_price:
                self.stdout.write(f"  Limit Price: ${limit_price:.2f}")
            self.stdout.write(f"  Market Price: ${current_price}")
            
            # Create the order
            order = SimulatedOrder.objects.create(
                user=user,
                exchange=instrument.exchange,
                instrument=instrument,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=limit_price,
                time_in_force='GTC'
            )
            
            # Submit order for matching
            self.stdout.write("Submitting to matching engine...")
            
            success, message, violations = matching_service.submit_order(order)
            
            if success:
                order.refresh_from_db()
                if order.status == 'FILLED':
                    self.stdout.write(self.style.SUCCESS(f"✓ ORDER FILLED: {order.filled_quantity}/{order.quantity} shares"))
                    
                    # Show trade details
                    fills = order.fills.all()
                    for fill in fills:
                        self.stdout.write(f"  Fill: {fill.quantity} @ ${fill.price}")
                elif order.status == 'PARTIALLY_FILLED':
                    self.stdout.write(self.style.WARNING(f"◐ PARTIALLY FILLED: {order.filled_quantity}/{order.quantity} shares"))
                else:
                    self.stdout.write(self.style.HTTP_INFO(f"○ Order acknowledged: {order.status}"))
            else:
                self.stdout.write(self.style.ERROR(f"✗ ORDER REJECTED: {message}"))
                if violations:
                    for violation in violations:
                        self.stdout.write(f"  Risk violation: {violation}")
            
            # Show updated order book
            order_book = instrument.order_book
            self.stdout.write(f"Order Book Update:")
            self.stdout.write(f"  Last Trade: ${order_book.last_trade_price} (Vol: {order_book.daily_volume})")
            self.stdout.write(f"  Bid/Ask: ${order_book.best_bid_price}/${order_book.best_ask_price}")
            
            # Show recent trades
            recent_trades = SimulatedTrade.objects.filter(
                instrument=instrument
            ).order_by('-trade_timestamp')[:2]
            
            if recent_trades:
                self.stdout.write("Recent Trades:")
                for trade in recent_trades:
                    age = (timezone.now() - trade.trade_timestamp).total_seconds()
                    self.stdout.write(f"  {trade.quantity} @ ${trade.price} ({age:.0f}s ago)")
            
            self.stdout.write()
            
            # Delay before next trade
            if trade_num < num_trades:
                self.stdout.write(f"Waiting {delay}s before next trade...")
                time.sleep(delay)
                self.stdout.write()
