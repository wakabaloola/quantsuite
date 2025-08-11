# tests/integration/test_performance.py
"""
Performance and load testing for the dashboard system (Docker Environment)
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.trading_simulation.models import UserSimulationProfile

User = get_user_model()

class TestDashboardPerformanceDocker(TransactionTestCase):
    """Performance tests adapted for Docker environment"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = []
        for i in range(5):
            user = User.objects.create_user(username=f'perfuser{i}', password='testpassword')
            UserSimulationProfile.objects.create(user=user)
            cls.users.append(user)

    def test_concurrent_api_requests_docker(self):
        """Test concurrent API requests in Docker environment"""
        print("\\n🔀 Testing Concurrent API Requests (Docker)...")

        def make_request(user):
            client = Client()
            refresh = RefreshToken.for_user(user)
            auth_header = f'Bearer {str(refresh.access_token)}'
            response = client.get('/api/analytics/dashboard/data/', HTTP_AUTHORIZATION=auth_header)
            return response.status_code

        with patch('apps.trading_analytics.views.dashboard_service.get_unified_dashboard_data') as mock_get_data:
            async def mock_async_get_data(*args, **kwargs):
                await asyncio.sleep(0.01)
                return {'dashboard_data': {}}
            mock_get_data.side_effect = mock_async_get_data

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(make_request, self.users))

            successful_requests = [r for r in results if r == 200]
            print(f"   📊 Successful requests: {len(successful_requests)}/{len(self.users)}")
            self.assertEqual(len(successful_requests), len(self.users))

