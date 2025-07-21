# apps/trading_simulation/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/trading/orders/(?P<user_id>\w+)/$', consumers.OrderUpdatesConsumer.as_asgi()),
    re_path(r'ws/trading/portfolio/(?P<user_id>\w+)/$', consumers.PortfolioUpdatesConsumer.as_asgi()),
    re_path(r'ws/trading/market/(?P<symbol>\w+)/$', consumers.MarketDataConsumer.as_asgi()),
    re_path(r'ws/trading/risk/(?P<user_id>\w+)/$', consumers.RiskAlertsConsumer.as_asgi()),
    re_path(r'ws/trading/algorithms/(?P<user_id>\w+)/$', consumers.AlgorithmUpdatesConsumer.as_asgi()),
]
