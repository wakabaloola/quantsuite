# apps/trading_simulation/management/commands/demo_setup_real_simulation.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.trading_simulation.services import (
    SimulatedExchangeService, UserTradingService, SimulationMonitoringService
)
from apps.trading_simulation.models import SimulatedExchange, SimulatedInstrument
from apps.market_data.models import Exchange, Ticker
from apps.order_management.models import OrderBook
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Set up real trading simulation environment with actual market data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=3,
            help='Number of demo users to create'
        )
        parser.add_argument(
            '--balance',
            type=float,
            default=100000.00,
            help='Initial virtual balance per user'
        )


    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== REAL TRADING SIMULATION SETUP ===\n'))

        # --- CLEANUP BLOCK ---
        self.stdout.write(self.style.WARNING('Clearing old simulation data...'))
        OrderBook.objects.all().delete()
        SimulatedInstrument.objects.all().delete()
        SimulatedExchange.objects.all().delete()
        User.objects.filter(username__startswith='demo_trader').delete()
        self.stdout.write(self.style.SUCCESS('✓ Old data cleared.\n'))
        # --- END OF CLEANUP BLOCK ---

        num_users = options['users']
        initial_balance = Decimal(str(options['balance']))

        # Show current state
        self.show_current_state()

        # Set up simulated exchanges
        self.setup_simulated_exchanges()

        # Set up demo users
        users = self.setup_demo_users(num_users, initial_balance)

        # Add real instruments to simulation
        self.setup_simulated_instruments()

        # Show final state
        self.show_simulation_ready_state()

        self.stdout.write(self.style.SUCCESS('\n=== SIMULATION ENVIRONMENT READY ==='))


    def show_current_state(self):
        self.stdout.write(self.style.HTTP_INFO('--- Current State ---'))
        self.stdout.write(f"Real Exchanges: {Exchange.objects.count()}")
        self.stdout.write(f"Real Tickers: {Ticker.objects.count()}")
        self.stdout.write(f"Simulated Exchanges: {SimulatedExchange.objects.count()}")
        self.stdout.write(f"Simulated Instruments: {SimulatedInstrument.objects.count()}")
        self.stdout.write()

    def setup_simulated_exchanges(self):
        self.stdout.write(self.style.WARNING('Setting up simulated exchanges...'))
        
        exchange_service = SimulatedExchangeService()
        
        # Get real exchanges and create simulated versions
        real_exchanges = Exchange.objects.all()[:5]  # Limit to first 5
        
        for real_exchange in real_exchanges:
            sim_exchange, created = SimulatedExchange.objects.get_or_create(
                code=f"SIM_{real_exchange.code}",
                defaults={
                    'name': f"Simulated {real_exchange.name}",
                    'real_exchange': real_exchange,
                    'status': 'ACTIVE',
                    'trading_fee_percentage': Decimal('0.001')  # 0.1% fee
                }
            )
            
            if created:
                self.stdout.write(f"✓ Created: {sim_exchange.name}")
            else:
                self.stdout.write(f"- Exists: {sim_exchange.name}")
        
        self.stdout.write()

    def setup_demo_users(self, num_users, initial_balance):
        self.stdout.write(self.style.WARNING(f'Setting up {num_users} demo users...'))
        
        user_service = UserTradingService()
        users = []
        
        for i in range(1, num_users + 1):
            username = f"demo_trader_{i}"
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@demo.local',
                    'first_name': f'Demo',
                    'last_name': f'Trader{i}'
                }
            )
            
            if created:
                user.set_password('demo123')
                user.save()
                self.stdout.write(f"✓ Created user: {username}")
            else:
                self.stdout.write(f"- Exists user: {username}")
            
            # Initialize trading profile
            profile = user_service.initialize_user_profile(user, initial_balance)
            self.stdout.write(f"  └─ Virtual balance: ${profile.virtual_cash_balance}")
            
            users.append(user)
        
        self.stdout.write()
        return users

    def setup_simulated_instruments(self):
        self.stdout.write(self.style.WARNING('Setting up simulated instruments...'))
        
        exchange_service = SimulatedExchangeService()
        
        # Get tickers with market data
        tickers_with_data = Ticker.objects.filter(market_data__isnull=False).distinct()[:10]
        sim_exchanges = SimulatedExchange.objects.all()
        
        instruments_created = 0
        
        for ticker in tickers_with_data:
            # Use the ticker's real exchange if we have a sim version, otherwise use first sim exchange
            sim_exchange = sim_exchanges.filter(
                real_exchange=ticker.exchange
            ).first() or sim_exchanges.first()
            
            if sim_exchange:
                instrument, created = SimulatedInstrument.objects.get_or_create(
                    real_ticker=ticker,
                    exchange=sim_exchange,
                    defaults={
                        'is_tradable': True,
                        'price_multiplier': Decimal('1.0'),
                        'volatility_multiplier': Decimal('1.0')
                    }
                )

                # Ensure an order book exists, regardless of whether the instrument is new
                OrderBook.objects.get_or_create(instrument=instrument)
                
                if created:
                    # Create order book
                    self.stdout.write(f"✓ Added: {ticker.symbol} to {sim_exchange.code}")
                    instruments_created += 1
                else:
                    self.stdout.write(f"- Exists: {ticker.symbol} in {sim_exchange.code}")
        
        self.stdout.write(f"Total instruments created: {instruments_created}")
        self.stdout.write()

    def show_simulation_ready_state(self):
        self.stdout.write(self.style.SUCCESS('--- Simulation Environment Status ---'))
        
        sim_exchanges = SimulatedExchange.objects.count()
        sim_instruments = SimulatedInstrument.objects.count()
        demo_users = User.objects.filter(username__startswith='demo_trader').count()
        order_books = OrderBook.objects.count()
        
        self.stdout.write(f"Simulated Exchanges: {sim_exchanges}")
        self.stdout.write(f"Simulated Instruments: {sim_instruments}")  
        self.stdout.write(f"Demo Users: {demo_users}")
        self.stdout.write(f"Order Books: {order_books}")
        
        # Show some sample instruments
        instruments = SimulatedInstrument.objects.select_related('real_ticker', 'exchange')[:5]
        self.stdout.write("\nSample tradable instruments:")
        for instrument in instruments:
            latest_price = instrument.order_book.last_trade_price or "No price"
            self.stdout.write(f"  {instrument.real_ticker.symbol}: {latest_price} on {instrument.exchange.code}")



 
