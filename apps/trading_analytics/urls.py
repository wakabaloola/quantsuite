# apps/trading_analytics/urls.py
"""
SIMULATED Trading Analytics URL Configuration
==========================================
URL patterns for VIRTUAL trading analytics and dashboard endpoints.
All endpoints analyze PAPER TRADING performance.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# App namespace for URL reversing
app_name = 'trading_analytics'

# DRF Router for ViewSets
router = DefaultRouter()
router.register(r'performance', views.TradingPerformanceViewSet, basename='performance')
router.register(r'portfolio', views.PortfolioAnalyticsViewSet, basename='portfolio')
router.register(r'reports', views.TradingReportsViewSet, basename='reports')

# URL patterns combining router URLs and custom endpoints
urlpatterns = [
    # DRF ViewSet URLs (performance, portfolio analytics, reports)
    path('', include(router.urls)),
    
    # Dashboard API endpoints (function-based views)
    path('dashboard/data/', views.dashboard_data_api, name='dashboard_data'),
    path('dashboard/summary/', views.dashboard_summary_api, name='dashboard_summary'),
    path('dashboard/health/', views.dashboard_health_api, name='dashboard_health'),
    path('dashboard/configure/', views.dashboard_configure_api, name='dashboard_configure'),
    path('portfolio/realtime/', views.real_time_portfolio_api, name='real_time_portfolio'),
    
    # Additional analytics endpoints (if you want to add more later)
    # path('risk/', views.risk_analytics_api, name='risk_analytics'),
    # path('benchmarks/', views.benchmark_comparison_api, name='benchmark_comparison'),
]
