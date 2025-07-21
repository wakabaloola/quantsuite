# apps/market_data/urls.py
from .analysis import views as analysis_views
from .streaming import views as streaming_views

urlpatterns = [
    # Streaming service endpoints
    path('streaming/start/', streaming_views.start_streaming, name='start_streaming'),
    path('streaming/stop/', streaming_views.stop_streaming, name='stop_streaming'),
    path('streaming/status/', streaming_views.streaming_status, name='streaming_status'),
    path('streaming/subscribe/', streaming_views.subscribe_symbols, name='subscribe_symbols'),
    path('streaming/unsubscribe/', streaming_views.unsubscribe_symbols, name='unsubscribe_symbols'),
    path('streaming/quote/<str:symbol>/', streaming_views.get_quote, name='get_quote'),

    # Enhanced technical analysis endpoints
    path('analysis/symbol/<str:symbol>/', analysis_views.analyze_symbol, name='analyze_symbol'),
    path('analysis/signal/<str:symbol>/', analysis_views.get_cached_signal, name='get_cached_signal'),
    path('analysis/watchlist/', analysis_views.analyze_watchlist, name='analyze_watchlist'),
    path('analysis/metrics/', analysis_views.get_service_metrics, name='ta_service_metrics'),
    path('analysis/history/<str:symbol>/', analysis_views.get_signal_history, name='signal_history'),

    # Etc.
]
