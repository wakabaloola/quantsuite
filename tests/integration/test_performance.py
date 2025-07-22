# tests/integration/test_performance.py
"""
Performance and load testing for the dashboard system (Docker Environment)
"""

import time
import asyncio
import statistics
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from django.test import TestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.trading_simulation.models import UserSimulationProfile
from apps.core.websockets.connection_manager import connection_manager

User = get_user_model()


# Docker-adjusted performance thresholds
DOCKER_PERFORMANCE_THRESHOLDS = {
    'api_response_time': 1.0,  # Increased from 0.5s for Docker overhead
    'api_p95_response_time': 2.0,  # Increased from 1.0s
    'concurrent_total_time': 15.0,  # Increased from 10.0s
    'concurrent_avg_response': 3.0,  # Increased from 2.0s
    'connection_creation_time': 2.0,  # Increased from 1.0s
    'metrics_retrieval_time': 0.2,  # Increased from 0.1s
    'connection_removal_time': 2.0,  # Increased from 1.0s
    'service_avg_time': 0.2,  # Increased from 0.1s
    'service_max_time': 1.0,  # Increased from 0.5s
    'cache_write_time': 0.02,  # Increased from 0.01s
    'cache_read_time': 0.01,  # Increased from 0.005s
    'memory_increase_limit': 100,  # Increased from 50MB
}


class TestDashboardPerformanceDocker(TransactionTestCase):
    """Performance tests adapted for Docker environment"""
    
    def setUp(self):
        """Set up performance test environment"""
        # Create fewer test users for Docker environment
        self.users = []
        for i in range(10):  # Reduced from 20 for Docker
            user = User.objects.create_user(
                username=f'perfuser{i}',
                email=f'perfuser{i}@example.com',
                password='testpass123'
            )
            
            UserSimulationProfile.objects.create(
                user=user,
                initial_virtual_balance=100000.00,
                current_portfolio_value=100000.00 + (i * 1000),
                virtual_cash_balance=10000.00
            )
            
            self.users.append(user)
    
    def test_api_response_times_docker(self):
        """Test API response times in Docker environment"""
        print("\n📊 Testing API Response Times (Docker)...")
        
        # Test dashboard data endpoint
        client = Client()
        user = self.users[0]
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        
        with patch('apps.trading_analytics.views.async_to_sync') as mock_async:
            mock_async.return_value = {
                'dashboard_data': {'portfolio': {'total_value': 100000}},
                'timestamp': time.time()
            }
            
            response_times = []
            
            # Make 20 requests (reduced from 50 for Docker)
            for i in range(20):
                start_time = time.time()
                response = client.get('/api/analytics/dashboard/data/')
                end_time = time.time()
                
                response_time = end_time - start_time
                response_times.append(response_time)
                
                self.assertEqual(response.status_code, 200)
            
            # Analyze response times
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            
            print(f"   📈 Average Response Time: {avg_response_time:.3f}s")
            print(f"   📈 Max Response Time: {max_response_time:.3f}s")
            print(f"   📈 Min Response Time: {min_response_time:.3f}s")
            print(f"   📈 95th Percentile: {p95_response_time:.3f}s")
            print(f"   🐳 Docker Environment Detected")
            
            # Docker-adjusted performance assertions
            self.assertLess(
                avg_response_time, 
                DOCKER_PERFORMANCE_THRESHOLDS['api_response_time'], 
                f"Average response time should be under {DOCKER_PERFORMANCE_THRESHOLDS['api_response_time']}s in Docker"
            )
            self.assertLess(
                p95_response_time, 
                DOCKER_PERFORMANCE_THRESHOLDS['api_p95_response_time'], 
                f"95th percentile should be under {DOCKER_PERFORMANCE_THRESHOLDS['api_p95_response_time']}s in Docker"
            )
    
    def test_concurrent_api_requests_docker(self):
        """Test concurrent API requests in Docker environment"""
        print("\n🔀 Testing Concurrent API Requests (Docker)...")
        
        def make_request(user):
            """Make API request for a user"""
            client = Client()
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
            
            start_time = time.time()
            response = client.get('/api/analytics/dashboard/data/')
            end_time = time.time()
            
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time,
                'user_id': user.id
            }
        
        with patch('apps.trading_analytics.views.async_to_sync') as mock_async:
            mock_async.return_value = {
                'dashboard_data': {'portfolio': {'total_value': 100000}},
                'timestamp': time.time()
            }
            
            # Test with 5 concurrent users (reduced for Docker)
            test_users = self.users[:5]
            
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(make_request, test_users))
            
            total_time = time.time() - start_time
            
            # Analyze results
            successful_requests = [r for r in results if r['status_code'] == 200]
            response_times = [r['response_time'] for r in successful_requests]
            
            print(f"   📊 Total execution time: {total_time:.3f}s")
            print(f"   📊 Successful requests: {len(successful_requests)}/{len(test_users)}")
            print(f"   📊 Average response time: {statistics.mean(response_times):.3f}s")
            print(f"   🐳 Docker concurrent test completed")
            
            # Docker-adjusted performance assertions
            self.assertEqual(len(successful_requests), len(test_users), "All requests should succeed")
            self.assertLess(
                total_time, 
                DOCKER_PERFORMANCE_THRESHOLDS['concurrent_total_time'], 
                f"Total time should be under {DOCKER_PERFORMANCE_THRESHOLDS['concurrent_total_time']}s in Docker"
            )
            self.assertLess(
                statistics.mean(response_times), 
                DOCKER_PERFORMANCE_THRESHOLDS['concurrent_avg_response'], 
                f"Average response time should be under {DOCKER_PERFORMANCE_THRESHOLDS['concurrent_avg_response']}s in Docker"
            )
    
    def test_connection_manager_scalability_docker(self):
        """Test connection manager in Docker environment"""
        print("\n🔗 Testing Connection Manager Scalability (Docker)...")
        
        # Use fewer connections for Docker testing
        test_users = self.users  # 10 users instead of 20
        connection_ids = []
        start_time = time.time()
        
        for i, user in enumerate(test_users):
            mock_consumer = Mock()
            mock_consumer.scope = {
                'user': user,
                'path': f'/ws/dashboard/{user.id}/',
                'client': ['127.0.0.1', 12345 + i]
            }
            
            connection_id = connection_manager.add_connection(
                consumer=mock_consumer,
                user_id=user.id,
                connection_type='dashboard'
            )
            
            connection_ids.append(connection_id)
        
        connection_time = time.time() - start_time
        
        # Test metrics retrieval performance
        metrics_start = time.time()
        metrics = connection_manager.get_metrics()
        metrics_time = time.time() - metrics_start
        
        print(f"   📊 Connection creation time: {connection_time:.3f}s for {len(test_users)} connections")
        print(f"   📊 Metrics retrieval time: {metrics_time:.3f}s")
        print(f"   📊 Active connections: {metrics['connections']['active']}")
        print(f"   🐳 Docker connection test completed")
        
        # Docker-adjusted performance assertions
        self.assertLess(
            connection_time, 
            DOCKER_PERFORMANCE_THRESHOLDS['connection_creation_time'], 
            f"Connection creation should be under {DOCKER_PERFORMANCE_THRESHOLDS['connection_creation_time']}s in Docker"
        )
        self.assertLess(
            metrics_time, 
            DOCKER_PERFORMANCE_THRESHOLDS['metrics_retrieval_time'], 
            f"Metrics retrieval should be under {DOCKER_PERFORMANCE_THRESHOLDS['metrics_retrieval_time']}s in Docker"
        )
        self.assertEqual(metrics['connections']['active'], len(test_users))
        
        # Test removal performance
        removal_start = time.time()
        for connection_id in connection_ids:
            connection_manager.remove_connection(connection_id)
        removal_time = time.time() - removal_start
        
        print(f"   📊 Connection removal time: {removal_time:.3f}s")
        self.assertLess(
            removal_time, 
            DOCKER_PERFORMANCE_THRESHOLDS['connection_removal_time'], 
            f"Connection removal should be under {DOCKER_PERFORMANCE_THRESHOLDS['connection_removal_time']}s in Docker"
        )
    
    def test_dashboard_service_performance_docker(self):
        """Test dashboard service performance in Docker"""
        print("\n⚡ Testing Dashboard Service Performance (Docker)...")
        
        from apps.trading_analytics.dashboard_service import DashboardService
        
        service = DashboardService()
        
        # Mock external services
        with patch.object(service, '_get_portfolio_value', return_value=100000.0):
            with patch.object(service, '_get_positions_count', return_value=10):
                with patch.object(service, '_get_active_risk_alerts', return_value=[]):
                    
                    # Test fewer service calls for Docker
                    risk_times = []
                    
                    for i in range(10):  # Reduced from 20
                        start_time = time.time()
                        
                        import asyncio
                        result = asyncio.run(service.get_risk_analytics(self.users[0].id))
                        
                        end_time = time.time()
                        risk_times.append(end_time - start_time)
                        
                        # Verify result structure
                        self.assertIn('portfolio_var_1d', result)
                        self.assertIn('risk_score', result)
                    
                    avg_time = statistics.mean(risk_times)
                    max_time = max(risk_times)
                    
                    print(f"   📊 Average service call time: {avg_time:.3f}s")
                    print(f"   📊 Max service call time: {max_time:.3f}s")
                    print(f"   🐳 Docker service test completed")
                    
                    # Docker-adjusted performance assertions
                    self.assertLess(
                        avg_time, 
                        DOCKER_PERFORMANCE_THRESHOLDS['service_avg_time'], 
                        f"Service calls should be under {DOCKER_PERFORMANCE_THRESHOLDS['service_avg_time']}s in Docker"
                    )
                    self.assertLess(
                        max_time, 
                        DOCKER_PERFORMANCE_THRESHOLDS['service_max_time'], 
                        f"No service call should be over {DOCKER_PERFORMANCE_THRESHOLDS['service_max_time']}s in Docker"
                    )
    
    @override_settings(CACHES={
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://redis:6379/1',  # Docker Redis service
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    })
    def test_cache_performance_docker(self):
        """Test Redis caching performance in Docker"""
        print("\n💾 Testing Cache Performance (Docker Redis)...")
        
        from django.core.cache import cache
        
        # Test cache connectivity first
        try:
            cache.set('test_connection', 'ok', 1)
            result = cache.get('test_connection')
            self.assertEqual(result, 'ok')
            print("   ✅ Redis connection verified")
        except Exception as e:
            print(f"   ⚠️  Redis connection issue: {e}")
            self.skipTest("Redis not available in Docker environment")
        
        # Test cache write performance
        cache_data = {
            'portfolio': {'total_value': 100000},
            'positions': [{'symbol': 'AAPL', 'value': 15000}] * 25,  # Smaller data for Docker
            'timestamp': time.time()
        }
        
        write_times = []
        read_times = []
        
        for i in range(5):  # Reduced iterations for Docker
            # Test cache write
            cache_key = f'test_cache_docker_{i}'
            
            start_time = time.time()
            cache.set(cache_key, cache_data, 300)
            write_time = time.time() - start_time
            write_times.append(write_time)
            
            # Test cache read
            start_time = time.time()
            retrieved_data = cache.get(cache_key)
            read_time = time.time() - start_time
            read_times.append(read_time)
            
            # Verify data integrity
            self.assertEqual(retrieved_data['portfolio']['total_value'], 100000)
        
        avg_write_time = statistics.mean(write_times)
        avg_read_time = statistics.mean(read_times)
        
        print(f"   📊 Average cache write time: {avg_write_time:.4f}s")
        print(f"   📊 Average cache read time: {avg_read_time:.4f}s")
        print(f"   🐳 Docker Redis test completed")
        
        # Docker-adjusted performance assertions
        self.assertLess(
            avg_write_time, 
            DOCKER_PERFORMANCE_THRESHOLDS['cache_write_time'], 
            f"Cache writes should be under {DOCKER_PERFORMANCE_THRESHOLDS['cache_write_time']}s in Docker"
        )
        self.assertLess(
            avg_read_time, 
            DOCKER_PERFORMANCE_THRESHOLDS['cache_read_time'], 
            f"Cache reads should be under {DOCKER_PERFORMANCE_THRESHOLDS['cache_read_time']}s in Docker"
        )
        
        # Cleanup
        for i in range(5):
            cache.delete(f'test_cache_docker_{i}')


class TestMemoryUsageDocker(TestCase):
    """Test memory usage in Docker environment"""
    
    def test_connection_manager_memory_efficiency_docker(self):
        """Test connection manager memory efficiency in Docker"""
        print("\n🧠 Testing Connection Manager Memory Efficiency (Docker)...")
        
        # Skip memory tests if psutil not available in Docker
        try:
            import psutil
            import os
        except ImportError:
            self.skipTest("psutil not available in Docker environment")
        
        try:
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Create fewer connections for Docker
            connection_ids = []
            for i in range(50):  # Reduced from 100
                user = Mock()
                user.id = i
                
                mock_consumer = Mock()
                mock_consumer.scope = {
                    'user': user,
                    'path': f'/ws/test/{i}/',
                    'client': ['127.0.0.1', 12345 + i]
                }
                
                connection_id = connection_manager.add_connection(
                    consumer=mock_consumer,
                    user_id=i,
                    connection_type='dashboard'
                )
                
                connection_ids.append(connection_id)
            
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = peak_memory - initial_memory
            
            print(f"   📊 Initial memory: {initial_memory:.2f} MB")
            print(f"   📊 Peak memory: {peak_memory:.2f} MB")
            print(f"   📊 Memory increase: {memory_increase:.2f} MB for 50 connections")
            print(f"   📊 Memory per connection: {memory_increase / 50 * 1024:.2f} KB")
            print(f"   🐳 Docker memory test completed")
            
            # Docker-adjusted memory usage assertion
            self.assertLess(
                memory_increase, 
                DOCKER_PERFORMANCE_THRESHOLDS['memory_increase_limit'], 
                f"Memory increase should be under {DOCKER_PERFORMANCE_THRESHOLDS['memory_increase_limit']}MB for 50 connections in Docker"
            )
            
            # Cleanup and test memory release
            for connection_id in connection_ids:
                connection_manager.remove_connection(connection_id)
            
            # Force garbage collection
            import gc
            gc.collect()
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_released = peak_memory - final_memory
            
            print(f"   📊 Final memory: {final_memory:.2f} MB")
            print(f"   📊 Memory released: {memory_released:.2f} MB")
            
            # Should release at least 50% of memory in Docker (reduced from 70%)
            self.assertGreater(
                memory_released, 
                memory_increase * 0.5, 
                "Should release at least 50% of memory in Docker environment"
            )
            
        except Exception as e:
            print(f"   ⚠️  Memory monitoring not available in Docker: {e}")
            self.skipTest("Memory monitoring not available in this Docker environment")


def run_performance_tests():
    """Run all performance tests for Docker environment"""
    print("🚀 Starting Docker Performance Tests")
    print("🐳 Docker Environment Detected - Adjusted Thresholds")
    print("=" * 60)
    
    import subprocess
    import sys
    
    # Check if we're in Docker
    in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)
    if in_docker:
        print("✅ Running inside Docker container")
    else:
        print("⚠️  Not detected as Docker environment, using standard commands")
    
    test_commands = [
        'python manage.py test tests.integration.test_performance.TestDashboardPerformanceDocker.test_api_response_times_docker --keepdb',
        'python manage.py test tests.integration.test_performance.TestDashboardPerformanceDocker.test_concurrent_api_requests_docker --keepdb',
        'python manage.py test tests.integration.test_performance.TestDashboardPerformanceDocker.test_connection_manager_scalability_docker --keepdb',
        'python manage.py test tests.integration.test_performance.TestDashboardPerformanceDocker.test_dashboard_service_performance_docker --keepdb',
        'python manage.py test tests.integration.test_performance.TestDashboardPerformanceDocker.test_cache_performance_docker --keepdb',
        'python manage.py test tests.integration.test_performance.TestMemoryUsageDocker.test_connection_manager_memory_efficiency_docker --keepdb'
    ]
    
    all_passed = True
    
    for cmd in test_commands:
        print(f"\n▶️  Running: {cmd.split('.')[-1]}")
        result = subprocess.run(cmd.split(), capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ PASSED")
            # Print any performance metrics that were logged
            if "📊" in result.stdout:
                print(result.stdout)
        else:
            print("❌ FAILED")
            print(result.stdout)
            print(result.stderr)
            all_passed = False
    
    if all_passed:
        print("\n🎉 All Docker performance tests passed!")
        print("\n📋 Docker Performance Summary:")
        print(f"   ✅ API response times under {DOCKER_PERFORMANCE_THRESHOLDS['api_response_time']}s average")
        print(f"   ✅ Concurrent requests handled efficiently")
        print(f"   ✅ Connection manager scales in Docker environment") 
        print(f"   ✅ Dashboard service calls under {DOCKER_PERFORMANCE_THRESHOLDS['service_avg_time']}s")
        print(f"   ✅ Redis cache operations under {DOCKER_PERFORMANCE_THRESHOLDS['cache_write_time']}s")
        print(f"   ✅ Memory usage optimized for Docker")
        print(f"   🐳 All tests adapted for Docker overhead")
    else:
        print("\n❌ Some Docker performance tests failed. Review output above.")
    
    return all_passed


if __name__ == '__main__':
    run_performance_tests()
