import logging
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import (
    AlgorithmicOrder, AlgorithmExecution, SimulatedOrder, OrderSide,
    OrderStatus, CustomStrategy, StrategyBacktest
)
from .services import OrderMatchingService
from apps.trading_simulation.models import SimulatedInstrument
from apps.risk_management.services import RiskManagementService

logger = logging.getLogger(__name__)


class TWAPAlgorithm:
    """
    Time-Weighted Average Price Algorithm
    Splits large orders into time-based slices for minimal market impact
    """
    
    def __init__(self, algo_order: AlgorithmicOrder):
        self.algo_order = algo_order
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_execution_schedule(self) -> List[Dict]:
        """Generate time-based execution schedule"""
        try:
            # Extract parameters
            params = self.algo_order.algorithm_parameters
            slice_count = params.get('slice_count', 10)
            randomize_timing = params.get('randomize_timing', False)
            
            # Calculate time intervals
            duration = self.algo_order.end_time - self.algo_order.start_time
            base_interval = duration / slice_count
            
            # Calculate slice sizes
            base_quantity = self.algo_order.total_quantity // slice_count
            remainder = self.algo_order.total_quantity % slice_count
            
            schedule = []
            current_time = self.algo_order.start_time
            
            for i in range(slice_count):
                slice_quantity = base_quantity
                if i < remainder:  # Distribute remainder across first slices
                    slice_quantity += 1
                
                # Add randomization if enabled
                execution_time = current_time
                if randomize_timing and i > 0:
                    import random
                    jitter = random.uniform(-0.2, 0.2) * base_interval.total_seconds()
                    execution_time += timedelta(seconds=jitter)
                
                schedule.append({
                    'execution_step': i + 1,
                    'scheduled_time': execution_time,
                    'quantity': slice_quantity,
                    'order_type': 'LIMIT',
                    'price_strategy': 'MIDPOINT_IMPROVED'
                })
                
                current_time += base_interval
            
            self.logger.info(f"Generated TWAP schedule: {slice_count} slices over {duration}")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Error generating TWAP schedule: {e}")
            return []
    
    def calculate_limit_price(self, market_data: Dict) -> Decimal:
        """Calculate appropriate limit price for TWAP execution"""
        try:
            bid = market_data.get('bid_price')
            ask = market_data.get('ask_price')
            
            if bid and ask:
                midpoint = (bid + ask) / 2
                
                # Price improvement parameters
                params = self.algo_order.algorithm_parameters
                improvement_bps = params.get('price_improvement_bps', 1)
                improvement = midpoint * Decimal(str(improvement_bps / 10000))
                
                # Add price improvement for better execution probability
                if self.algo_order.side == "BUY":
                    return midpoint + improvement
                else:
                    return midpoint - improvement
            
            # Fallback to last trade price
            return market_data.get('last_price', Decimal('0'))
            
        except Exception as e:
            self.logger.error(f"Error calculating TWAP limit price: {e}")
            return Decimal('0')


class VWAPAlgorithm:
    """
    Volume-Weighted Average Price Algorithm
    Adjusts order sizes based on historical volume patterns
    """
    
    def __init__(self, algo_order: AlgorithmicOrder):
        self.algo_order = algo_order
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_execution_schedule(self) -> List[Dict]:
        """Generate volume-based execution schedule"""
        try:
            # Get historical volume profile
            volume_profile = self._get_volume_profile()
            
            schedule = []
            remaining_quantity = self.algo_order.total_quantity
            duration = self.algo_order.end_time - self.algo_order.start_time
            
            for i, volume_pct in enumerate(volume_profile):
                if remaining_quantity <= 0:
                    break
                
                # Calculate slice size based on volume percentage
                slice_quantity = int(self.algo_order.total_quantity * volume_pct)
                slice_quantity = min(slice_quantity, remaining_quantity)
                
                if slice_quantity > 0:
                    # Calculate execution time based on volume distribution
                    time_pct = i / len(volume_profile)
                    scheduled_time = self.algo_order.start_time + (duration * time_pct)
                    
                    schedule.append({
                        'execution_step': i + 1,
                        'scheduled_time': scheduled_time,
                        'quantity': slice_quantity,
                        'order_type': 'LIMIT',
                        'price_strategy': 'VWAP_ADJUSTED',
                        'volume_target': volume_pct
                    })
                    
                    remaining_quantity -= slice_quantity
            
            # Handle any remaining quantity in final slice
            if remaining_quantity > 0 and schedule:
                schedule[-1]['quantity'] += remaining_quantity
            
            self.logger.info(f"Generated VWAP schedule: {len(schedule)} slices")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Error generating VWAP schedule: {e}")
            return []
    
    def _get_volume_profile(self) -> List[float]:
        """Get historical intraday volume profile"""
        # Get parameters
        params = self.algo_order.algorithm_parameters
        profile_type = params.get('volume_profile', 'STANDARD')
        
        if profile_type == 'AGGRESSIVE':
            # Front-loaded volume distribution
            return [0.15, 0.20, 0.18, 0.15, 0.12, 0.10, 0.06, 0.04]
        elif profile_type == 'PASSIVE':
            # Back-loaded volume distribution
            return [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.12]
        else:
            # Standard U-shaped intraday volume profile
            return [0.12, 0.15, 0.11, 0.09, 0.08, 0.10, 0.13, 0.22]
    
    def calculate_participation_rate(self, current_volume: int) -> float:
        """Calculate appropriate participation rate"""
        params = self.algo_order.algorithm_parameters
        max_participation = params.get('max_participation_rate', 0.20)
        aggressive_factor = params.get('aggressive_factor', 1.0)
        
        # Adjust participation based on current market volume
        if current_volume > 1000:
            return min(max_participation * aggressive_factor, 0.30)
        else:
            return max(max_participation * 0.5, 0.05)


class IcebergAlgorithm:
    """
    Iceberg Algorithm
    Shows only small portions of large orders to minimize market impact
    """
    
    def __init__(self, algo_order: AlgorithmicOrder):
        self.algo_order = algo_order
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_execution_schedule(self) -> List[Dict]:
        """Generate iceberg execution schedule"""
        try:
            params = self.algo_order.algorithm_parameters
            display_size = params.get('display_size', 100)
            refresh_threshold = params.get('refresh_threshold', 0.5)
            randomize_display = params.get('randomize_display', False)
            
            schedule = []
            remaining_quantity = self.algo_order.total_quantity
            step = 1
            
            while remaining_quantity > 0:
                # Calculate slice size
                slice_quantity = min(display_size, remaining_quantity)
                
                # Add randomization to display size
                if randomize_display and step > 1:
                    import random
                    variation = random.uniform(0.8, 1.2)
                    slice_quantity = int(min(slice_quantity * variation, remaining_quantity))
                
                schedule.append({
                    'execution_step': step,
                    'scheduled_time': self.algo_order.start_time,  # Immediate execution
                    'quantity': slice_quantity,
                    'order_type': 'LIMIT',
                    'price_strategy': 'BEST_PRICE',
                    'display_quantity': slice_quantity,
                    'refresh_threshold': refresh_threshold,
                    'is_iceberg_slice': True
                })
                
                remaining_quantity -= slice_quantity
                step += 1
                
                # Prevent infinite loops
                if step > 1000:
                    self.logger.warning("Iceberg algorithm generated too many slices, stopping")
                    break
            
            self.logger.info(f"Generated Iceberg schedule: {len(schedule)} slices")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Error generating Iceberg schedule: {e}")
            return []
    
    def should_refresh_slice(self, execution: AlgorithmExecution, 
                           current_fill_ratio: float) -> bool:
        """Determine if iceberg slice should be refreshed"""
        try:
            params = self.algo_order.algorithm_parameters
            refresh_threshold = params.get('refresh_threshold', 0.5)
            
            return current_fill_ratio >= refresh_threshold
            
        except Exception as e:
            self.logger.error(f"Error checking refresh condition: {e}")
            return False


class SniperAlgorithm:
    """
    Sniper Algorithm
    Waits for optimal execution opportunities based on market conditions
    """
    
    def __init__(self, algo_order: AlgorithmicOrder):
        self.algo_order = algo_order
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_execution_schedule(self) -> List[Dict]:
        """Generate opportunistic execution schedule"""
        try:
            # Sniper algorithm creates a single execution opportunity
            # that waits for optimal conditions
            schedule = [{
                'execution_step': 1,
                'scheduled_time': self.algo_order.start_time,
                'quantity': self.algo_order.total_quantity,
                'order_type': 'LIMIT',
                'price_strategy': 'SNIPER_OPPORTUNISTIC',
                'patience_mode': True
            }]
            
            self.logger.info("Generated Sniper schedule: waiting for optimal conditions")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Error generating Sniper schedule: {e}")
            return []
    
    def should_execute(self, market_data: Dict) -> bool:
        """Determine if current market conditions are favorable for execution"""
        try:
            params = self.algo_order.algorithm_parameters
            max_spread_bps = params.get('max_spread_bps', 20)
            min_volume = params.get('min_volume', 1000)
            patience_seconds = params.get('patience_seconds', 300)
            
            # Check patience timeout FIRST - if timeout reached, execute regardless
            time_elapsed = timezone.now() - self.algo_order.start_time
            if time_elapsed.total_seconds() > patience_seconds:
                self.logger.info("Patience timeout reached, executing at market")
                return True
            
            # Check spread condition
            spread_bps = market_data.get('spread_bps', 1000)
            if spread_bps > max_spread_bps:
                self.logger.debug(f"Spread too wide: {spread_bps} > {max_spread_bps} bps")
                return False
            
            # Check volume condition
            volume = market_data.get('volume', 0)
            if volume < min_volume:
                self.logger.debug(f"Volume too low: {volume} < {min_volume}")
                return False
            
            # Check price improvement opportunity
            target_price = self.algo_order.limit_price
            current_price = market_data.get('last_price')
            
            if target_price and current_price:
                if self.algo_order.side == "BUY":
                    price_favorable = current_price <= target_price
                else:
                    price_favorable = current_price >= target_price
                
                if not price_favorable:
                    self.logger.debug(f"Price not favorable: {current_price} vs target {target_price}")
                    return False
            
            self.logger.info("All sniper conditions met, executing order")
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking sniper execution conditions: {e}")
            return False


class ParticipationRateAlgorithm:
    """
    Participation Rate (POV - Percentage of Volume) Algorithm
    Maintains a target percentage of market volume
    """
    
    def __init__(self, algo_order: AlgorithmicOrder):
        self.algo_order = algo_order
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_execution_quantity(self, market_volume: int, 
                                   time_elapsed: int) -> int:
        """Calculate quantity to execute based on market volume"""
        try:
            participation_rate = float(self.algo_order.participation_rate or 0.20)
            target_quantity = int(market_volume * participation_rate)
            
            # Don't exceed remaining quantity - THIS WAS THE BUG
            remaining = self.algo_order.remaining_quantity
            return min(target_quantity, remaining)
            
        except Exception as e:
            self.logger.error(f"Error calculating POV quantity: {e}")
            return 0


class AlgorithmExecutionEngine:
    """
    Core engine for executing algorithmic trading strategies
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.order_service = OrderMatchingService()
        self.risk_service = RiskManagementService()
    
    def start_algorithm(self, algo_order: AlgorithmicOrder) -> bool:
        """Start executing an algorithmic order"""
        try:
            with transaction.atomic():
                # Pre-execution risk check
                risk_result = self.risk_service.validate_algorithmic_order(algo_order)
                if not risk_result.get('approved', False):
                    algo_order.status = 'REJECTED'
                    algo_order.save()
                    self.logger.warning(f"Algorithm rejected by risk: {risk_result.get('violations')}")
                    return False
                
                # Generate execution schedule based on algorithm type
                algorithm = self._get_algorithm_instance(algo_order)
                if not algorithm:
                    raise ValueError(f"Unsupported algorithm type: {algo_order.algorithm_type}")
                
                schedule = algorithm.generate_execution_schedule()
                if not schedule:
                    raise ValueError("Failed to generate execution schedule")
                
                # Create execution records
                for step_data in schedule:
                    AlgorithmExecution.objects.create(
                        algo_order=algo_order,
                        execution_step=step_data['execution_step'],
                        scheduled_time=step_data['scheduled_time'],
                        market_price=Decimal('0'),  # Will be updated at execution
                        executed_quantity=0
                    )
                
                # Update algorithm status
                algo_order.status = 'RUNNING'
                algo_order.started_timestamp = timezone.now()
                algo_order.save()
                
                self.logger.info(f"Started algorithm {algo_order.algo_order_id} with {len(schedule)} steps")
                
                # Broadcast algorithm start via WebSocket
                self._broadcast_algorithm_update(algo_order, 'STARTED')
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error starting algorithm {algo_order.algo_order_id}: {e}")
            algo_order.status = 'FAILED'
            algo_order.save()
            return False
    
    def _get_algorithm_instance(self, algo_order: AlgorithmicOrder):
        """Get appropriate algorithm instance"""
        algorithm_map = {
            'TWAP': TWAPAlgorithm,
            'VWAP': VWAPAlgorithm,
            'ICEBERG': IcebergAlgorithm,
            'SNIPER': SniperAlgorithm,
            'PARTICIPATION_RATE': ParticipationRateAlgorithm
        }
        
        algorithm_class = algorithm_map.get(algo_order.algorithm_type)
        if algorithm_class:
            return algorithm_class(algo_order)
        return None
    
    def process_algorithm_step(self, execution: AlgorithmExecution) -> bool:
        """Process a single execution step"""
        try:
            # Get current market data
            market_data = self._get_market_data(execution.algo_order.instrument)
            
            # Algorithm-specific execution logic
            if execution.algo_order.algorithm_type == 'SNIPER':
                algorithm = SniperAlgorithm(execution.algo_order)
                if not algorithm.should_execute(market_data):
                    self.logger.debug(f"Sniper conditions not met for {execution.algo_order.algo_order_id}")
                    return False
            
            # Calculate execution parameters
            limit_price = self._calculate_execution_price(execution, market_data)
            quantity = self._calculate_execution_quantity(execution, market_data)
            
            if quantity <= 0:
                self.logger.warning(f"No quantity to execute for step {execution.execution_step}")
                return False
            
            # Create child order
            child_order = SimulatedOrder.objects.create(
                user=execution.algo_order.user,
                exchange=execution.algo_order.exchange,
                instrument=execution.algo_order.instrument,
                side=execution.algo_order.side,
                order_type='LIMIT',
                quantity=quantity,
                price=limit_price,
                client_order_id=f"ALGO_{execution.algo_order.algo_order_id}_{execution.execution_step}"
            )
            
            # Submit the order
            success, message, violations = self.order_service.submit_order(child_order)
            
            if success:
                # Update execution record
                execution.child_order = child_order
                execution.execution_time = timezone.now()
                execution.market_price = market_data.get('last_price', Decimal('0'))
                execution.market_volume = market_data.get('volume', 0)
                execution.spread_bps = market_data.get('spread_bps', Decimal('0'))
                execution.save()
                
                # Update algorithm progress
                self._update_algorithm_progress(execution.algo_order)
                
                # Broadcast execution update
                self._broadcast_execution_update(execution)
                
                self.logger.info(f"Executed step {execution.execution_step} for algo {execution.algo_order.algo_order_id}")
                return True
            else:
                self.logger.warning(f"Failed to execute step: {message}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing algorithm step: {e}")
            return False
    
    def _get_market_data(self, instrument: SimulatedInstrument) -> Dict:
        """Get current market data for instrument"""
        try:
            order_book = instrument.order_book
            
            # Calculate spread in basis points
            spread_bps = Decimal('0')
            if order_book.best_bid_price and order_book.best_ask_price:
                spread = order_book.best_ask_price - order_book.best_bid_price
                mid_price = (order_book.best_bid_price + order_book.best_ask_price) / 2
                if mid_price > 0:
                    spread_bps = (spread / mid_price) * 10000
            
            return {
                'last_price': order_book.last_trade_price,
                'bid_price': order_book.best_bid_price,
                'ask_price': order_book.best_ask_price,
                'volume': order_book.daily_volume,
                'spread_bps': spread_bps,
                'trade_count': order_book.trade_count
            }
            
        except Exception as e:
            self.logger.error(f"Error getting market data: {e}")
            return {}
    
    def _calculate_execution_price(self, execution: AlgorithmExecution, 
                                 market_data: Dict) -> Decimal:
        """Calculate appropriate execution price"""
        try:
            algo_order = execution.algo_order
            
            # Get algorithm instance for price calculation
            algorithm = self._get_algorithm_instance(algo_order)
            
            if hasattr(algorithm, 'calculate_limit_price'):
                return algorithm.calculate_limit_price(market_data)
            
            # Default pricing strategy
            bid = market_data.get('bid_price')
            ask = market_data.get('ask_price')
            
            if bid and ask:
                midpoint = (bid + ask) / 2
                # Small improvement for better execution probability
                improvement = midpoint * Decimal('0.0001')  # 1 bps
                
                if algo_order.side == "BUY":
                    return midpoint + improvement
                else:
                    return midpoint - improvement
            
            return market_data.get('last_price', Decimal('0'))
            
        except Exception as e:
            self.logger.error(f"Error calculating execution price: {e}")
            return Decimal('0')
    
    def _calculate_execution_quantity(self, execution: AlgorithmExecution,
                                    market_data: Dict) -> int:
        """Calculate quantity for this execution step"""
        try:
            algo_order = execution.algo_order
            
            # For participation rate algorithms
            if algo_order.algorithm_type == 'PARTICIPATION_RATE':
                algorithm = ParticipationRateAlgorithm(algo_order)
                return algorithm.calculate_execution_quantity(
                    market_data.get('volume', 0),
                    0  # time_elapsed placeholder
                )
            
            # Get scheduled quantity from execution record
            scheduled_qty = algo_order.remaining_quantity
            
            # Apply size constraints
            max_slice = algo_order.max_slice_size or scheduled_qty
            min_slice = algo_order.min_slice_size or 1
            
            return max(min_slice, min(max_slice, scheduled_qty))
            
        except Exception as e:
            self.logger.error(f"Error calculating execution quantity: {e}")
            return 0
    
    def _update_algorithm_progress(self, algo_order: AlgorithmicOrder):
        """Update algorithm execution progress"""
        try:
            # Aggregate filled quantity from all child orders
            total_filled = 0
            child_orders = SimulatedOrder.objects.filter(
                client_order_id__startswith=f"ALGO_{algo_order.algo_order_id}_"
            )
            
            for child_order in child_orders:
                total_filled += child_order.filled_quantity
            
            # Update algorithm order
            algo_order.executed_quantity = total_filled
            
            # Check if algorithm is complete
            if algo_order.executed_quantity >= algo_order.total_quantity:
                algo_order.status = 'COMPLETED'
                algo_order.completed_timestamp = timezone.now()
                
                # Calculate performance metrics
                self._calculate_algorithm_performance(algo_order)
            
            algo_order.save()
            
        except Exception as e:
            self.logger.error(f"Error updating algorithm progress: {e}")
    
    def _calculate_algorithm_performance(self, algo_order: AlgorithmicOrder):
        """Calculate algorithm performance metrics"""
        try:
            # Calculate average execution price
            child_orders = SimulatedOrder.objects.filter(
                client_order_id__startswith=f"ALGO_{algo_order.algo_order_id}_",
                filled_quantity__gt=0
            )
            
            if child_orders.exists():
                total_value = sum(
                    order.filled_quantity * (order.average_fill_price or order.price or 0)
                    for order in child_orders
                )
                total_quantity = sum(order.filled_quantity for order in child_orders)
                
                if total_quantity > 0:
                    algo_order.average_execution_price = total_value / total_quantity
                
                # Calculate implementation shortfall vs benchmark
                # (This would compare against TWAP/VWAP benchmark)
                # For now, set as placeholder
                algo_order.implementation_shortfall = Decimal('0.0010')  # 1 bps
                
                algo_order.save()
            
        except Exception as e:
            self.logger.error(f"Error calculating algorithm performance: {e}")
    
    def _broadcast_algorithm_update(self, algo_order: AlgorithmicOrder, event_type: str):
        """Broadcast algorithm updates via WebSocket"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'orders_{algo_order.user.id}',
                    {
                        'type': 'algorithm_update',
                        'algorithm': {
                            'algo_order_id': str(algo_order.algo_order_id),
                            'algorithm_type': algo_order.algorithm_type,
                            'status': algo_order.status,
                            'fill_ratio': algo_order.fill_ratio,
                            'event_type': event_type,
                            'timestamp': timezone.now().isoformat()
                        }
                    }
                )
        except Exception as e:
            self.logger.error(f"Error broadcasting algorithm update: {e}")
    
    def _broadcast_execution_update(self, execution: AlgorithmExecution):
        """Broadcast execution updates via WebSocket"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'orders_{execution.algo_order.user.id}',
                    {
                        'type': 'execution_update',
                        'execution': {
                            'algo_order_id': str(execution.algo_order.algo_order_id),
                            'execution_step': execution.execution_step,
                            'executed_quantity': execution.executed_quantity,
                            'market_price': float(execution.market_price) if execution.market_price else None,
                            'timestamp': timezone.now().isoformat()
                        }
                    }
                )
        except Exception as e:
            self.logger.error(f"Error broadcasting execution update: {e}")
    
    def pause_algorithm(self, algo_order: AlgorithmicOrder) -> bool:
        """Pause a running algorithm"""
        try:
            if algo_order.status == 'RUNNING':
                algo_order.status = 'PAUSED'
                algo_order.save()
                
                # Cancel any pending child orders
                pending_orders = SimulatedOrder.objects.filter(
                    client_order_id__startswith=f"ALGO_{algo_order.algo_order_id}_",
                    status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED']
                )
                
                for order in pending_orders:
                    self.order_service.cancel_order(order, "Algorithm paused")
                
                self._broadcast_algorithm_update(algo_order, 'PAUSED')
                
                self.logger.info(f"Paused algorithm {algo_order.algo_order_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error pausing algorithm: {e}")
            return False
    
    def resume_algorithm(self, algo_order: AlgorithmicOrder) -> bool:
        """Resume a paused algorithm"""
        try:
            if algo_order.status == 'PAUSED':
                algo_order.status = 'RUNNING'
                algo_order.save()
                
                self._broadcast_algorithm_update(algo_order, 'RESUMED')
                
                self.logger.info(f"Resumed algorithm {algo_order.algo_order_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error resuming algorithm: {e}")
            return False
    
    def cancel_algorithm(self, algo_order: AlgorithmicOrder) -> bool:
        """Cancel a running algorithm"""
        try:
            if algo_order.status in ['RUNNING', 'PAUSED']:
                algo_order.status = 'CANCELLED'
                algo_order.completed_timestamp = timezone.now()
                algo_order.save()
                
                # Cancel all pending child orders
                pending_orders = SimulatedOrder.objects.filter(
                    client_order_id__startswith=f"ALGO_{algo_order.algo_order_id}_",
                    status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
                )
                
                for order in pending_orders:
                    self.order_service.cancel_order(order, "Algorithm cancelled")
                
                self._broadcast_algorithm_update(algo_order, 'CANCELLED')
                
                self.logger.info(f"Cancelled algorithm {algo_order.algo_order_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error cancelling algorithm: {e}")
            return False
