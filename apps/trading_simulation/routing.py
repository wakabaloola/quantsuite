# apps/trading_simulation/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/trading/orders/(?P<user_id>\w+)/$', consumers.OrderUpdatesConsumer.as_asgi()),
    re_path(r'ws/trading/portfolio/(?P<user_id>\w+)/$', consumers.PortfolioUpdatesConsumer.as_asgi()),
    re_path(r'ws/trading/market/(?P<symbol>\w+)/$', consumers.MarketDataConsumer.as_asgi()),
    re_path(r'ws/trading/risk/(?P<user_id>\w+)/$', consumers.RiskAlertsConsumer.as_asgi()),

    # Real-time streaming consumer
    re_path(r'ws/streaming/(?P<symbol>\w+)/$', consumers.RealTimeMarketDataConsumer.as_asgi()),
    re_path(r'ws/streaming/$', consumers.RealTimeMarketDataConsumer.as_asgi()),

    # Technical signals WebSocket
    re_path(r'ws/signals/(?P<symbol>\w+)/$', consumers.TechnicalSignalsConsumer.as_asgi()),
    re_path(r'ws/signals/$', consumers.TechnicalSignalsConsumer.as_asgi()),

    # Algorithm execution WebSocket
    re_path(r'ws/algorithms/(?P<user_id>\w+)/$', consumers.AlgorithmExecutionConsumer.as_asgi()),

    # WebSocket monitoring (admin only)
    re_path(r'ws/monitoring/$', consumers.WebSocketMonitoringConsumer.as_asgi()),

    # Integrated Market Dashboard (comprehensive feed)
    re_path(r'ws/dashboard/(?P<user_id>\w+)/$', consumers.IntegratedMarketDashboardConsumer.as_asgi()),
]
