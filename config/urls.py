# config/urls.py
"""Enhanced URL configuration for QSuite quantitative research platform"""
"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Import viewsets
from apps.market_data.views import (
    DataSourceViewSet, ExchangeViewSet, TickerViewSet, MarketDataViewSet,
    DataIntegrationViewSet, TechnicalAnalysisViewSet, AnalyticsViewSet,
    ScreeningViewSet, PortfolioViewSet
)

# API Documentation
schema_view = get_schema_view(
    openapi.Info(
        title="QuantSuite Quantitative Research Platform API",
        default_version='v1',
        description="""
        Professional-grade API for quantitative research and algorithmic trading.

        ## Features
        - **Global Market Data**: Real-time and historical data from multiple exchanges
        - **Technical Analysis**: RSI, MACD, Bollinger Bands, and custom indicators
        - **Portfolio Analytics**: Performance metrics, correlation analysis, risk assessment
        - **Stock Screening**: Technical and fundamental screening capabilities
        - **Data Integration**: yfinance and Alpha Vantage integration
        - **Backtesting**: Strategy development and testing framework

        ## Data Sources
        - Yahoo Finance (via yfinance) - Global markets, real-time quotes
        - Alpha Vantage - US markets, fundamental data
        - Manual data upload and custom integrations

        ## Supported Markets
        - US: NYSE, NASDAQ, AMEX
        - UK: LSE (London Stock Exchange)
        - Europe: Euronext, Xetra, Borsa Italiana
        - Asia: TSE, HKEX, NSE, BSE
        - And many more via yfinance integration

        ## Authentication
        All endpoints require JWT authentication. Get your token from `/api/auth/login/`
        """,
        contact=openapi.Contact(email="admin@quantsuite.io"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[],
)

# Main API Router
router = DefaultRouter()

# Core market data endpoints
router.register(r'data-sources', DataSourceViewSet, basename='datasource')
router.register(r'exchanges', ExchangeViewSet, basename='exchange')
router.register(r'tickers', TickerViewSet, basename='ticker')
router.register(r'market-data', MarketDataViewSet, basename='marketdata')

# Data integration endpoints
router.register(r'integrations', DataIntegrationViewSet, basename='integration')

# Analytics and technical analysis
router.register(r'technical', TechnicalAnalysisViewSet, basename='technical')
router.register(r'analytics', AnalyticsViewSet, basename='analytics')
router.register(r'screening', ScreeningViewSet, basename='screening')

# Portfolio management
router.register(r'portfolios', PortfolioViewSet, basename='portfolio')

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),

    # Authentication endpoints
    path('api/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # API v1 endpoints
    path('api/v1/', include(router.urls)),

    # Additional API utilities
    path('api/v1/auth/', include('rest_framework.urls')),  # Browsable API auth

    # API Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='api-docs'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='api-redoc'),
    path('api/schema/', schema_view.without_ui(cache_timeout=0), name='api-schema'),

    # Health check endpoint
    path('health/', include('apps.core.urls')),  # We'll create this
]

# Development-specific URLs
from django.conf import settings
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

    # Serve media files in development
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
