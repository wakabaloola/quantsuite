# apps/order_management/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SimulatedOrderViewSet, SimulatedTradeViewSet, OrderBookViewSet,
    TradingEngineViewSet
)
from .algorithm_views import AlgorithmicOrderViewSet, AlgorithmExecutionViewSet, CustomStrategyViewSet

# Create router for viewsets
router = DefaultRouter()

# Register standard order management viewsets
router.register(r'orders', SimulatedOrderViewSet, basename='orders')
router.register(r'trades', SimulatedTradeViewSet, basename='trades')
router.register(r'order-books', OrderBookViewSet, basename='order-books')
router.register(r'trading-engine', TradingEngineViewSet, basename='trading-engine')

# Register algorithm viewsets
router.register(r'algorithmic-orders', AlgorithmicOrderViewSet, basename='algorithmic-orders')
router.register(r'algorithm-executions', AlgorithmExecutionViewSet, basename='algorithm-executions')
router.register(r'custom-strategies', CustomStrategyViewSet, basename='custom-strategies')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
]
