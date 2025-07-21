# apps/order_management/tasks.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional

from celery import shared_task
from django.utils import timezone
from asgiref.sync import async_to_sync

from apps.core.events import (
    publish_algorithm_execution_started,
    publish_algorithm_execution_progress, 
    publish_algorithm_execution_completed,
    publish_algorithm_execution_error
)
from .models import AlgorithmicOrder, AlgorithmExecution, SimulatedOrder

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def execute_algorithmic_order(self, algo_order_id: str):
    """Execute an algorithmic order step by step"""
    try:
        algo_order = AlgorithmicOrder.objects.get(algo_order_id=algo_order_id)
        
        # Update status to running
        algo_order.status = 'RUNNING'
        algo_order.started_timestamp = timezone.now()
        algo_order.save()
        
        # Publish started event
        async_to_sync(publish_algorithm_execution_started)(
            algo_order_id=str(algo_order.algo_order_id),
            algorithm_type=algo_order.algorithm_type,
            total_quantity=algo_order.total_quantity,
            estimated_duration_minutes=algo_order.duration_minutes,
            execution_parameters=algo_order.algorithm_parameters,
            user_id=algo_order.user_id
        )
        
        # Execute algorithm based on type
        if algo_order.algorithm_type == 'TWAP':
            execute_twap_algorithm(algo_order)
        elif algo_order.algorithm_type == 'VWAP':
            execute_vwap_algorithm(algo_order)
        elif algo_order.algorithm_type == 'ICEBERG':
            execute_iceberg_algorithm(algo_order)
        elif algo_order.algorithm_type == 'POV':
            execute_pov_algorithm(algo_order)
        else:
            execute_custom_algorithm(algo_order)
            
    except Exception as e:
        logger.error(f"Algorithm execution failed for {algo_order_id}: {e}")
        
        # Publish error event
        async_to_sync(publish_algorithm_execution_error)(
            algo_order_id=algo_order_id,
            error_type=type(e).__name__,
            error_message=str(e),
            execution_step=0,
            recovery_action="CANCEL",
            user_id=getattr(algo_order, 'user_id', None)
        )
        
        # Update algorithm status
        try:
            algo_order.status = 'FAILED'
            algo_order.completed_timestamp = timezone.now()
            algo_order.save()
        except:
            pass


def execute_twap_algorithm(algo_order: AlgorithmicOrder):
    """Execute Time-Weighted Average Price algorithm"""
    try:
        # Calculate execution schedule
        duration_minutes = algo_order.duration_minutes
        interval_minutes = algo_order.algorithm_parameters.get('interval_minutes', 5)
        total_steps = max(1, duration_minutes // interval_minutes)
        slice_size = algo_order.total_quantity // total_steps
        
        logger.info(f"Executing TWAP: {total_steps} steps, {slice_size} shares per step")
        
        for step in range(1, total_steps + 1):
            if algo_order.status != 'RUNNING':
                break
                
            # Calculate execution time
            execution_time = algo_order.start_time + timedelta(minutes=step * interval_minutes)
            
            # Wait until execution time
            now = timezone.now()
            if execution_time > now:
                delay_seconds = (execution_time - now).total_seconds()
                if delay_seconds > 0:
                    execute_algorithmic_step.apply_async(
                        args=[str(algo_order.algo_order_id), step, slice_size],
                        countdown=delay_seconds
                    )
                else:
                    execute_algorithmic_step.delay(str(algo_order.algo_order_id), step, slice_size)
            else:
                execute_algorithmic_step.delay(str(algo_order.algo_order_id), step, slice_size)
        
    except Exception as e:
        logger.error(f"TWAP execution error: {e}")
        raise


def execute_vwap_algorithm(algo_order: AlgorithmicOrder):
    """Execute Volume-Weighted Average Price algorithm"""
    try:
        # Simplified VWAP - in production would analyze historical volume patterns
        target_participation = algo_order.algorithm_parameters.get('participation_rate', 0.1)
        interval_minutes = algo_order.algorithm_parameters.get('interval_minutes', 5)
        
        # Calculate steps based on market volume
        estimated_steps = 10  # Simplified
        slice_size = algo_order.total_quantity // estimated_steps
        
        logger.info(f"Executing VWAP: {estimated_steps} steps, {slice_size} shares per step")
        
        for step in range(1, estimated_steps + 1):
            if algo_order.status != 'RUNNING':
                break
                
            execution_time = algo_order.start_time + timedelta(minutes=step * interval_minutes)
            execute_algorithmic_step.apply_async(
                args=[str(algo_order.algo_order_id), step, slice_size],
                eta=execution_time
            )
    
    except Exception as e:
        logger.error(f"VWAP execution error: {e}")
        raise


def execute_iceberg_algorithm(algo_order: AlgorithmicOrder):
    """Execute Iceberg algorithm"""
    try:
        iceberg_size = algo_order.algorithm_parameters.get('iceberg_size', 1000)
        refresh_interval = algo_order.algorithm_parameters.get('refresh_seconds', 30)
        
        steps = algo_order.total_quantity // iceberg_size
        logger.info(f"Executing ICEBERG: {steps} icebergs of {iceberg_size} shares")
        
        for step in range(1, steps + 1):
            if algo_order.status != 'RUNNING':
                break
                
            execute_algorithmic_step.apply_async(
                args=[str(algo_order.algo_order_id), step, iceberg_size],
                countdown=step * refresh_interval
            )
    
    except Exception as e:
        logger.error(f"ICEBERG execution error: {e}")
        raise


def execute_pov_algorithm(algo_order: AlgorithmicOrder):
    """Execute Percentage of Volume algorithm"""
    try:
        target_participation = algo_order.algorithm_parameters.get('participation_rate', 0.2)
        check_interval = algo_order.algorithm_parameters.get('check_interval_minutes', 2)
        
        # Simplified POV execution
        estimated_steps = 15
        base_slice_size = algo_order.total_quantity // estimated_steps
        
        logger.info(f"Executing POV: {target_participation*100}% participation")
        
        for step in range(1, estimated_steps + 1):
            if algo_order.status != 'RUNNING':
                break
                
            # Adjust slice size based on market volume (simplified)
            slice_size = int(base_slice_size * (0.8 + 0.4 * step / estimated_steps))
            
            execute_algorithmic_step.apply_async(
                args=[str(algo_order.algo_order_id), step, slice_size],
                countdown=step * check_interval * 60
            )
    
    except Exception as e:
        logger.error(f"POV execution error: {e}")
        raise


def execute_custom_algorithm(algo_order: AlgorithmicOrder):
    """Execute custom algorithm"""
    logger.info(f"Custom algorithm execution not implemented for {algo_order.algorithm_type}")
    raise NotImplementedError(f"Custom algorithm {algo_order.algorithm_type} not implemented")


@shared_task(bind=True)
def execute_algorithmic_step(self, algo_order_id: str, step: int, quantity: int):
    """Execute a single step of an algorithmic order"""
    try:
        algo_order = AlgorithmicOrder.objects.get(algo_order_id=algo_order_id)
        
        if algo_order.status != 'RUNNING':
            logger.info(f"Algorithm {algo_order_id} not running, skipping step {step}")
            return
        
        if algo_order.executed_quantity >= algo_order.total_quantity:
            logger.info(f"Algorithm {algo_order_id} already complete")
            return
            
        # Adjust quantity if it would exceed remaining
        remaining = algo_order.total_quantity - algo_order.executed_quantity
        actual_quantity = min(quantity, remaining)
        
        # Create child order
        child_order = create_child_order(algo_order, actual_quantity)
        
        # Record execution step
        execution = AlgorithmExecution.objects.create(
            algo_order=algo_order,
            execution_step=step,
            scheduled_time=timezone.now(),
            executed_quantity=actual_quantity,
            market_price=child_order.price or Decimal('100.00')  # Would get real market price
        )
        
        # Update algorithm progress
        algo_order.executed_quantity += actual_quantity
        
        # Calculate performance metrics
        total_steps = algo_order.algorithm_parameters.get('total_steps', 10)
        current_slippage = calculate_slippage(algo_order, child_order)
        
        if algo_order.average_execution_price:
            weighted_price = (
                (algo_order.average_execution_price * (algo_order.executed_quantity - actual_quantity)) +
                (child_order.price * actual_quantity)
            ) / algo_order.executed_quantity
            algo_order.average_execution_price = weighted_price
        else:
            algo_order.average_execution_price = child_order.price
        
        algo_order.save()
        
        # Publish progress event
        async_to_sync(publish_algorithm_execution_progress)(
            algo_order_id=str(algo_order.algo_order_id),
            execution_step=step,
            total_steps=total_steps,
            executed_quantity=algo_order.executed_quantity,
            remaining_quantity=algo_order.total_quantity - algo_order.executed_quantity,
            average_execution_price=algo_order.average_execution_price,
            current_slippage_bps=current_slippage,
            estimated_completion_time=algo_order.end_time,
            user_id=algo_order.user_id
        )
        
        # Check if algorithm is complete
        if algo_order.executed_quantity >= algo_order.total_quantity:
            complete_algorithm_execution(algo_order)
            
    except Exception as e:
        logger.error(f"Algorithm step execution failed: {e}")
        
        # Publish error event
        async_to_sync(publish_algorithm_execution_error)(
            algo_order_id=algo_order_id,
            error_type=type(e).__name__,
            error_message=str(e),
            execution_step=step,
            recovery_action="RETRY",
            user_id=getattr(algo_order, 'user_id', None)
        )


def create_child_order(algo_order: AlgorithmicOrder, quantity: int) -> SimulatedOrder:
    """Create a child order for algorithmic execution"""
    from apps.trading_simulation.models import SimulatedInstrument
    
    # Get simulated instrument
    sim_instrument = SimulatedInstrument.objects.filter(
        real_ticker=algo_order.instrument.real_ticker,
        exchange=algo_order.exchange
    ).first()
    
    # Create market order (simplified)
    child_order = SimulatedOrder.objects.create(
        user=algo_order.user,
        exchange=algo_order.exchange,
        instrument=sim_instrument,
        side=algo_order.side,
        order_type='MARKET',
        quantity=quantity,
        parent_order=None,  # Would link to parent if SimulatedOrder had this field
        status='PENDING'
    )
    
    # Simulate immediate fill at market price
    market_price = sim_instrument.get_current_simulated_price() or Decimal('100.00')
    child_order.price = market_price
    child_order.filled_quantity = quantity
    child_order.average_fill_price = market_price
    child_order.status = 'FILLED'
    child_order.first_fill_timestamp = timezone.now()
    child_order.last_fill_timestamp = timezone.now()
    child_order.completion_timestamp = timezone.now()
    child_order.save()
    
    return child_order


def calculate_slippage(algo_order: AlgorithmicOrder, child_order: SimulatedOrder) -> float:
    """Calculate slippage in basis points"""
    try:
        if not child_order.price:
            return 0.0
            
        # Use algorithm limit price as benchmark, or first execution price
        benchmark_price = algo_order.limit_price
        if not benchmark_price and algo_order.executions.exists():
            first_execution = algo_order.executions.first()
            benchmark_price = first_execution.market_price
        
        if not benchmark_price:
            return 0.0
            
        slippage = (child_order.price - benchmark_price) / benchmark_price * 10000
        if algo_order.side == 'SELL':
            slippage = -slippage  # Reverse for sell orders
            
        return float(slippage)
        
    except Exception as e:
        logger.error(f"Slippage calculation error: {e}")
        return 0.0


def complete_algorithm_execution(algo_order: AlgorithmicOrder):
    """Complete algorithm execution and publish final event"""
    try:
        # Update final status
        algo_order.status = 'COMPLETED'
        algo_order.completed_timestamp = timezone.now()
        
        # Calculate final metrics
        duration_minutes = 0
        if algo_order.started_timestamp:
            duration = algo_order.completed_timestamp - algo_order.started_timestamp
            duration_minutes = int(duration.total_seconds() / 60)
        
        # Calculate implementation shortfall (simplified)
        implementation_shortfall = 0.0
        if algo_order.limit_price and algo_order.average_execution_price:
            shortfall = (algo_order.average_execution_price - algo_order.limit_price) / algo_order.limit_price
            if algo_order.side == 'SELL':
                shortfall = -shortfall
            implementation_shortfall = float(shortfall * 10000)  # basis points
            algo_order.implementation_shortfall = Decimal(str(implementation_shortfall))
        
        algo_order.save()
        
        # Prepare performance metrics
        performance_metrics = {
            'total_child_orders': algo_order.executions.count(),
            'execution_efficiency': min(100.0, (algo_order.executed_quantity / algo_order.total_quantity) * 100),
            'average_slippage_bps': float(algo_order.total_slippage),
            'implementation_shortfall_bps': implementation_shortfall,
            'duration_minutes': duration_minutes
        }
        
        # Publish completion event
        async_to_sync(publish_algorithm_execution_completed)(
            algo_order_id=str(algo_order.algo_order_id),
            final_status='COMPLETED',
            total_executed_quantity=algo_order.executed_quantity,
            average_execution_price=algo_order.average_execution_price,
            total_slippage_bps=float(algo_order.total_slippage),
            implementation_shortfall=implementation_shortfall,
            execution_duration_minutes=duration_minutes,
            performance_metrics=performance_metrics,
            user_id=algo_order.user_id
        )
        
        logger.info(f"Algorithm {algo_order.algo_order_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Error completing algorithm execution: {e}")
