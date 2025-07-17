# apps/order_management/tests/test_algorithm_services.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

from apps.order_management.models import AlgorithmicOrder, AlgorithmExecution, SimulatedOrder
from apps.order_management.algorithm_services import (
    TWAPAlgorithm, VWAPAlgorithm, IcebergAlgorithm, SniperAlgorithm,
    ParticipationRateAlgorithm, AlgorithmExecutionEngine
)
from apps.trading_simulation.models import SimulatedExchange, SimulatedInstrument, UserSimulationProfile
from apps.market_data.models import Exchange, Ticker, Sector, Industry, DataSource

User = get_user_model()


class TWAPAlgorithmTestCase(TestCase):
    """Test cases for TWAP Algorithm"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='twap_user', email='twap@test.com')
        
        # Create required objects
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='AAPL', name='Apple Inc.', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='AAPL', alpha_vantage_symbol='AAPL'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        # Create user profile
        UserSimulationProfile.objects.create(user=self.user)
    
    def test_twap_schedule_generation(self):
        """Test TWAP execution schedule generation"""
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=2)
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=start_time,
            end_time=end_time,
            algorithm_parameters={
                'slice_count': 10,
                'price_improvement_bps': 5,
                'randomize_timing': False
            }
        )
        
        twap = TWAPAlgorithm(algo_order)
        schedule = twap.generate_execution_schedule()
        
        # Verify schedule properties
        self.assertEqual(len(schedule), 10)
        self.assertEqual(sum(step['quantity'] for step in schedule), 1000)
        
        # Check first and last execution times
        self.assertEqual(schedule[0]['scheduled_time'], start_time)
        self.assertAlmostEqual(
            schedule[-1]['scheduled_time'], 
            start_time + timedelta(hours=1, minutes=48),  # 9/10 * 2 hours
            delta=timedelta(minutes=1)
        )
        
        # Verify all steps have correct structure
        for i, step in enumerate(schedule):
            self.assertEqual(step['execution_step'], i + 1)
            self.assertEqual(step['order_type'], 'LIMIT')
            self.assertEqual(step['price_strategy'], 'MIDPOINT_IMPROVED')
            self.assertGreater(step['quantity'], 0)
    
    def test_twap_price_calculation(self):
        """Test TWAP limit price calculation"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters={'price_improvement_bps': 10}
        )
        
        twap = TWAPAlgorithm(algo_order)
        
        # Test with bid/ask data
        market_data = {
            'bid_price': Decimal('149.50'),
            'ask_price': Decimal('149.60'),
            'last_price': Decimal('149.55')
        }
        
        price = twap.calculate_limit_price(market_data)
        
        # Should be midpoint + improvement for buy order
        expected_midpoint = Decimal('149.55')
        expected_improvement = expected_midpoint * Decimal('0.001')  # 10 bps
        expected_price = expected_midpoint + expected_improvement
        
        self.assertAlmostEqual(float(price), float(expected_price), places=4)
    
    def test_twap_randomized_timing(self):
        """Test TWAP with randomized timing"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters={
                'slice_count': 5,
                'randomize_timing': True
            }
        )
        
        twap = TWAPAlgorithm(algo_order)
        schedule = twap.generate_execution_schedule()
        
        self.assertEqual(len(schedule), 5)
        
        # First execution should be at start time
        self.assertEqual(schedule[0]['scheduled_time'], algo_order.start_time)
        
        # Other executions should have some timing variation
        # (Note: randomization makes this test non-deterministic, 
        # but we can check structure)
        for step in schedule[1:]:
            self.assertIsInstance(step['scheduled_time'], type(timezone.now()))


class VWAPAlgorithmTestCase(TestCase):
    """Test cases for VWAP Algorithm"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='vwap_user', email='vwap@test.com')
        
        # Reuse setup logic (simplified for brevity)
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='MSFT', name='Microsoft Corp.', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='MSFT', alpha_vantage_symbol='MSFT'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
    
    def test_vwap_volume_profiles(self):
        """Test different VWAP volume profiles"""
        # Test standard profile
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=800,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={'volume_profile': 'STANDARD'}
        )
        
        vwap = VWAPAlgorithm(algo_order)
        profile = vwap._get_volume_profile()
        
        # Standard profile should sum to approximately 1.0
        self.assertAlmostEqual(sum(profile), 1.0, places=2)
        self.assertEqual(len(profile), 8)  # 8 time slices
        
        # Test aggressive profile
        algo_order.algorithm_parameters = {'volume_profile': 'AGGRESSIVE'}
        vwap = VWAPAlgorithm(algo_order)
        aggressive_profile = vwap._get_volume_profile()
        
        # Aggressive should be front-loaded
        self.assertGreater(aggressive_profile[0], profile[0])
        self.assertGreater(aggressive_profile[1], profile[1])
    
    def test_vwap_schedule_generation(self):
        """Test VWAP execution schedule generation"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={'volume_profile': 'STANDARD'}
        )
        
        vwap = VWAPAlgorithm(algo_order)
        schedule = vwap.generate_execution_schedule()
        
        # Verify schedule properties
        self.assertGreater(len(schedule), 0)
        self.assertLessEqual(len(schedule), 8)  # Max 8 slices
        
        # Total quantity should match (within rounding)
        total_scheduled = sum(step['quantity'] for step in schedule)
        self.assertEqual(total_scheduled, 1000)
        
        # Each step should have VWAP-specific properties
        for step in schedule:
            self.assertEqual(step['order_type'], 'LIMIT')
            self.assertEqual(step['price_strategy'], 'VWAP_ADJUSTED')
            self.assertIn('volume_target', step)
    
    def test_vwap_participation_rate(self):
        """Test VWAP participation rate calculation"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters={
                'max_participation_rate': 0.25,
                'aggressive_factor': 1.5
            }
        )
        
        vwap = VWAPAlgorithm(algo_order)
        
        # Test with high volume
        high_vol_rate = vwap.calculate_participation_rate(5000)
        self.assertGreater(high_vol_rate, 0.20)
        self.assertLessEqual(high_vol_rate, 0.30)
        
        # Test with low volume
        low_vol_rate = vwap.calculate_participation_rate(500)
        self.assertGreater(low_vol_rate, 0.05)
        self.assertLess(low_vol_rate, high_vol_rate)


class IcebergAlgorithmTestCase(TestCase):
    """Test cases for Iceberg Algorithm"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='iceberg_user', email='iceberg@test.com')
        
        # Simplified setup
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='GOOGL', name='Alphabet Inc.', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='GOOGL', alpha_vantage_symbol='GOOGL'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
    
    def test_iceberg_schedule_generation(self):
        """Test Iceberg execution schedule generation"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='ICEBERG',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=4),
            algorithm_parameters={
                'display_size': 100,
                'refresh_threshold': 0.5,
                'randomize_display': False
            }
        )
        
        iceberg = IcebergAlgorithm(algo_order)
        schedule = iceberg.generate_execution_schedule()
        
        # Should create 10 slices (1000 / 100)
        self.assertEqual(len(schedule), 10)
        
        # Each slice should be display_size except possibly the last
        for i, step in enumerate(schedule[:-1]):
            self.assertEqual(step['quantity'], 100)
            self.assertEqual(step['display_quantity'], 100)
            self.assertTrue(step['is_iceberg_slice'])
        
        # All executions should be immediate (iceberg characteristic)
        for step in schedule:
            self.assertEqual(step['scheduled_time'], algo_order.start_time)
    
    def test_iceberg_randomized_display(self):
        """Test Iceberg with randomized display sizes"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='ICEBERG',
            side='BUY',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={
                'display_size': 100,
                'randomize_display': True
            }
        )
        
        iceberg = IcebergAlgorithm(algo_order)
        schedule = iceberg.generate_execution_schedule()
        
        # Should have multiple slices
        self.assertGreater(len(schedule), 3)
        
        # Total quantity should match
        total = sum(step['quantity'] for step in schedule)
        self.assertEqual(total, 500)
        
        # With randomization, slice sizes might vary (except first slice)
        # First slice should be exactly display_size
        self.assertEqual(schedule[0]['quantity'], 100)
    
    def test_iceberg_refresh_logic(self):
        """Test Iceberg refresh threshold logic"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='ICEBERG',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={'refresh_threshold': 0.6}
        )
        
        iceberg = IcebergAlgorithm(algo_order)
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now(),
            market_price=Decimal("100.00")
        )
        
        # Test refresh conditions
        self.assertTrue(iceberg.should_refresh_slice(execution, 0.7))  # Above threshold
        self.assertFalse(iceberg.should_refresh_slice(execution, 0.5))  # Below threshold
        self.assertTrue(iceberg.should_refresh_slice(execution, 0.6))   # At threshold


class SniperAlgorithmTestCase(TestCase):
    """Test cases for Sniper Algorithm"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='sniper_user', email='sniper@test.com')
        
        # Simplified setup
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='TSLA', name='Tesla Inc.', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='TSLA', alpha_vantage_symbol='TSLA'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
    
    def test_sniper_execution_conditions(self):
        """Test Sniper algorithm execution conditions"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='SNIPER',
            side='BUY',
            total_quantity=200,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            limit_price=Decimal('250.00'),
            algorithm_parameters={
                'max_spread_bps': 20,
                'min_volume': 1000,
                'patience_seconds': 300
            }
        )
        
        sniper = SniperAlgorithm(algo_order)
        
        # Test favorable conditions
        good_market_data = {
            'spread_bps': 15,           # Below max spread
            'volume': 2000,             # Above min volume
            'last_price': Decimal('249.50')  # Below limit price for buy
        }
        self.assertTrue(sniper.should_execute(good_market_data))
        
        # Test unfavorable conditions - wide spread
        wide_spread_data = {
            'spread_bps': 25,           # Above max spread
            'volume': 2000,
            'last_price': Decimal('249.50')
        }
        self.assertFalse(sniper.should_execute(wide_spread_data))
        
        # Test unfavorable conditions - low volume
        low_volume_data = {
            'spread_bps': 15,
            'volume': 500,              # Below min volume
            'last_price': Decimal('249.50')
        }
        self.assertFalse(sniper.should_execute(low_volume_data))
        
        # Test unfavorable conditions - poor price
        poor_price_data = {
            'spread_bps': 15,
            'volume': 2000,
            'last_price': Decimal('251.00')  # Above limit price for buy
        }
        self.assertFalse(sniper.should_execute(poor_price_data))
    
    def test_sniper_patience_timeout(self):
        """Test Sniper patience timeout"""
        # Create order with start time in the past
        past_time = timezone.now() - timedelta(minutes=10)
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='SNIPER',
            side='BUY',
            total_quantity=200,
            start_time=past_time,  # 10 minutes ago
            end_time=timezone.now() + timedelta(hours=1),
            algorithm_parameters={
                'patience_seconds': 300  # 5 minutes
            }
        )
        
        sniper = SniperAlgorithm(algo_order)
        
        # Even with poor conditions, should execute due to timeout
        poor_conditions = {
            'spread_bps': 50,           # Wide spread
            'volume': 100,              # Low volume
            'last_price': Decimal('300.00')  # Poor price
        }
        
        self.assertTrue(sniper.should_execute(poor_conditions))


class AlgorithmExecutionEngineTestCase(TestCase):
    """Test cases for Algorithm Execution Engine"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='engine_user', email='engine@test.com')
        
        # Complete setup
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='NVDA', name='NVIDIA Corp.', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='NVDA', alpha_vantage_symbol='NVDA'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        # Create user profile with sufficient balance
        UserSimulationProfile.objects.create(
            user=self.user,
            virtual_cash_balance=Decimal('100000.00')
        )
        
        self.engine = AlgorithmExecutionEngine()
    
    @patch('apps.risk_management.services.RiskManagementService.validate_algorithmic_order')
    def test_algorithm_startup(self, mock_risk_validation):
        """Test algorithm startup process"""
        # Mock risk validation to pass
        mock_risk_validation.return_value = {'approved': True, 'violations': []}
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={'slice_count': 5}
        )
        
        # Test successful startup
        success = self.engine.start_algorithm(algo_order)
        
        self.assertTrue(success)
        
        # Refresh from database
        algo_order.refresh_from_db()
        
        self.assertEqual(algo_order.status, 'RUNNING')
        self.assertIsNotNone(algo_order.started_timestamp)
        
        # Should have created execution records
        executions = algo_order.executions.all()
        self.assertEqual(executions.count(), 5)
        
        # Risk validation should have been called
        mock_risk_validation.assert_called_once_with(algo_order)
    
    @patch('apps.risk_management.services.RiskManagementService.validate_algorithmic_order')
    def test_algorithm_risk_rejection(self, mock_risk_validation):
        """Test algorithm rejection due to risk"""
        # Mock risk validation to fail
        mock_risk_validation.return_value = {
            'approved': False, 
            'violations': ['Order size too large']
        }
        
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=50000,  # Large order
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2)
        )
        
        success = self.engine.start_algorithm(algo_order)
        
        self.assertFalse(success)
        
        # Refresh from database
        algo_order.refresh_from_db()
        
        self.assertEqual(algo_order.status, 'REJECTED')
        self.assertIsNone(algo_order.started_timestamp)
    
    def test_algorithm_pause_resume_cancel(self):
        """Test algorithm pause, resume, and cancel operations"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            status='RUNNING'  # Set as already running
        )
        
        # Test pause
        success = self.engine.pause_algorithm(algo_order)
        self.assertTrue(success)
        
        algo_order.refresh_from_db()
        self.assertEqual(algo_order.status, 'PAUSED')
        
        # Test resume
        success = self.engine.resume_algorithm(algo_order)
        self.assertTrue(success)
        
        algo_order.refresh_from_db()
        self.assertEqual(algo_order.status, 'RUNNING')
        
        # Test cancel
        success = self.engine.cancel_algorithm(algo_order)
        self.assertTrue(success)
        
        algo_order.refresh_from_db()
        self.assertEqual(algo_order.status, 'CANCELLED')
        self.assertIsNotNone(algo_order.completed_timestamp)
    
    def test_unsupported_algorithm_type(self):
        """Test handling of unsupported algorithm types"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='CUSTOM',  # Unsupported type
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2)
        )
        
        success = self.engine.start_algorithm(algo_order)
        
        self.assertFalse(success)
        
        algo_order.refresh_from_db()
        self.assertEqual(algo_order.status, 'REJECTED')
    
    @patch("channels.layers.get_channel_layer")
    def test_websocket_broadcasting(self, mock_channel_layer):
        """Test WebSocket broadcasting functionality with async support"""
        # Mock channel layer
        mock_group_send = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.group_send = mock_group_send
        mock_channel_layer.return_value = mock_channel

        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            status='RUNNING'
        )

        # Test algorithm update broadcast
        self.engine._broadcast_algorithm_update(algo_order, 'STARTED')

        # Algorithm updates now broadcast to multiple groups:
        # - orders_{user_id}
        # - algorithms_{user_id}
        # So we expect at least 2 calls
        self.assertGreaterEqual(mock_group_send.call_count, 2)

        # Test execution update broadcast
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now(),
            executed_quantity=100,
            market_price=Decimal("100.00")
        )

        initial_call_count = mock_group_send.call_count
        self.engine._broadcast_execution_update(execution)

        # Should have additional calls for execution update
        self.assertGreater(mock_group_send.call_count, initial_call_count)

    @patch('channels.layers.get_channel_layer')
    def test_algorithm_lifecycle_websocket_integration(self, mock_channel_layer):
        """Test complete algorithm lifecycle with WebSocket updates"""
        mock_layer = MagicMock()
        mock_channel_layer.return_value = mock_layer
        
        # Create algorithm order
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            algorithm_parameters={'slice_count': 5}
        )
        
        # Mock risk validation
        with patch.object(self.engine.risk_service, 'validate_algorithmic_order') as mock_risk:
            mock_risk.return_value = {'approved': True, 'violations': []}
            
            # Test start algorithm
            success = self.engine.start_algorithm(algo_order)
            self.assertTrue(success)
            
            # Verify start broadcast
            start_calls = [call for call in mock_layer.group_send.call_args_list 
                          if 'STARTED' in str(call)]
            self.assertTrue(len(start_calls) > 0)
            
            # Test pause algorithm
            success = self.engine.pause_algorithm(algo_order)
            self.assertTrue(success)
            
            # Verify pause broadcast
            pause_calls = [call for call in mock_layer.group_send.call_args_list 
                          if 'PAUSED' in str(call)]
            self.assertTrue(len(pause_calls) > 0)
            
            # Test resume algorithm
            success = self.engine.resume_algorithm(algo_order)
            self.assertTrue(success)
            
            # Verify resume broadcast
            resume_calls = [call for call in mock_layer.group_send.call_args_list 
                           if 'RESUMED' in str(call)]
            self.assertTrue(len(resume_calls) > 0)

    @patch('channels.layers.get_channel_layer')
    def test_execution_step_websocket_updates(self, mock_channel_layer):
        """Test that execution steps trigger WebSocket updates"""
        mock_layer = MagicMock()
        mock_channel_layer.return_value = mock_layer
        
        # Create running algorithm
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            status='RUNNING'
        )
        
        # Create execution record
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now(),
            market_price=Decimal('150.00')
        )
        
        # Mock market data and order submission
        with patch.object(self.engine, '_get_market_data') as mock_market_data:
            mock_market_data.return_value = {
                'last_price': Decimal('150.50'),
                'bid_price': Decimal('150.25'),
                'ask_price': Decimal('150.75'),
                'volume': 10000,
                'spread_bps': Decimal('33.3')
            }
            
            with patch.object(self.engine.order_service, 'submit_order') as mock_submit:
                mock_submit.return_value = (True, 'Order submitted', [])
                
                # Process execution step
                success = self.engine.process_algorithm_step(execution)
                
                # Should attempt to create child order
                mock_submit.assert_called_once()
                
                # Verify execution update was broadcast
                execution_calls = [call for call in mock_layer.group_send.call_args_list 
                                 if 'execution_update' in str(call)]
                self.assertTrue(len(execution_calls) > 0)

    @patch('channels.layers.get_channel_layer')
    def test_algorithm_rejection_websocket_notification(self, mock_channel_layer):
        """Test WebSocket notification for algorithm rejection"""
        mock_layer = MagicMock()
        mock_channel_layer.return_value = mock_layer
        
        # Create algorithm that will be rejected
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='TWAP',
            side='BUY',
            total_quantity=1000000,  # Very large order
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2)
        )
        
        # Mock risk service to reject
        with patch.object(self.engine.risk_service, 'validate_algorithmic_order') as mock_risk:
            mock_risk.return_value = {
                'approved': False,
                'violations': ['Order size exceeds limit', 'Insufficient cash balance']
            }
            
            # Attempt to start algorithm
            success = self.engine.start_algorithm(algo_order)
            self.assertFalse(success)
            
            # Verify rejection status
            algo_order.refresh_from_db()
            self.assertEqual(algo_order.status, 'REJECTED')
            
            # Verify no WebSocket broadcast for rejected algorithm
            # (since rejection happens before status change to RUNNING)
            self.assertEqual(mock_layer.group_send.call_count, 0)

    def test_websocket_message_structure(self):
        """Test the structure of WebSocket messages"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='VWAP',
            side='SELL',
            total_quantity=500,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            status='RUNNING'
        )
        
        # Create execution record
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=1,
            scheduled_time=timezone.now(),
            executed_quantity=100,
            market_price=Decimal('245.75')
        )
        
        # Test algorithm update message structure
        with patch('channels.layers.get_channel_layer') as mock_channel_layer:
            mock_layer = MagicMock()
            mock_channel_layer.return_value = mock_layer
            
            self.engine._broadcast_algorithm_update(algo_order, 'STARTED')
            
            # Verify call was made
            self.assertTrue(mock_layer.group_send.called)
            
            # Get the call arguments
            call_args = mock_layer.group_send.call_args_list[0]
            group_name = call_args[0][0]
            message = call_args[0][1]
            
            # Verify message structure
            self.assertIn(f'orders_{self.user.id}', group_name)
            self.assertEqual(message['type'], 'algorithm_update')
            self.assertIn('algorithm', message)
            
            algorithm_data = message['algorithm']
            required_fields = [
                'algo_order_id', 'algorithm_type', 'status', 'symbol',
                'fill_ratio', 'total_quantity', 'executed_quantity',
                'event_type', 'timestamp'
            ]
            
            for field in required_fields:
                self.assertIn(field, algorithm_data)


class ParticipationRateAlgorithmTestCase(TestCase):
    """Test cases for Participation Rate Algorithm"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='pov_user', email='pov@test.com')
        
        # Minimal setup
        self.real_exchange = Exchange.objects.create(name='Test Exchange', code='TEST')
        self.sim_exchange = SimulatedExchange.objects.create(
            name='Simulated Test', code='SIM_TEST', real_exchange=self.real_exchange
        )
        
        self.sector = Sector.objects.create(name='Technology', code='TECH')
        self.industry = Industry.objects.create(name='Consumer Electronics', sector=self.sector)
        self.data_source = DataSource.objects.create(
            name='Test Source', code='TEST_DS', url='https://test.com',
            api_endpoint='https://api.test.com', is_active=True,
            requires_api_key=False, rate_limit_per_minute=60,
            supported_markets=[], supported_timeframes=[]
        )
        
        self.ticker = Ticker.objects.create(
            symbol='SPY', name='SPDR S&P 500', exchange=self.real_exchange,
            sector=self.sector, industry=self.industry, data_source=self.data_source,
            currency='USD', country='US', yfinance_symbol='SPY', alpha_vantage_symbol='SPY'
        )
        
        self.instrument = SimulatedInstrument.objects.create(
            real_ticker=self.ticker, exchange=self.sim_exchange
        )
        
        UserSimulationProfile.objects.create(user=self.user)
    
    def test_participation_rate_calculation(self):
        """Test participation rate quantity calculation"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='PARTICIPATION_RATE',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            participation_rate=Decimal('0.20'),  # 20% participation
            executed_quantity=200  # 200 already executed, 800 remaining
        )

        pov = ParticipationRateAlgorithm(algo_order)

        # Test with market volume of 5000 - algorithm should want 1000 but limit to 800 remaining
        quantity = pov.calculate_execution_quantity(5000, 60)
        expected_target = 5000 * 0.20  # 1000 shares
        remaining = algo_order.remaining_quantity  # 800 shares
        expected_result = min(int(expected_target), remaining)

        self.assertEqual(quantity, expected_result)  # Should respect remaining quantity limit

        # Test with low market volume
        quantity = pov.calculate_execution_quantity(100, 60)
        expected = 100 * 0.20  # 20 shares
        self.assertEqual(quantity, int(expected))

    def test_participation_rate_with_zero_market_volume(self):
        """Test participation rate with zero market volume"""
        algo_order = AlgorithmicOrder.objects.create(
            user=self.user,
            exchange=self.sim_exchange,
            instrument=self.instrument,
            algorithm_type='PARTICIPATION_RATE',
            side='BUY',
            total_quantity=1000,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            participation_rate=Decimal('0.15')
        )
        
        pov = ParticipationRateAlgorithm(algo_order)
        
        # Test with zero market volume
        quantity = pov.calculate_execution_quantity(0, 60)
        self.assertEqual(quantity, 0)
