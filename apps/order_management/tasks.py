# apps/order_management/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta

from .models import AlgorithmicOrder, AlgorithmExecution
from .algorithm_services import AlgorithmExecutionEngine

logger = get_task_logger(__name__)


@shared_task
def sync_algorithm_market_data():
    """Synchronize market data for running algorithms"""
    try:
        # Get all running algorithms
        running_algorithms = AlgorithmicOrder.objects.filter(
            status='RUNNING'
        ).select_related('instrument__real_ticker')
        
        if not running_algorithms.exists():
            return {'status': 'NO_RUNNING_ALGORITHMS'}
        
        engine = AlgorithmExecutionEngine()
        updated_count = 0
        
        for algo_order in running_algorithms:
            try:
                # Get enhanced market data
                market_data = engine._get_enhanced_market_data(algo_order.instrument)
                
                # Update algorithm with latest market conditions
                algo_order.last_market_check = timezone.now()
                algo_order.save(update_fields=['last_market_check'])
                
                # Check if any pending executions should trigger
                pending_executions = AlgorithmExecution.objects.filter(
                    algo_order=algo_order,
                    execution_time__isnull=True,
                    scheduled_time__lte=timezone.now()
                )
                
                for execution in pending_executions:
                    if engine.process_algorithm_step(execution):
                        updated_count += 1
                
            except Exception as e:
                logger.error(f"Error syncing data for algorithm {algo_order.algo_order_id}: {e}")
                continue
        
        logger.info(f"Market data sync completed: {updated_count} executions processed")
        
        return {
            'status': 'SUCCESS',
            'algorithms_checked': running_algorithms.count(),
            'executions_processed': updated_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Market data sync failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}


@shared_task
def update_algorithm_technical_indicators():
    """Update technical indicators for algorithm decision making"""
    try:
        from apps.market_data.tasks import calculate_technical_indicators_single
        
        # Get symbols for running algorithms
        running_algorithms = AlgorithmicOrder.objects.filter(
            status__in=['RUNNING', 'PAUSED']
        ).select_related('instrument__real_ticker')
        
        symbols = list(set([
            algo.instrument.real_ticker.symbol 
            for algo in running_algorithms
        ]))
        
        if not symbols:
            return {'status': 'NO_SYMBOLS'}
        
        # Submit technical indicator calculations
        task_results = []
        for symbol in symbols:
            result = calculate_technical_indicators_single.delay(
                symbol=symbol,
                timeframe='1d',
                indicators=['rsi', 'macd', 'bollinger_bands', 'sma_20', 'sma_50']
            )
            task_results.append(result.id)
        
        return {
            'status': 'SUCCESS',
            'symbols_updated': len(symbols),
            'task_ids': task_results,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Technical indicators update failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}
