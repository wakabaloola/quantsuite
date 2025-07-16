from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.order_management.models import AlgorithmicOrder, AlgorithmExecution, CustomStrategy, StrategyBacktest
from apps.trading_simulation.models import SimulatedExchange, SimulatedInstrument
from apps.market_data.models import Exchange, Ticker, Sector, Industry, DataSource
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

User = get_user_model()


class AlgorithmicOrderModelTestCase(TestCase):
    """Test cases for AlgorithmicOrder models"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='algo_trader', 
            email='algo@test.com'
        )
        
        # Create required related objects with correct field names
        self.real_exchange = Exchange.objects.create(
            name='Test Exchange', 
            code='TEST'
        )
        
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', 
            code='SIM_TEST', 
            real_exchange=self.real_exchange
        )
        
        # Create Sector - has both name and code fields
        self.sector = Sector.objects.create(
            name='Technology',
            code='TECH'
        )
        
        # Create Industry - only has name and sector fields (no code field)
        self.industry = Industry.objects.create(
            name='Consumer Electronics',
            sector=self.sector
        )
        
        # Create DataSource - has all the required fields
        self.data_source = DataSource.objects.create(
            name='Test Data Source',
            code='TEST_DS',
            url='https://test.example.com',
            api_endpoint='https://api.test.example.com',
            requires_api_key=False,
            rate_limit_per_minute=60,
            supported_markets=['US', 'NASDAQ'],
            supported_timeframes=['1m', '5m', '1h', '1d'],
            is_active=True
        )
        
        # Create Ticker with all required fields
        self.real_ticker = Ticker.objects.create(
            symbol='AAPL',
            name='Apple Inc.',
            description='Apple Inc. manufactures consumer electronics',
            exchange=self.real_exchange,
            sector=self.sector,
            industry=self.industry,
            currency='USD',
            country='US',
            data_source=self.data_source,
            yfinance_symbol='AAPL',
            alpha_vantage_symbol='AAPL',
            market_cap=Decimal('3000000000000.00'),
            shares_outstanding=Decimal('16000000000.00'),
            last_updated=timezone.now()
        )
        
        self.sim_instrument = SimulatedInstrument.objects.create(
            real_ticker=self.real_ticker, 
            exchange=self.sim_exchange
        )
    
    def test_twap_order_creation(self):
        """Test TWAP algorithmic order creation"""
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=2)
        
        twap_params = {
            'slice_count': 10,
            'price_improvement_bps': 5,
            'max_participation_rate': 0.20,
            'randomize_timing': False
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=start_time,
            end_time=end_time,
            algorithm_parameters=twap_params,
            min_slice_size=50,
            max_slice_size=200,
            limit_price=Decimal('150.00')
        )
        
        self.assertEqual(algo_order.algorithm_type, 'TWAP')
        self.assertEqual(algo_order.remaining_quantity, 1000)
        self.assertEqual(algo_order.fill_ratio, 0)
        self.assertEqual(algo_order.duration_minutes, 120)
        self.assertEqual(algo_order.status, 'PENDING')
        self.assertEqual(algo_order.algorithm_parameters['slice_count'], 10)
        
        # Test string representation
        self.assertIn('TWAP', str(algo_order))
        self.assertIn('AAPL', str(algo_order))
    
    def test_vwap_order_creation(self):
        """Test VWAP algorithmic order creation"""
        vwap_params = {
            'volume_profile': 'HISTORICAL',
            'lookback_days': 20,
            'aggressive_factor': 1.2
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters=vwap_params
        )
        
        self.assertEqual(algo_order.algorithm_type, 'VWAP')
        self.assertEqual(algo_order.side, 'SELL')
        self.assertEqual(algo_order.total_quantity, 500)
    
    def test_iceberg_order_creation(self):
        """Test Iceberg algorithmic order creation"""
        iceberg_params = {
            'display_size': 100,
            'refresh_threshold': 0.5,
            'randomize_display': True
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='ICEBERG',
            side='BUY',
            total_quantity=2000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=4),
            algorithm_parameters=iceberg_params
        )
        
        self.assertEqual(algo_order.algorithm_type, 'ICEBERG')
        self.assertEqual(algo_order.total_quantity, 2000)
        self.assertEqual(algo_order.algorithm_parameters['display_size'], 100)
    
    def test_sniper_order_creation(self):
        """Test Sniper algorithmic order creation"""
        sniper_params = {
            'max_spread_bps': 15,
            'min_volume': 1000,
            'patience_seconds': 300
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='SNIPER',
            side='BUY',
            total_quantity=200,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters=sniper_params,
            limit_price=Decimal('148.00')
        )
        
        self.assertEqual(algo_order.algorithm_type, 'SNIPER')
        self.assertEqual(algo_order.total_quantity, 200)
        self.assertEqual(algo_order.algorithm_parameters['max_spread_bps'], 15)
    
    def test_algorithm_execution_creation(self):
        """Test AlgorithmExecution model"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1)
        )
        
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now() + timedelta(minutes=6),
            market_price=Decimal('149.50'),
            market_volume=5000,
            spread_bps=Decimal('8.50'),
            executed_quantity=100,
            execution_price=Decimal('149.52'),
            slippage_bps=Decimal('1.33')
        )
        
        self.assertEqual(execution.algo_order, algo_order)
        self.assertEqual(execution.execution_step, 1)
        self.assertEqual(execution.executed_quantity, 100)
        self.assertEqual(execution.slippage_bps, Decimal('1.33'))
        
        # Test string representation
        self.assertIn('Execution 1', str(execution))
    
    def test_multiple_executions(self):
        """Test multiple executions for one algorithm"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2)
        )
        
        # Create multiple executions
        executions = []
        for i in range(5):
            execution = AlgorithmExecution.objects.create(
                algo_order=algo_order,
                execution_step=i + 1,
                scheduled_time=timezone.now() + timedelta(minutes=12 * (i + 1)),
                market_price=Decimal('149.50') + Decimal('0.10') * i,
                executed_quantity=200
            )
            executions.append(execution)
        
        # Test relationships
        self.assertEqual(algo_order.executions.count(), 5)
        self.assertEqual(list(algo_order.executions.all()), executions)
    
    def test_json_field_functionality(self):
        """Test JSON field storage and retrieval"""
        params = {
            'slice_count': 15,
            'nested_param': {'sub_param': 'value', 'number': 42},
            'list_param': [1, 2, 3],
            'boolean_param': True,
            'float_param': 3.14159
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters=params
        )
        
        # Test nested access
        self.assertEqual(
            algo_order.algorithm_parameters['nested_param']['sub_param'], 
            'value'
        )
        self.assertEqual(
            algo_order.algorithm_parameters['nested_param']['number'], 
            42
        )
        self.assertEqual(algo_order.algorithm_parameters['list_param'], [1, 2, 3])
        self.assertTrue(algo_order.algorithm_parameters['boolean_param'])
        self.assertAlmostEqual(algo_order.algorithm_parameters['float_param'], 3.14159)
        
        # Test parameter update
        algo_order.algorithm_parameters['new_param'] = 'new_value'
        algo_order.algorithm_parameters['nested_param']['new_sub'] = 'updated'
        algo_order.save()
        
        # Refresh and verify
        algo_order.refresh_from_db()
        self.assertEqual(algo_order.algorithm_parameters['new_param'], 'new_value')
        self.assertEqual(algo_order.algorithm_parameters['nested_param']['new_sub'], 'updated')
    
    def test_model_properties(self):
        """Test model properties and calculated fields"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.sim_instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            executed_quantity=250
        )
        
        # Test calculated properties
        self.assertEqual(algo_order.fill_ratio, 25.0)
        self.assertEqual(algo_order.remaining_quantity, 750)
        self.assertEqual(algo_order.duration_minutes, 120)
        
        # Test status updates
        algo_order.executed_quantity = 1000
        algo_order.save()
        self.assertEqual(algo_order.fill_ratio, 100.0)
        self.assertEqual(algo_order.remaining_quantity, 0)
    
    def test_algorithm_types(self):
        """Test all supported algorithm types"""
        algorithm_types = ['TWAP', 'VWAP', 'ICEBERG', 'SNIPER', 'IMPLEMENTATION_SHORTFALL', 'PARTICIPATION_RATE']
        
        for algo_type in algorithm_types:
            with self.subTest(algorithm_type=algo_type):
                algo_order = AlgorithmicOrder.objects.create(
                    user=self.user,
                    exchange=self.sim_exchange,
                    instrument=self.sim_instrument,
                    algorithm_type=algo_type,
                    side='BUY',
                    total_quantity=100,
                    start_time=timezone.now(),
                    end_time=timezone.now() + timedelta(hours=1)
                )
                self.assertEqual(algo_order.algorithm_type, algo_type)


class CustomStrategyModelTestCase(TestCase):
    """Test cases for CustomStrategy models"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='strategy_user', 
            email='strategy@test.com'
        )
    
    def test_custom_strategy_creation(self):
        """Test CustomStrategy model creation"""
        strategy_code = '''
def execute_strategy(market_data, portfolio, parameters):
    """Simple moving average strategy"""
    current_price = market_data.get('price', 0)
    threshold = parameters.get('threshold', 150.00)
    position_size = parameters.get('position_size', 100)
    
    if current_price > threshold:
        return {'action': 'BUY', 'quantity': position_size}
    elif current_price < threshold * 0.95:
        return {'action': 'SELL', 'quantity': position_size}
    else:
        return {'action': 'HOLD'}
        '''
        
        strategy = CustomStrategy.objects.create(
            user=self.user,
            name='Test MA Strategy',
            description='Simple moving average strategy',
            strategy_code=strategy_code,
            strategy_parameters={
                'threshold': 150.00, 
                'position_size': 100,
                'max_position': 1000,
                'stop_loss_pct': 0.05
            },
            max_position_size=Decimal('10000.00'),
            max_daily_loss=Decimal('500.00')
        )
        
        self.assertEqual(strategy.name, 'Test MA Strategy')
        self.assertTrue(strategy.is_active)
        self.assertFalse(strategy.is_validated)
        self.assertEqual(strategy.total_executions, 0)
        self.assertEqual(strategy.strategy_parameters['threshold'], 150.00)
        self.assertEqual(strategy.strategy_parameters['position_size'], 100)
        
        # Test string representation - use correct username
        self.assertIn('Test MA Strategy', str(strategy))
        self.assertIn('strategy_user', str(strategy))
    
    def test_strategy_backtest_creation(self):
        """Test StrategyBacktest model creation"""
        strategy = CustomStrategy.objects.create(
            user=self.user,
            name='Backtest Strategy',
            description='Strategy for backtesting',
            strategy_code='def test_strategy(): return {"action": "HOLD"}'
        )
        
        backtest = StrategyBacktest.objects.create(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=Decimal('50000.00'),
            instruments_tested=['AAPL', 'MSFT', 'GOOGL'],
            final_capital=Decimal('55750.00'),
            total_return=Decimal('11.50'),
            annual_return=Decimal('23.00'),
            sharpe_ratio=Decimal('1.45'),
            max_drawdown=Decimal('8.20'),
            total_trades=45,
            winning_trades=28,
            losing_trades=17,
            average_trade_pnl=Decimal('127.78'),
            backtest_results={
                'monthly_returns': [2.1, -1.5, 3.2, 0.8, 4.1, 2.8],
                'max_dd_date': '2024-03-15',
                'best_trade': 450.00,
                'worst_trade': -280.00,
                'volatility': 0.18,
                'calmar_ratio': 2.80
            }
        )
        
        self.assertEqual(backtest.strategy, strategy)
        self.assertEqual(backtest.total_return, Decimal('11.50'))
        self.assertEqual(backtest.total_trades, 45)
        self.assertEqual(backtest.winning_trades, 28)
        self.assertEqual(backtest.losing_trades, 17)
        self.assertEqual(len(backtest.instruments_tested), 3)
        
        # Test win rate calculation
        win_rate = (backtest.winning_trades / backtest.total_trades) * 100
        self.assertAlmostEqual(win_rate, 62.22, places=2)
        
        # Test JSON field access
        self.assertEqual(len(backtest.backtest_results['monthly_returns']), 6)
        self.assertEqual(backtest.backtest_results['best_trade'], 450.00)
        
        # Test string representation
        self.assertIn('Backtest Strategy', str(backtest))
        self.assertIn('2024-01-01', str(backtest))
        self.assertIn('2024-06-30', str(backtest))
    
    def test_strategy_performance_tracking(self):
        """Test strategy performance tracking"""
        strategy = CustomStrategy.objects.create(
            user=self.user,
            name='Performance Strategy',
            strategy_code='def execute(): pass'
        )
        
        # Simulate some executions and P&L
        strategy.total_executions = 10
        strategy.total_pnl = Decimal('1250.00')  #  profit
        strategy.win_rate = Decimal('75.00')     # 75% win rate
        strategy.save()
        
        self.assertEqual(strategy.total_executions, 10)
        self.assertEqual(strategy.total_pnl, Decimal('1250.00'))
        self.assertEqual(strategy.win_rate, Decimal('75.00'))
