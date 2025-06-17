# apps/market_data/views.py
"""Enhanced API views for quantitative research platform"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Avg, Max, Min, Count
from django.utils import timezone
from datetime import timedelta
import pandas as pd
from decimal import Decimal

from .models import (
    DataSource, Exchange, Ticker, MarketData, FundamentalData,
    TechnicalIndicator, DataIngestionLog, Portfolio, Position
)
from .serializers import (
    DataSourceSerializer, ExchangeSerializer, TickerListSerializer,
    TickerDetailSerializer, TickerCreateSerializer, MarketDataSerializer,
    MarketDataBulkSerializer, FundamentalDataSerializer, TechnicalIndicatorSerializer,
    DataIngestionLogSerializer, DataIngestionRequestSerializer,
    QuoteRequestSerializer, QuoteResponseSerializer, PortfolioSerializer,
    PositionSerializer, SymbolSearchSerializer, SymbolSearchResultSerializer,
    TechnicalIndicatorsRequestSerializer, CorrelationMatrixRequestSerializer,
    StockScreeningRequestSerializer, AnalyticsRequestSerializer
)
from .services import DataIngestionService, YFinanceService, AlphaVantageService
from .filters import TickerFilter, MarketDataFilter


class DataSourceViewSet(viewsets.ModelViewSet):
    """Enhanced data source management"""
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name', 'code']
    filterset_fields = ['requires_api_key', 'is_active']


class ExchangeViewSet(viewsets.ModelViewSet):
    """Exchange management"""
    queryset = Exchange.objects.all()
    serializer_class = ExchangeSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name', 'code', 'country']
    filterset_fields = ['country', 'currency', 'is_active']


class TickerViewSet(viewsets.ModelViewSet):
    """Enhanced ticker management with global market support"""
    queryset = Ticker.objects.select_related('exchange', 'sector', 'industry', 'data_source')
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['symbol', 'name', 'description']
    filterset_class = TickerFilter
    ordering_fields = ['symbol', 'market_cap', 'created_at']
    ordering = ['symbol']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TickerListSerializer
        elif self.action == 'create':
            return TickerCreateSerializer
        return TickerDetailSerializer
    
    @action(detail=True, methods=['get'])
    def latest_price(self, request, pk=None):
        """Get latest market data for ticker"""
        ticker = self.get_object()
        try:
            latest_data = ticker.market_data.latest('timestamp')
            serializer = MarketDataSerializer(latest_data)
            return Response(serializer.data)
        except MarketData.DoesNotExist:
            return Response({'error': 'No market data available'}, 
                          status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get comprehensive statistics for ticker"""
        ticker = self.get_object()
        
        # Basic market data stats
        market_data_stats = ticker.market_data.aggregate(
            avg_close=Avg('close'),
            max_high=Max('high'),
            min_low=Min('low'),
            record_count=Count('id')
        )
        
        # Price performance (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_data = ticker.market_data.filter(timestamp__gte=thirty_days_ago)
        
        if recent_data.exists():
            first_price = recent_data.last().close
            latest_price = recent_data.first().close
            performance_30d = float((latest_price - first_price) / first_price * 100)
        else:
            performance_30d = None
        
        return Response({
            'ticker': ticker.symbol,
            'market_data_stats': market_data_stats,
            'performance_30d_percent': performance_30d,
            'last_updated': ticker.last_updated
        })
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        """Advanced ticker search with external APIs"""
        serializer = SymbolSearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        query = serializer.validated_data['query']
        country = serializer.validated_data.get('country')
        limit = serializer.validated_data.get('limit', 20)
        
        # Search in database first
        db_results = []
        db_query = self.queryset.filter(
            Q(symbol__icontains=query) | Q(name__icontains=query)
        )
        
        if country:
            db_query = db_query.filter(country=country)
        
        for ticker in db_query[:limit//2]:
            db_results.append({
                'symbol': ticker.symbol,
                'name': ticker.name,
                'exchange': ticker.exchange.code,
                'country': ticker.country,
                'currency': ticker.currency,
                'sector': ticker.sector.name if ticker.sector else None,
                'industry': ticker.industry.name if ticker.industry else None,
                'source': 'database'
            })
        
        # Search with yfinance for additional results
        yfinance_service = YFinanceService()
        external_results = yfinance_service.search_ticker(query, country)
        
        # Combine results
        all_results = db_results + external_results[:limit-len(db_results)]
        
        return Response({
            'query': query,
            'total_results': len(all_results),
            'results': all_results
        })


class MarketDataViewSet(viewsets.ModelViewSet):
    """Enhanced market data with comprehensive filtering"""
    serializer_class = MarketDataSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = MarketDataFilter
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        return MarketData.objects.select_related('ticker', 'data_source')
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """Get historical market data with advanced filtering"""
        symbol = request.query_params.get('symbol')
        if not symbol:
            return Response({'error': 'symbol parameter required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            ticker = Ticker.objects.get(symbol=symbol)
        except Ticker.DoesNotExist:
            return Response({'error': f'Ticker {symbol} not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Get query parameters
        period = request.query_params.get('period', '1y')
        interval = request.query_params.get('interval', '1d')
        start_date = request.query_params.get('start')
        end_date = request.query_params.get('end')
        format_type = request.query_params.get('format', 'json')
        
        # Build queryset
        queryset = MarketData.objects.filter(ticker=ticker, timeframe=interval)
        
        if start_date and end_date:
            queryset = queryset.filter(timestamp__range=[start_date, end_date])
        elif period:
            # Convert period to date range
            period_map = {
                '1d': 1, '5d': 5, '1mo': 30, '3mo': 90, '6mo': 180,
                '1y': 365, '2y': 730, '5y': 1825, '10y': 3650
            }
            days = period_map.get(period, 365)
            start_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(timestamp__gte=start_date)
        
        data = queryset.order_by('timestamp')
        
        # Format response based on request
        if format_type == 'pandas':
            # Return pandas-compatible format
            records = []
            for item in data:
                records.append({
                    'Date': item.timestamp.date().isoformat(),
                    'Open': float(item.open),
                    'High': float(item.high),
                    'Low': float(item.low),
                    'Close': float(item.close),
                    'Volume': float(item.volume)
                })
            
            return Response({
                'data': records,
                'columns': ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'],
                'index': list(range(len(records))),
                'pandas_version': '2.0.0'
            })
        
        elif format_type == 'csv':
            # Return CSV data
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
            
            for item in data:
                writer.writerow([
                    item.timestamp.date(),
                    float(item.open),
                    float(item.high),
                    float(item.low),
                    float(item.close),
                    float(item.volume)
                ])
            
            response = Response(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{symbol}_{period}.csv"'
            return response
        
        # Default JSON format
        serializer = self.get_serializer(data, many=True)
        return Response({
            'symbol': symbol,
            'period': period,
            'interval': interval,
            'total_records': data.count(),
            'data': serializer.data
        })
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """High-performance bulk market data creation"""
        serializer = MarketDataBulkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data_records = serializer.validated_data['data']
        
        # Batch create for performance
        market_data_objects = []
        for record in data_records:
            try:
                ticker = Ticker.objects.get(id=record['ticker_id'])
                market_data_objects.append(MarketData(
                    ticker=ticker,
                    timestamp=record['timestamp'],
                    timeframe=record['timeframe'],
                    open=record['open'],
                    high=record['high'],
                    low=record['low'],
                    close=record['close'],
                    volume=record['volume'],
                    adjusted_close=record.get('adjusted_close'),
                    data_source_id=1  # Default to first data source
                ))
            except Ticker.DoesNotExist:
                continue
        
        created_objects = MarketData.objects.bulk_create(
            market_data_objects,
            batch_size=1000,
            ignore_conflicts=True
        )
        
        return Response({
            'created': len(created_objects),
            'total_requested': len(data_records)
        })
    
    @action(detail=False, methods=['get'])
    def quotes(self, request):
        """Get real-time quotes for multiple symbols"""
        symbols_param = request.query_params.get('symbols', '')
        if not symbols_param:
            return Response({'error': 'symbols parameter required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        symbols = [s.strip() for s in symbols_param.split(',')]
        
        yfinance_service = YFinanceService()
        quotes = []
        
        for symbol in symbols:
            quote_data = yfinance_service.get_real_time_quote(symbol)
            if quote_data:
                quotes.append(quote_data)
        
        return Response({
            'quotes': quotes,
            'timestamp': timezone.now(),
            'count': len(quotes)
        })


class DataIntegrationViewSet(viewsets.ViewSet):
    """Data integration endpoints for external sources"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='yfinance/fetch')
    def yfinance_fetch(self, request):
        """Fetch data from yfinance"""
        serializer = DataIngestionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        ingestion_service = DataIngestionService()
        log = ingestion_service.ingest_market_data(
            symbols=serializer.validated_data['symbols'],
            data_source='yfinance',
            period=serializer.validated_data['period'],
            interval=serializer.validated_data['interval']
        )
        
        log_serializer = DataIngestionLogSerializer(log)
        return Response(log_serializer.data)
    
    @action(detail=False, methods=['post'], url_path='alphavantage/fetch')
    def alphavantage_fetch(self, request):
        """Fetch data from Alpha Vantage"""
        serializer = DataIngestionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        ingestion_service = DataIngestionService()
        log = ingestion_service.ingest_market_data(
            symbols=serializer.validated_data['symbols'],
            data_source='alpha_vantage',
            period=serializer.validated_data['period'],
            interval=serializer.validated_data['interval']
        )
        
        log_serializer = DataIngestionLogSerializer(log)
        return Response(log_serializer.data)
    
    @action(detail=False, methods=['get'], url_path='yfinance/search')
    def yfinance_search(self, request):
        """Search tickers using yfinance"""
        query = request.query_params.get('query', '')
        country = request.query_params.get('country')
        
        if not query:
            return Response({'error': 'query parameter required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        yfinance_service = YFinanceService()
        results = yfinance_service.search_ticker(query, country)
        
        return Response({
            'query': query,
            'results': results
        })


class TechnicalAnalysisViewSet(viewsets.ViewSet):
    """Technical analysis endpoints"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'], url_path='indicators/(?P<symbol>[^/.]+)')
    def technical_indicators(self, request, symbol=None):
        """Calculate technical indicators for a symbol"""
        try:
            ticker = Ticker.objects.get(symbol=symbol)
        except Ticker.DoesNotExist:
            return Response({'error': f'Ticker {symbol} not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        indicators_param = request.query_params.get('indicators', 'rsi,macd,sma_20')
        indicators = [i.strip() for i in indicators_param.split(',')]
        timeframe = request.query_params.get('timeframe', '1d')
        period = int(request.query_params.get('period', 14))
        
        # Get recent market data
        market_data = MarketData.objects.filter(
            ticker=ticker,
            timeframe=timeframe
        ).order_by('-timestamp')[:200]  # Get enough data for calculations
        
        if not market_data:
            return Response({'error': 'No market data available'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Convert to pandas DataFrame for calculations
        df = pd.DataFrame([
            {
                'timestamp': item.timestamp,
                'open': float(item.open),
                'high': float(item.high),
                'low': float(item.low),
                'close': float(item.close),
                'volume': float(item.volume)
            }
            for item in reversed(market_data)
        ])
        
        results = {}
        
        # Calculate requested indicators
        for indicator in indicators:
            if indicator == 'rsi':
                results['rsi'] = self._calculate_rsi(df, period)
            elif indicator == 'macd':
                results['macd'] = self._calculate_macd(df)
            elif indicator.startswith('sma_'):
                period_sma = int(indicator.split('_')[1])
                results[indicator] = self._calculate_sma(df, period_sma)
            elif indicator.startswith('ema_'):
                period_ema = int(indicator.split('_')[1])
                results[indicator] = self._calculate_ema(df, period_ema)
            elif indicator == 'bollinger_bands':
                results['bollinger_bands'] = self._calculate_bollinger_bands(df, period)
        
        return Response({
            'symbol': symbol,
            'timeframe': timeframe,
            'indicators': results,
            'timestamp': timezone.now()
        })
    
    def _calculate_rsi(self, df, period=14):
        """Calculate RSI"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
        
        return {
            'current_value': float(current_rsi) if current_rsi else None,
            'signal': 'overbought' if current_rsi and current_rsi > 70 else 'oversold' if current_rsi and current_rsi < 30 else 'neutral',
            'period': period,
            'history': [
                {'date': df.iloc[i]['timestamp'].date().isoformat(), 'value': float(rsi.iloc[i])}
                for i in range(len(rsi)) if not pd.isna(rsi.iloc[i])
            ][-20:]  # Last 20 values
        }
    
    def _calculate_macd(self, df, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd_line': float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None,
            'signal_line': float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else None,
            'histogram': float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else None,
            'signal': 'bullish' if histogram.iloc[-1] > 0 else 'bearish',
        }
    
    def _calculate_sma(self, df, period):
        """Calculate Simple Moving Average"""
        sma = df['close'].rolling(window=period).mean()
        current_price = df['close'].iloc[-1]
        current_sma = sma.iloc[-1]
        
        return {
            'current_value': float(current_sma) if not pd.isna(current_sma) else None,
            'period': period,
            'price_above_sma': float(current_price) > float(current_sma) if not pd.isna(current_sma) else None,
        }
    
    def _calculate_ema(self, df, period):
        """Calculate Exponential Moving Average"""
        ema = df['close'].ewm(span=period).mean()
        current_price = df['close'].iloc[-1]
        current_ema = ema.iloc[-1]
        
        return {
            'current_value': float(current_ema) if not pd.isna(current_ema) else None,
            'period': period,
            'price_above_ema': float(current_price) > float(current_ema) if not pd.isna(current_ema) else None,
        }
    
    def _calculate_bollinger_bands(self, df, period=20, std_dev=2):
        """Calculate Bollinger Bands"""
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        current_price = df['close'].iloc[-1]
        
        return {
            'upper_band': float(upper_band.iloc[-1]) if not pd.isna(upper_band.iloc[-1]) else None,
            'middle_band': float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else None,
            'lower_band': float(lower_band.iloc[-1]) if not pd.isna(lower_band.iloc[-1]) else None,
            'current_price': float(current_price),
            'position': 'above_upper' if current_price > upper_band.iloc[-1] else 'below_lower' if current_price < lower_band.iloc[-1] else 'within_bands'
        }


class AnalyticsViewSet(viewsets.ViewSet):
    """Advanced analytics endpoints"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='correlation-matrix')
    def correlation_matrix(self, request):
        """Calculate correlation matrix for multiple symbols"""
        serializer = CorrelationMatrixRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        symbols = serializer.validated_data['symbols']
        period = serializer.validated_data['period']
        method = serializer.validated_data['method']
        
        # Get market data for all symbols
        tickers = Ticker.objects.filter(symbol__in=symbols)
        if tickers.count() != len(symbols):
            missing = set(symbols) - set(tickers.values_list('symbol', flat=True))
            return Response({'error': f'Tickers not found: {missing}'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Calculate date range
        period_map = {'1mo': 30, '3mo': 90, '6mo': 180, '1y': 365, '2y': 730}
        days = period_map.get(period, 365)
        start_date = timezone.now() - timedelta(days=days)
        
        # Build price matrix
        price_data = {}
        for ticker in tickers:
            prices = MarketData.objects.filter(
                ticker=ticker,
                timestamp__gte=start_date,
                timeframe='1d'
            ).order_by('timestamp').values_list('timestamp', 'close')
            
            price_data[ticker.symbol] = {
                timestamp.date(): float(close) for timestamp, close in prices
            }
        
        # Create aligned DataFrame
        all_dates = set()
        for symbol_prices in price_data.values():
            all_dates.update(symbol_prices.keys())
        
        all_dates = sorted(all_dates)
        
        df_data = {}
        for symbol in symbols:
            df_data[symbol] = [
                price_data[symbol].get(date) for date in all_dates
            ]
        
        df = pd.DataFrame(df_data, index=all_dates)
        df = df.dropna()  # Remove rows with missing data
        
        # Calculate correlation matrix
        if method == 'pearson':
            corr_matrix = df.corr()
        else:  # spearman
            corr_matrix = df.corr(method='spearman')
        
        # Convert to dictionary format
        correlation_dict = {}
        for symbol1 in symbols:
            correlation_dict[symbol1] = {}
            for symbol2 in symbols:
                correlation_dict[symbol1][symbol2] = float(corr_matrix.loc[symbol1, symbol2])
        
        return Response({
            'correlation_matrix': correlation_dict,
            'method': method,
            'period': period,
            'data_points': len(df),
            'date_range': {
                'start': df.index[0].isoformat(),
                'end': df.index[-1].isoformat()
            }
        })


class ScreeningViewSet(viewsets.ViewSet):
    """Stock screening endpoints"""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='technical')
    def technical_screening(self, request):
        """Screen stocks based on technical criteria"""
        serializer = StockScreeningRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        criteria = serializer.validated_data['criteria']
        universe = serializer.validated_data.get('universe', 'ALL')
        limit = serializer.validated_data.get('limit', 50)
        
        # Start with base queryset
        if universe == 'SP500':
            # Would filter for S&P 500 stocks
            base_query = Ticker.objects.filter(is_active=True)
        else:
            base_query = Ticker.objects.filter(is_active=True)
        
        # Apply market cap filters
        market_cap_min = serializer.validated_data.get('market_cap_min')
        market_cap_max = serializer.validated_data.get('market_cap_max')
        
        if market_cap_min:
            base_query = base_query.filter(market_cap__gte=market_cap_min)
        if market_cap_max:
            base_query = base_query.filter(market_cap__lte=market_cap_max)
        
        # Apply sector filter
        sectors = serializer.validated_data.get('sector')
        if sectors:
            base_query = base_query.filter(sector__name__in=sectors)
        
        results = []
        
        # Process each ticker
        for ticker in base_query[:500]:  # Limit initial set for performance
            try:
                # Get recent market data
                recent_data = MarketData.objects.filter(
                    ticker=ticker,
                    timeframe='1d'
                ).order_by('-timestamp')[:50]
                
                if len(recent_data) < 20:  # Need minimum data
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame([
                    {
                        'close': float(item.close),
                        'volume': float(item.volume),
                        'high': float(item.high),
                        'low': float(item.low)
                    }
                    for item in reversed(recent_data)
                ])
                
                # Check each criterion
                passes_all = True
                criterion_scores = {}
                
                for criterion in criteria:
                    indicator = criterion['indicator']
                    operator = criterion['operator']
                    value = criterion['value']
                    period = criterion.get('period', 14)
                    
                    # Calculate indicator value
                    if indicator == 'rsi':
                        delta = df['close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                        rs = gain / loss
                        rsi = 100 - (100 / (1 + rs))
                        current_value = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
                    
                    elif indicator == 'price_vs_sma':
                        sma = df['close'].rolling(window=period).mean()
                        current_value = df['close'].iloc[-1] / sma.iloc[-1] if not pd.isna(sma.iloc[-1]) else None
                    
                    elif indicator == 'volume_ratio':
                        volume_avg = df['volume'].rolling(window=period).mean()
                        current_value = df['volume'].iloc[-1] / volume_avg.iloc[-1] if not pd.isna(volume_avg.iloc[-1]) else None
                    
                    else:
                        current_value = None
                    
                    if current_value is None:
                        passes_all = False
                        break
                    
                    # Apply operator
                    if operator == '>':
                        passes = current_value > value
                    elif operator == '<':
                        passes = current_value < value
                    elif operator == '>=':
                        passes = current_value >= value
                    elif operator == '<=':
                        passes = current_value <= value
                    elif operator == '==':
                        passes = abs(current_value - value) < 0.01
                    elif operator == '!=':
                        passes = abs(current_value - value) >= 0.01
                    else:
                        passes = False
                    
                    criterion_scores[indicator] = current_value
                    
                    if not passes:
                        passes_all = False
                        break
                
                if passes_all:
                    results.append({
                        'symbol': ticker.symbol,
                        'name': ticker.name,
                        'exchange': ticker.exchange.code,
                        'sector': ticker.sector.name if ticker.sector else None,
                        'market_cap': float(ticker.market_cap) if ticker.market_cap else None,
                        'criteria_scores': criterion_scores,
                        'current_price': float(recent_data[0].close)
                    })
                
                if len(results) >= limit:
                    break
                    
            except Exception as e:
                continue
        
        return Response({
            'total_matches': len(results),
            'criteria_count': len(criteria),
            'universe': universe,
            'results': results
        })


class PortfolioViewSet(viewsets.ModelViewSet):
    """Portfolio management"""
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get portfolio analytics"""
        portfolio = self.get_object()
        
        # This would implement comprehensive portfolio analytics
        # For now, return basic structure
        return Response({
            'portfolio_id': portfolio.id,
            'total_value': 0.0,  # Would calculate actual value
            'performance_metrics': {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0
            },
            'positions_count': portfolio.positions.count()
        })


# Custom filter classes would be defined here
class TickerFilter:
    pass

class MarketDataFilter:
    pass
