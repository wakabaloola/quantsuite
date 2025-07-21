from .streaming import views as streaming_views

urlpatterns = [
    # Streaming service endpoints
    path('streaming/start/', streaming_views.start_streaming, name='start_streaming'),
    path('streaming/stop/', streaming_views.stop_streaming, name='stop_streaming'),
    path('streaming/status/', streaming_views.streaming_status, name='streaming_status'),
    path('streaming/subscribe/', streaming_views.subscribe_symbols, name='subscribe_symbols'),
    path('streaming/unsubscribe/', streaming_views.unsubscribe_symbols, name='unsubscribe_symbols'),
    path('streaming/quote/<str:symbol>/', streaming_views.get_quote, name='get_quote'),

    # Etc.
]
