# apps/trading_simulation/management/commands/demo_institutional_platform.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.trading_simulation.models import SimulatedInstrument
from apps.order_management.models import SimulatedOrder, OrderBookLevel, OrderQueue
from apps.order_management.services import OrderMatchingService
from apps.market_data.services import YFinanceService, DataIngestionService
from apps.market_data.streaming.service import streaming_engine
from apps.market_data.models import Ticker, MarketData
from apps.market_data.technical_analysis import TechnicalAnalysisCalculator
from decimal import Decimal, InvalidOperation
import time
import asyncio
import random
import traceback

User = get_user_model()

class Command(BaseCommand):
    help = 'Comprehensive institutional trading platform demonstration with real market data'
    
    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='AAPL')
        parser.add_argument('--trades', type=int, default=15)
        parser.add_argument('--enable-streaming', action='store_true',
                          help='Enable real-time streaming engine')
        parser.add_argument('--technical-analysis', action='store_true',
                          help='Show technical analysis integration')
        parser.add_argument('--delay', type=float, default=1.5)
    
    def handle(self, *args, **options):
        symbol = options['symbol'].upper()
        num_trades = options['trades']
        enable_streaming = options['enable_streaming']
        show_ta = options['technical_analysis']
        delay = options['delay']
        
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('TRADING PLATFORM DEMONSTRATION'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(f"Symbol: {symbol}")
        self.stdout.write(f"Trading Orders: {num_trades}")
        self.stdout.write(f"Real-time Streaming: {'Enabled' if enable_streaming else 'Disabled'}")
        self.stdout.write(f"Technical Analysis: {'Enabled' if show_ta else 'Disabled'}")
        self.stdout.write()
        
        # Initialize services
        self.yfinance_service = YFinanceService()
        self.data_ingestion_service = DataIngestionService()
        self.matching_service = OrderMatchingService()
        
        # Get or create instrument
        instrument = self.get_or_create_instrument(symbol)
        if not instrument:
            self.stdout.write(self.style.ERROR(f"Could not create instrument for {symbol}"))
            return
        
        # Get real current market price
        real_price = self.get_live_market_price(symbol)
        if not real_price:
            self.stdout.write(self.style.ERROR("Could not fetch live market price"))
            return
        
        # Show platform initialization
        self.show_platform_initialization(symbol, real_price, enable_streaming)
        
        # Initialize streaming if requested
        if enable_streaming:
            self.initialize_streaming(symbol)
        
        # Show technical analysis if requested
        if show_ta:
            self.demonstrate_technical_analysis(symbol)
        
        # Clear order book for clean demo
        self.clear_order_book(instrument)
        
        # Get demo users
        users = self.get_demo_users()
        
        # Show initial state
        self.show_platform_state(instrument, users, "INITIAL SETUP")
        
        # Execute institutional trading workflow
        self.execute_institutional_workflow(
            instrument, users, real_price, num_trades, delay
        )
        
        # Show final analysis
        self.show_final_analysis(instrument, users, real_price)
        
        # Cleanup streaming if enabled
        if enable_streaming:
            self.cleanup_streaming()
    
    def get_or_create_instrument(self, symbol):
        """Get or create trading instrument with real market data"""
        try:
            # Try to get existing instrument
            instrument = SimulatedInstrument.objects.get(real_ticker__symbol=symbol)
            self.stdout.write(f"✅ Found existing instrument: {symbol}")
            return instrument
            
        except SimulatedInstrument.DoesNotExist:
            # Create new ticker and instrument
            self.stdout.write(f"🔄 Creating new instrument for {symbol}...")
            
            ticker = self.data_ingestion_service.create_or_update_ticker(symbol)
            if not ticker:
                return None
            
            # Find a simulated exchange
            from apps.trading_simulation.models import SimulatedExchange
            exchange = SimulatedExchange.objects.first()
            if not exchange:
                self.stdout.write(self.style.ERROR("No simulated exchanges found"))
                return None
            
            # Create simulated instrument
            instrument = SimulatedInstrument.objects.create(
                real_ticker=ticker,
                exchange=exchange,
                is_tradeable=True,
                minimum_order_size=1,
                maximum_order_size=10000,
                price_increment=Decimal('0.01')
            )
            
            self.stdout.write(f"✅ Created new instrument: {symbol}")
            return instrument
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error with instrument {symbol}: {str(e)}"))
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return None
    
    def get_live_market_price(self, symbol):
        """Get real live market price from Yahoo Finance"""
        try:
            self.stdout.write(f"🔍 Fetching live market data for {symbol}...")
            
            quote_data = self.yfinance_service.get_real_time_quote(symbol)
            if not quote_data:
                self.stdout.write(self.style.WARNING(f"No quote data returned for {symbol}"))
                return None
                
            if not quote_data.get('price'):
                self.stdout.write(self.style.WARNING(f"No price data in quote for {symbol}"))
                return None
            
            try:
                price = Decimal(str(quote_data['price']))
            except (TypeError, ValueError, InvalidOperation) as e:
                self.stdout.write(self.style.ERROR(f"Invalid price data: {quote_data.get('price')} - {e}"))
                return None
            
            self.stdout.write(f"LIVE MARKET PRICE: ${price}")
            self.stdout.write(f"Volume: {quote_data.get('volume', 'N/A'):,}")
            self.stdout.write(f"Change: {quote_data.get('change', 'N/A')}")
            self.stdout.write(f"Market Cap: ${quote_data.get('market_cap', 'N/A'):,}")
            
            return price
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching live price: {str(e)}"))
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return None
    
    def show_platform_initialization(self, symbol, price, streaming_enabled):
        """Show comprehensive platform initialization"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("🏗️  PLATFORM INITIALIZATION"))
        self.stdout.write("=" * 60)
        
        self.stdout.write(f"Live Price Feed: ${price} ({symbol})")
        
        # Streaming status
        if streaming_enabled:
            self.stdout.write(f"🚀 Streaming Engine: Starting streaming...")
        else:
            self.stdout.write(f"📋 Streaming Engine: Disabled for this demo")
        
        self.stdout.write()
    
    def initialize_streaming(self, symbol):
        """Initialize real-time streaming engine"""
        try:
            self.stdout.write(f"🚀 Initializing streaming for {symbol}...")
            
            # Subscribe to symbol
            streaming_engine.subscribe_symbol(symbol, high_frequency=True)
            
            # Fix: Handle async call properly
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the coroutine in the event loop
            loop.run_until_complete(streaming_engine.start())
            
            self.stdout.write(f"✅ Streaming engine active")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Streaming initialization failed: {e}"))
    
    def demonstrate_technical_analysis(self, symbol):
        """Show technical analysis integration"""
        try:
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write(self.style.HTTP_INFO("📈 TECHNICAL ANALYSIS INTEGRATION"))
            self.stdout.write("=" * 50)
            
            # Fix: Handle multiple tickers properly
            try:
                ta_calc = TechnicalAnalysisCalculator(symbol)
            except Exception as ticker_error:
                self.stdout.write(f"Technical analysis initialization failed: {ticker_error}")
                return
            
            # Calculate RSI
            try:
                rsi_data = ta_calc.calculate_rsi(period=14)
                current_rsi = rsi_data.get('current_value', 'N/A')
                self.stdout.write(f"RSI (14): {current_rsi}")
                
                if isinstance(current_rsi, (int, float)):
                    if current_rsi > 70:
                        self.stdout.write(f"🔴 Signal: OVERBOUGHT (RSI > 70)")
                    elif current_rsi < 30:
                        self.stdout.write(f"🟢 Signal: OVERSOLD (RSI < 30)")
                    else:
                        self.stdout.write(f"🟡 Signal: NEUTRAL (30 < RSI < 70)")
            except Exception as rsi_error:
                self.stdout.write(f"📊 RSI: Calculation error - {rsi_error}")
            
            # Calculate moving averages
            try:
                sma_data = ta_calc.calculate_sma(period=20)
                current_sma = sma_data.get('current_value', 'N/A')
                self.stdout.write(f"📈 SMA (20): ${current_sma}")
            except Exception as sma_error:
                self.stdout.write(f"📈 SMA (20): Calculation error - {sma_error}")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Technical analysis demo failed: {e}"))
        
        self.stdout.write()
    
    def clear_order_book(self, instrument):
        """Clear existing order book for clean demo"""
        OrderBookLevel.objects.filter(order_book=instrument.order_book).delete()
        self.stdout.write(f"🧹 Order book cleared.")
    
    def get_demo_users(self):
        """Get demo trading users"""
        users = list(User.objects.filter(username__startswith='demo_trader_'))
        if len(users) < 2:
            self.stdout.write(self.style.ERROR("Need at least 2 demo users"))
            return []
        return users
    
    def show_platform_state(self, instrument, users, stage):
        """Show comprehensive platform state"""
        order_book = instrument.order_book
        
        self.stdout.write(f"\nPLATFORM STATE: {stage}")
        self.stdout.write("─" * 50)
        
        # Market data
        self.stdout.write(f"Last Trade: ${order_book.last_trade_price or 'None'}")
        self.stdout.write(f"Daily Volume: {order_book.daily_volume:,} shares")
        self.stdout.write(f"Daily Range: ${order_book.daily_low or 'N/A'} - ${order_book.daily_high or 'N/A'}")
        
        # Order book depth
        self.show_order_book(instrument)
        
        # Portfolio summary
        self.show_portfolio_summary(users, instrument)
        
        self.stdout.write()
    
    def show_order_book(self, instrument):
        """Show professional order book display"""
        order_book = instrument.order_book
        
        # Get order book levels
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='BUY', quantity__gt=0
        ).order_by('-price')[:5]
        
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='SELL', quantity__gt=0
        ).order_by('price')[:5]
        
        # Calculate spread
        if order_book.best_bid_price and order_book.best_ask_price:
            spread = order_book.best_ask_price - order_book.best_bid_price
            spread_bps = (spread / order_book.best_ask_price) * Decimal('10000')
            self.stdout.write(f"Spread: ${spread:.3f} ({spread_bps:.1f} bps)")
        
        # Professional order book display
        self.stdout.write(f"ORDER BOOK DEPTH:")
        self.stdout.write(f"        {'BID SIDE (Buyers)':^25} | {'ASK SIDE (Sellers)':^25}")
        self.stdout.write(f"       {'Price':>8} {'Size':>6} {'Orders':>6} | {'Price':>8} {'Size':>6} {'Orders':>6}")
        self.stdout.write(f"    {'-' * 23} | {'-' * 23}")
        
        max_levels = max(len(bid_levels), len(ask_levels))
        for i in range(max_levels):
            bid_str = "                       "
            ask_str = "                       "
            
            if i < len(bid_levels):
                bid = bid_levels[i]
                bid_str = f"    ${bid.price:7.2f} {bid.quantity:5d} {bid.order_count:5d}"
            
            if i < len(ask_levels):
                ask = ask_levels[i]
                ask_str = f"    ${ask.price:7.2f} {ask.quantity:5d} {ask.order_count:5d}"
            
            self.stdout.write(f"{bid_str} |{ask_str}")
    
    def show_portfolio_summary(self, users, instrument):
        """Show portfolio summary for all users"""
        self.stdout.write(f"PORTFOLIO SUMMARY:")
        
        for user in users:
            try:
                profile = user.simulation_profile
                
                # Fix: Refresh/recalculate portfolio values
                profile.refresh_from_db()
                if hasattr(profile, 'update_portfolio_value'):
                    profile.update_portfolio_value()
                
                positions = user.simulated_positions.filter(instrument=instrument)
                
                portfolio_value = profile.current_portfolio_value
                cash = profile.virtual_cash_balance
                
                self.stdout.write(f"{user.username}:")
                self.stdout.write(f"    💰 Cash: ${cash:,.2f}")
                self.stdout.write(f"    📈 Portfolio: ${portfolio_value:,.2f}")
                
                if positions.exists():
                    for pos in positions:
                        pnl_color = self.style.SUCCESS if pos.unrealized_pnl >= 0 else self.style.ERROR
                        self.stdout.write(f"    🔹 {instrument.real_ticker.symbol}: {pos.quantity} shares")
                        self.stdout.write(f"      Cost: ${pos.average_cost:.2f} | "
                                        f"Market: ${pos.current_price or 'N/A'} | "
                                        f"P&L: {pnl_color(f'${pos.unrealized_pnl:+.2f}')}")
            except Exception as e:
                self.stdout.write(f"{user.username}: Error loading portfolio - {e}")
    
    def execute_institutional_workflow(self, instrument, users, base_price, num_trades, delay):
        """Execute trading workflow"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("🏛️  TRADING WORKFLOW"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Executing {num_trades} trading operations...")
        self.stdout.write(f"Base price: ${base_price} (live market data)")
        self.stdout.write()
        
        for i in range(1, num_trades + 1):
            try:
                # Get updated market price (simulate real-time updates)
                current_price = self.get_current_market_price(base_price, i)
                
                # Generate institutional-style order
                order_params = self.generate_order(users, current_price, i)
                
                self.stdout.write(f"--- Trade {i}/{num_trades} ---")
                self.show_order_details(order_params, current_price)
                
                # Create and submit order
                order = self.create_order(instrument, **order_params)
                
                try:
                    success, message, violations = self.matching_service.submit_order(order)
                except Exception as matching_error:
                    self.stdout.write(self.style.ERROR(f"Order matching failed: {matching_error}"))
                    continue
                
                # Show execution results
                self.show_execution_results(order, success, message)
                
                # Show market impact
                self.show_market_impact(instrument, i)
                
                # Brief delay for realism
                time.sleep(delay)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error in trade {i}: {str(e)}"))
                self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
                continue
    
    def get_current_market_price(self, base_price, trade_num):
        """Simulate market price movement"""
        # Add some realistic price movement
        volatility = 0.002  # 0.2% volatility
        drift = random.uniform(-volatility, volatility)
        return base_price * (Decimal('1') + Decimal(str(drift)))
    
    def generate_order(self, users, current_price, trade_num):
        """Generate sophisticated institutional order parameters"""
        user = random.choice(users)
        
        # Institutional order patterns
        order_types = ['LIMIT', 'LIMIT', 'LIMIT', 'MARKET']  # Favor limit orders
        sides = ['BUY', 'SELL']
        
        # Professional quantity patterns
        quantity_patterns = [
            100, 150, 200, 250, 500, 750, 1000,  # Round lots
            175, 225, 275, 375,  # Odd lots
            1500, 2000, 2500  # Block orders
        ]
        
        order_type = random.choice(order_types)
        side = random.choice(sides)
        quantity = random.choice(quantity_patterns)
        
        # Professional pricing strategy
        if order_type == 'LIMIT':
            if side == 'BUY':
                # Buy slightly below market
                price_discount_bps = random.randint(5, 100)  # 5-100 bps below
                discount_factor = Decimal(str(price_discount_bps / 10000))
                price = current_price * (Decimal('1') - discount_factor)
            else:
                # Sell slightly above market
                price_premium_bps = random.randint(5, 80)  # 5-80 bps above
                premium_factor = Decimal(str(price_premium_bps / 10000))
                price = current_price * (Decimal('1') + premium_factor)
        else:
            price = None
        
        return {
            'user': user,
            'side': side,
            'order_type': order_type,
            'quantity': quantity,
            'price': price
        }
    
    def show_order_details(self, order_params, market_price):
        """Show detailed order information"""
        user = order_params['user']
        side = order_params['side']
        order_type = order_params['order_type']
        quantity = order_params['quantity']
        price = order_params['price']
        
        # Calculate order value
        order_value = quantity * (price or market_price)
        
        self.stdout.write(f"👤 Trader: {user.username}")
        self.stdout.write(f"📋 Order: {side} {quantity:,} shares @ {order_type}")
        
        if price:
            price_diff = ((price - market_price) / market_price) * Decimal('10000')
            self.stdout.write(f"💰 Limit Price: ${price:.3f} ({price_diff:+.1f} bps from market)")
        else:
            self.stdout.write(f"💰 Market Order: ${market_price:.3f}")
        
        self.stdout.write(f"💵 Notional Value: ${order_value:,.2f}")
    
    def create_order(self, instrument, user, side, order_type, quantity, price):
        """Create order object"""
        return SimulatedOrder.objects.create(
            user=user,
            exchange=instrument.exchange,
            instrument=instrument,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force='GTC'
        )
    
    def show_execution_results(self, order, success, message):
        """Show order execution results"""
        if success:
            if order.status == 'FILLED':
                self.stdout.write(self.style.SUCCESS(f"✅ FILLED: {order.filled_quantity}/{order.quantity} shares"))
                
                # Show fills
                fills = order.fills.all()
                for fill in fills:
                    self.stdout.write(f"  💰 Fill: {fill.quantity} @ ${fill.price:.3f}")
                    
            elif order.status == 'PARTIALLY_FILLED':
                self.stdout.write(self.style.WARNING(f"◐ PARTIAL: {order.filled_quantity}/{order.quantity} shares"))
            else:
                self.stdout.write(f"📋 ACKNOWLEDGED: Order in book")
        else:
            self.stdout.write(self.style.ERROR(f"❌ REJECTED: {message}"))
    
    def show_market_impact(self, instrument, trade_num):
        """Show market impact of the trade"""
        # Fix: Refresh order book from database
        order_book = instrument.order_book
        order_book.refresh_from_db()
        
        self.stdout.write(f"📊 Market Impact:")
        self.stdout.write(f"  Last Price: ${order_book.last_trade_price or 'N/A'}")
        self.stdout.write(f"  Volume: {order_book.daily_volume:,} shares")
        self.stdout.write(f"  Best Bid: ${order_book.best_bid_price or 'None'}")
        self.stdout.write(f"  Best Ask: ${order_book.best_ask_price or 'None'}")
        
        if order_book.best_bid_price and order_book.best_ask_price:
            spread = order_book.best_ask_price - order_book.best_bid_price
            spread_bps = (spread / order_book.last_trade_price) * Decimal('10000') if order_book.last_trade_price else Decimal('0')
            
            if spread_bps < 10:
                quality = self.style.SUCCESS("Excellent")
            elif spread_bps < 30:
                quality = self.style.WARNING("Good")
            else:
                quality = self.style.ERROR("Wide")
            
            self.stdout.write(f"  Market Quality: {quality} ({spread_bps:.1f} bps)")
        
        self.stdout.write()
    
    def show_final_analysis(self, instrument, users, original_price):
        """Show comprehensive final analysis"""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("📊 FINAL INSTITUTIONAL ANALYSIS"))
        self.stdout.write("=" * 70)
        
        order_book = instrument.order_book
        order_book.refresh_from_db()
        
        # Price movement analysis
        if order_book.last_trade_price:
            price_change = order_book.last_trade_price - original_price
            price_change_pct = (price_change / original_price) * Decimal('100')
            
            if price_change > 0:
                direction = self.style.SUCCESS("📈 BULLISH")
            elif price_change < 0:
                direction = self.style.ERROR("📉 BEARISH")
            else:
                direction = self.style.WARNING("➡️  NEUTRAL")
            
            self.stdout.write(f"💹 PRICE DISCOVERY:")
            self.stdout.write(f"  Market Open: ${original_price:.3f}")
            self.stdout.write(f"  Current: ${order_book.last_trade_price:.3f}")
            self.stdout.write(f"  Change: {direction} ${price_change:+.3f} ({price_change_pct:+.3f}%)")
        
        # Trading activity
        self.stdout.write(f"\n📊 TRADING ACTIVITY:")
        self.stdout.write(f"  Total Volume: {order_book.daily_volume:,} shares")
        self.stdout.write(f"  Trade Count: {order_book.trade_count}")
        
        if order_book.trade_count > 0:
            avg_trade_size = order_book.daily_volume / order_book.trade_count
            self.stdout.write(f"  Average Size: {avg_trade_size:.0f} shares/trade")
        
        # Order book analysis
        bid_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='BUY'
        ).count()
        ask_levels = OrderBookLevel.objects.filter(
            order_book=order_book, side='SELL'
        ).count()
        
        self.stdout.write(f"\n🏗️  ORDER BOOK DEPTH:")
        self.stdout.write(f"  Bid Levels: {bid_levels}")
        self.stdout.write(f"  Ask Levels: {ask_levels}")
        
        if bid_levels > ask_levels:
            self.stdout.write(f"  Flow: {self.style.SUCCESS('BUYING PRESSURE dominant')}")
        elif ask_levels > bid_levels:
            self.stdout.write(f"  Flow: {self.style.ERROR('SELLING PRESSURE dominant')}")
        else:
            self.stdout.write(f"  Flow: {self.style.WARNING('BALANCED order flow')}")
        
        # Show final portfolio state
        self.stdout.write(f"\n👥 FINAL PORTFOLIO STATE:")
        self.show_portfolio_summary(users, instrument)
        
        # Success summary
        self.stdout.write(f"\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("🎯 DEMONSTRATION COMPLETE"))
        self.stdout.write("=" * 70)
        
    def cleanup_streaming(self):
        """Cleanup streaming engine"""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            loop.run_until_complete(streaming_engine.stop())
            self.stdout.write(f"🛑 Streaming engine stopped")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Streaming cleanup error: {e}"))
