# apps/core/views.py
"""Core application views for health checks and system monitoring"""
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import time
import psutil
from decimal import Decimal


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Basic health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'version': '1.0.0',
        'environment': 'development'  # Would come from settings
    })


@api_view(['GET'])
def system_metrics(request):
    """Comprehensive system health and performance metrics"""
    start_time = time.time()
    
    # Database health
    db_healthy = True
    db_response_time = None
    try:
        db_start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_response_time = (time.time() - db_start) * 1000  # Convert to ms
    except Exception as e:
        db_healthy = False
        db_error = str(e)
    
    # Cache health
    cache_healthy = True
    cache_response_time = None
    try:
        cache_start = time.time()
        cache.set('health_check', 'ok', 30)
        cache.get('health_check')
        cache_response_time = (time.time() - cache_start) * 1000
    except Exception as e:
        cache_healthy = False
        cache_error = str(e)
    
    # System resources
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        system_metrics = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': memory.percent,
            'memory_available_gb': round(memory.available / (1024**3), 2),
            'disk_percent': disk.percent,
            'disk_free_gb': round(disk.free / (1024**3), 2),
        }
    except Exception:
        system_metrics = {'error': 'Unable to get system metrics'}
    
    # Application metrics
    try:
        from apps.market_data.models import Ticker, MarketData, DataIngestionLog
        
        app_metrics = {
            'total_tickers': Ticker.objects.count(),
            'active_tickers': Ticker.objects.filter(is_active=True).count(),
            'total_market_data_records': MarketData.objects.count(),
            'recent_ingestions': DataIngestionLog.objects.filter(
                start_time__gte=timezone.now() - timezone.timedelta(days=1)
            ).count(),
        }
    except Exception:
        app_metrics = {'error': 'Unable to get application metrics'}
    
    # Overall health status
    overall_healthy = db_healthy and cache_healthy
    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    response_time = (time.time() - start_time) * 1000
    
    return Response({
        'status': 'healthy' if overall_healthy else 'unhealthy',
        'timestamp': timezone.now().isoformat(),
        'response_time_ms': round(response_time, 2),
        'services': {
            'database': {
                'status': 'healthy' if db_healthy else 'unhealthy',
                'response_time_ms': round(db_response_time, 2) if db_response_time else None,
                'error': db_error if not db_healthy else None
            },
            'cache': {
                'status': 'healthy' if cache_healthy else 'unhealthy',
                'response_time_ms': round(cache_response_time, 2) if cache_response_time else None,
                'error': cache_error if not cache_healthy else None
            }
        },
        'system': system_metrics,
        'application': app_metrics
    }, status=status_code)


@api_view(['GET'])
def database_health(request):
    """Detailed database health check"""
    try:
        start_time = time.time()
        
        with connection.cursor() as cursor:
            # Basic connectivity
            cursor.execute("SELECT 1")
            
            # Database stats
            cursor.execute("""
                SELECT 
                    pg_database_size(current_database()) as db_size,
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                    (SELECT setting FROM pg_settings WHERE name = 'max_connections') as max_connections
            """)
            db_size, active_connections, max_connections = cursor.fetchone()
            
            # Table stats
            cursor.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    n_tup_ins + n_tup_upd + n_tup_del as total_writes,
                    seq_scan + idx_scan as total_scans
                FROM pg_stat_user_tables 
                WHERE schemaname = 'public'
                ORDER BY total_writes DESC 
                LIMIT 5
            """)
            table_stats = cursor.fetchall()
        
        response_time = (time.time() - start_time) * 1000
        
        return Response({
            'status': 'healthy',
            'response_time_ms': round(response_time, 2),
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / (1024**2), 2),
            'connections': {
                'active': active_connections,
                'max': int(max_connections),
                'usage_percent': round((active_connections / int(max_connections)) * 100, 2)
            },
            'top_tables': [
                {
                    'schema': row[0],
                    'table': row[1],
                    'total_writes': row[2],
                    'total_scans': row[3]
                }
                for row in table_stats
            ]
        })
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def cache_health(request):
    """Detailed cache health check"""
    try:
        start_time = time.time()
        
        # Test basic operations
        test_key = f'health_test_{int(time.time())}'
        cache.set(test_key, 'test_value', 60)
        retrieved_value = cache.get(test_key)
        cache.delete(test_key)
        
        if retrieved_value != 'test_value':
            raise Exception('Cache read/write test failed')
        
        response_time = (time.time() - start_time) * 1000
        
        # Get cache info if using Redis
        cache_info = {}
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")
            info = redis_conn.info()
            
            cache_info = {
                'used_memory_human': info.get('used_memory_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
            }
            
            # Calculate hit rate
            hits = cache_info['keyspace_hits']
            misses = cache_info['keyspace_misses']
            if hits + misses > 0:
                cache_info['hit_rate_percent'] = round((hits / (hits + misses)) * 100, 2)
            
        except Exception:
            cache_info = {'error': 'Unable to get detailed cache info'}
        
        return Response({
            'status': 'healthy',
            'response_time_ms': round(response_time, 2),
            'cache_info': cache_info
        })
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def services_health(request):
    """Check health of external services and integrations"""
    services_status = {}
    
    # Test yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        if info and 'symbol' in info:
            services_status['yfinance'] = {'status': 'healthy', 'test_symbol': 'AAPL'}
        else:
            services_status['yfinance'] = {'status': 'degraded', 'message': 'Limited response'}
    except Exception as e:
        services_status['yfinance'] = {'status': 'unhealthy', 'error': str(e)}
    
    # Test Alpha Vantage (if API key is configured)
    try:
        from django.conf import settings
        if hasattr(settings, 'ALPHA_VANTAGE_API_KEY') and settings.ALPHA_VANTAGE_API_KEY:
            import requests
            response = requests.get(
                'https://www.alphavantage.co/query',
                params={
                    'function': 'GLOBAL_QUOTE',
                    'symbol': 'AAPL',
                    'apikey': settings.ALPHA_VANTAGE_API_KEY
                },
                timeout=10
            )
            if response.status_code == 200 and 'Global Quote' in response.json():
                services_status['alpha_vantage'] = {'status': 'healthy'}
            else:
                services_status['alpha_vantage'] = {'status': 'degraded', 'response_code': response.status_code}
        else:
            services_status['alpha_vantage'] = {'status': 'not_configured', 'message': 'API key not set'}
    except Exception as e:
        services_status['alpha_vantage'] = {'status': 'unhealthy', 'error': str(e)}
    
    # Check Celery workers (if available)
    try:
        from celery import current_app
        inspect = current_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            worker_count = len(active_workers)
            services_status['celery'] = {
                'status': 'healthy',
                'active_workers': worker_count,
                'workers': list(active_workers.keys())
            }
        else:
            services_status['celery'] = {'status': 'unhealthy', 'message': 'No active workers'}
            
    except Exception as e:
        services_status['celery'] = {'status': 'unknown', 'error': str(e)}
    
    # Overall status
    healthy_services = sum(1 for service in services_status.values() 
                          if service.get('status') == 'healthy')
    total_services = len(services_status)
    
    overall_status = 'healthy' if healthy_services == total_services else 'degraded'
    status_code = status.HTTP_200_OK if overall_status == 'healthy' else status.HTTP_206_PARTIAL_CONTENT
    
    return Response({
        'status': overall_status,
        'services': services_status,
        'summary': {
            'healthy': healthy_services,
            'total': total_services,
            'health_percentage': round((healthy_services / total_services) * 100, 2)
        }
    }, status=status_code)
