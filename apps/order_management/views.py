# apps/order_management/views.py
"""
SIMULATED Order Management API Views
===================================
RESTful endpoints for VIRTUAL order management and trading.
All endpoints handle PAPER TRADING - no real money involved.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Sum, Count
from decimal import Decimal

from .models import (
    SimulatedOrder, SimulatedTrade, OrderBook, OrderBookLevel, 
    Fill, MatchingEngine, OrderStatus
)
from .serializers import (
    SimulatedOrderSerializer, OrderCreateSerializer, SimulatedTradeSerializer,
    OrderBookSerializer, FillSerializer, BulkOrderCreateSerializer,
    OrderBookSnapshotRequestSerializer
)
from .services import OrderMatchingService, OrderBookService
from apps.trading_simulation.models import SimulatedInstrument, SimulatedExchange


class SimulatedOrderViewSet(viewsets.ModelViewSet):
    """
    SIMULATED Order Management
    Create, manage, and track virtual trading orders
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'side', 'order_type', 'instrument', 'exchange']
    ordering = ['-order_timestamp']
    
    def get_queryset(self):
        # Users can only see their own orders
        return SimulatedOrder.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return SimulatedOrderSerializer
    
    def create(self, request, *args, **kwargs):
        """Create and submit a new simulated order"""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Get related objects
            instrument = SimulatedInstrument.objects.get(
                id=serializer.validated_data['instrument_id']
            )
            exchange = SimulatedExchange.objects.get(
                id=serializer.validated_data['exchange_id']
            )
            
            # Create order object
            order = SimulatedOrder.objects.create(
                user=request.user,
                instrument=instrument,
                exchange=exchange,
                side=serializer.validated_data['side'],
                order_type=serializer.validated_data['order_type'],
                quantity=serializer.validated_data['quantity'],
                price=serializer.validated_data.get('price'),
                stop_price=serializer.validated_data.get('stop_price'),
                time_in_force=serializer.validated_data.get('time_in_force', 'GTC'),
                display_quantity=serializer.validated_data.get('display_quantity'),
                minimum_quantity=serializer.validated_data.get('minimum_quantity'),
                client_order_id=serializer.validated_data.get('client_order_id', '')
            )
            
            # Submit order through matching engine
            matching_service = OrderMatchingService()
            success, message, violations = matching_service.submit_order(order)
            
            # Return response
            response_serializer = SimulatedOrderSerializer(order)
            
            if success:
                return Response({
                    'order': response_serializer.data,
                    'message': message,
                    'status': 'SUBMITTED'
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'order': response_serializer.data,
                    'message': message,
                    'violations': violations,
                    'status': 'REJECTED'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except SimulatedInstrument.DoesNotExist:
            return Response(
                {'error': 'Instrument not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except SimulatedExchange.DoesNotExist:
            return Response(
                {'error': 'Exchange not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending order"""
        try:
            order = self.get_object()
            
            if order.status not in [OrderStatus.PENDING, OrderStatus.SUBMITTED, 
                                  OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED]:
                return Response(
                    {'error': f'Cannot cancel order in status: {order.status}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            matching_service = OrderMatchingService()
            success = matching_service.cancel_order(
                order, 
                reason=request.data.get('reason', 'User cancellation')
            )
            
            if success:
                serializer = self.get_serializer(order)
                return Response({
                    'order': serializer.data,
                    'message': 'Order cancelled successfully'
                })
            else:
                return Response(
                    {'error': 'Failed to cancel order'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def fills(self, request, pk=None):
        """Get all fills for an order"""
        try:
            order = self.get_object()
            fills = order.fills.all().order_by('-fill_timestamp')
            serializer = FillSerializer(fills, many=True)
            
            return Response({
                'order_id': order.order_id,
                'total_fills': fills.count(),
                'fills': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple orders at once"""
        try:
            serializer = BulkOrderCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            created_orders = []
            rejected_orders = []
            
            for order_data in serializer.validated_data['orders']:
                try:
                    # Get related objects
                    instrument = SimulatedInstrument.objects.get(
                        id=order_data['instrument_id']
                    )
                    exchange = SimulatedExchange.objects.get(
                        id=order_data['exchange_id']
                    )
                    
                    # Create order
                    order = SimulatedOrder.objects.create(
                        user=request.user,
                        instrument=instrument,
                        exchange=exchange,
                        side=order_data['side'],
                        order_type=order_data['order_type'],
                        quantity=order_data['quantity'],
                        price=order_data.get('price'),
                        stop_price=order_data.get('stop_price'),
                        time_in_force=order_data.get('time_in_force', 'GTC'),
                        client_order_id=order_data.get('client_order_id', '')
                    )
                    
                    # Submit order
                    matching_service = OrderMatchingService()
                    success, message, violations = matching_service.submit_order(order)
                    
                    if success:
                        created_orders.append({
                            'order_id': str(order.order_id),
                            'status': order.status,
                            'message': message
                        })
                    else:
                        rejected_orders.append({
                            'order_id': str(order.order_id),
                            'message': message,
                            'violations': violations
                        })
                        
                except Exception as e:
                    rejected_orders.append({
                        'error': str(e),
                        'order_data': order_data
                    })
            
            return Response({
                'created_orders': created_orders,
                'rejected_orders': rejected_orders,
                'total_created': len(created_orders),
                'total_rejected': len(rejected_orders)
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get user's orders with filtering and statistics"""
        try:
            orders = self.get_queryset()
            
            # Apply additional filters
            status_filter = request.query_params.get('status')
            if status_filter:
                orders = orders.filter(status=status_filter)
            
            instrument_symbol = request.query_params.get('instrument')
            if instrument_symbol:
                orders = orders.filter(instrument__real_ticker__symbol=instrument_symbol)
            
            # Pagination
            page = self.paginate_queryset(orders)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                
                # Add statistics
                stats = self._calculate_order_statistics(orders)
                
                response = self.get_paginated_response(serializer.data)
                response.data['statistics'] = stats
                return response
            
            serializer = self.get_serializer(orders, many=True)
            stats = self._calculate_order_statistics(orders)
            
            return Response({
                'orders': serializer.data,
                'statistics': stats
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_order_statistics(self, orders):
        """Calculate order statistics"""
        try:
            total_orders = orders.count()
            if total_orders == 0:
                return {}
            
            stats = orders.aggregate(
                filled_orders=Count('id', filter=Q(status='FILLED')),
                partially_filled=Count('id', filter=Q(status='PARTIALLY_FILLED')),
                cancelled_orders=Count('id', filter=Q(status='CANCELLED')),
                rejected_orders=Count('id', filter=Q(status='REJECTED')),
                total_quantity=Sum('quantity'),
                total_filled_quantity=Sum('filled_quantity'),
                total_fees=Sum('total_fees')
            )
            
            # Calculate percentages
            stats['fill_rate'] = (stats['filled_orders'] / total_orders * 100) if total_orders > 0 else 0
            stats['rejection_rate'] = (stats['rejected_orders'] / total_orders * 100) if total_orders > 0 else 0
            stats['average_fill_ratio'] = (stats['total_filled_quantity'] / stats['total_quantity'] * 100) if stats['total_quantity'] > 0 else 0
            
            return stats
            
        except Exception:
            return {}


class SimulatedTradeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    SIMULATED Trade History
    View historical virtual trades
    """
    serializer_class = SimulatedTradeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['instrument', 'exchange']
    ordering = ['-trade_timestamp']
    
    def get_queryset(self):
        # Users can see trades involving their orders
        return SimulatedTrade.objects.filter(
            Q(buy_order__user=self.request.user) | 
            Q(sell_order__user=self.request.user)
        )
    
    @action(detail=False, methods=['get'])
    def my_trades(self, request):
        """Get user's trades with statistics"""
        try:
            trades = self.get_queryset()
            
            # Apply filters
            instrument_symbol = request.query_params.get('instrument')
            if instrument_symbol:
                trades = trades.filter(instrument__real_ticker__symbol=instrument_symbol)
            
            start_date = request.query_params.get('start_date')
            if start_date:
                trades = trades.filter(trade_timestamp__date__gte=start_date)
            
            end_date = request.query_params.get('end_date')
            if end_date:
                trades = trades.filter(trade_timestamp__date__lte=end_date)
            
            # Pagination
            page = self.paginate_queryset(trades)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                
                # Add statistics
                stats = self._calculate_trade_statistics(trades, request.user)
                
                response = self.get_paginated_response(serializer.data)
                response.data['statistics'] = stats
                return response
            
            serializer = self.get_serializer(trades, many=True)
            stats = self._calculate_trade_statistics(trades, request.user)
            
            return Response({
                'trades': serializer.data,
                'statistics': stats
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _calculate_trade_statistics(self, trades, user):
        """Calculate trade statistics for user"""
        try:
            user_trades = trades.filter(
                Q(buy_order__user=user) | Q(sell_order__user=user)
            )
            
            if not user_trades.exists():
                return {}
            
            # Basic statistics
            total_trades = user_trades.count()
            total_volume = user_trades.aggregate(Sum('quantity'))['quantity__sum'] or 0
            total_value = user_trades.aggregate(Sum('notional_value'))['notional_value__sum'] or 0
            
            # Calculate average trade size and value
            avg_trade_size = total_volume / total_trades if total_trades > 0 else 0
            avg_trade_value = total_value / total_trades if total_trades > 0 else 0
            
            # Trading activity by time
            today_trades = user_trades.filter(trade_timestamp__date=timezone.now().date()).count()
            
            return {
                'total_trades': total_trades,
                'total_volume': total_volume,
                'total_value': float(total_value),
                'average_trade_size': avg_trade_size,
                'average_trade_value': float(avg_trade_value),
                'trades_today': today_trades
            }
            
        except Exception:
            return {}


class OrderBookViewSet(viewsets.ReadOnlyModelViewSet):
    """
    SIMULATED Order Book Data
    View virtual order book information
    """
    queryset = OrderBook.objects.all()
    serializer_class = OrderBookSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['instrument__exchange']
    
    @action(detail=False, methods=['post'])
    def snapshot(self, request):
        """Get order book snapshot for specific instrument"""
        try:
            serializer = OrderBookSnapshotRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            instrument = SimulatedInstrument.objects.get(
                id=serializer.validated_data['instrument_id']
            )
            
            service = OrderBookService()
            snapshot = service.get_order_book_snapshot(instrument)
            
            return Response(snapshot)
            
        except SimulatedInstrument.DoesNotExist:
            return Response(
                {'error': 'Instrument not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def levels(self, request, pk=None):
        """Get detailed order book levels"""
        try:
            order_book = self.get_object()
            depth = int(request.query_params.get('depth', 5))
            
            # Get bid levels (descending price order)
            bid_levels = OrderBookLevel.objects.filter(
                order_book=order_book,
                side='BUY'
            ).order_by('-price')[:depth]
            
            # Get ask levels (ascending price order) 
            ask_levels = OrderBookLevel.objects.filter(
                order_book=order_book,
                side='SELL'
            ).order_by('price')[:depth]
            
            bid_data = []
            for level in bid_levels:
                bid_data.append({
                    'price': float(level.price),
                    'quantity': level.quantity,
                    'order_count': level.order_count
                })
            
            ask_data = []
            for level in ask_levels:
                ask_data.append({
                    'price': float(level.price),
                    'quantity': level.quantity,
                    'order_count': level.order_count
                })
            
            return Response({
                'instrument': order_book.instrument.real_ticker.symbol,
                'timestamp': timezone.now(),
                'bids': bid_data,
                'asks': ask_data,
                'depth': depth
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def market_summary(self, request):
        """Get market summary across all instruments"""
        try:
            exchange_id = request.query_params.get('exchange_id')
            
            order_books = self.get_queryset()
            if exchange_id:
                order_books = order_books.filter(instrument__exchange_id=exchange_id)
            
            summary = []
            
            for order_book in order_books:
                instrument_data = {
                    'symbol': order_book.instrument.real_ticker.symbol,
                    'exchange': order_book.instrument.exchange.code,
                    'last_price': float(order_book.last_trade_price) if order_book.last_trade_price else None,
                    'bid': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                    'ask': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                    'daily_volume': order_book.daily_volume,
                    'daily_high': float(order_book.daily_high) if order_book.daily_high else None,
                    'daily_low': float(order_book.daily_low) if order_book.daily_low else None,
                    'spread_bps': order_book.spread_bps,
                    'trade_count': order_book.trade_count
                }
                
                # Calculate daily change
                if order_book.last_trade_price and order_book.opening_price:
                    change = order_book.last_trade_price - order_book.opening_price
                    change_pct = (change / order_book.opening_price) * 100
                    instrument_data['daily_change'] = float(change)
                    instrument_data['daily_change_percent'] = float(change_pct)
                else:
                    instrument_data['daily_change'] = 0.0
                    instrument_data['daily_change_percent'] = 0.0
                
                summary.append(instrument_data)
            
            return Response({
                'market_summary': summary,
                'total_instruments': len(summary),
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TradingEngineViewSet(viewsets.ViewSet):
    """
    SIMULATED Trading Engine Control
    Control and monitor the virtual trading engine
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        """Get trading engine status"""
        try:
            # Get engine statistics across all exchanges
            engines = MatchingEngine.objects.all()
            
            engine_stats = []
            for engine in engines:
                stats = {
                    'exchange': engine.exchange.code,
                    'algorithm': engine.matching_algorithm,
                    'is_active': engine.is_active,
                    'orders_processed': engine.orders_processed,
                    'trades_executed': engine.trades_executed,
                    'average_latency_ms': float(engine.average_latency_ms),
                    'last_match_timestamp': engine.last_match_timestamp
                }
                engine_stats.append(stats)
            
            return Response({
                'engines': engine_stats,
                'total_engines': len(engine_stats),
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def process_pending_orders(self, request):
        """Manually trigger processing of pending orders"""
        try:
            exchange_id = request.data.get('exchange_id')
            
            if exchange_id:
                exchanges = [SimulatedExchange.objects.get(id=exchange_id)]
            else:
                exchanges = SimulatedExchange.objects.filter(status='ACTIVE')
            
            processed_count = 0
            matching_service = OrderMatchingService()
            
            for exchange in exchanges:
                # Get pending orders for this exchange
                pending_orders = SimulatedOrder.objects.filter(
                    exchange=exchange,
                    status__in=[OrderStatus.PENDING, OrderStatus.ACKNOWLEDGED]
                )
                
                for order in pending_orders:
                    # Attempt to match order
                    matches = matching_service._match_order(order)
                    if matches:
                        processed_count += 1
            
            return Response({
                'message': f'Processed {processed_count} pending orders',
                'timestamp': timezone.now()
            })
            
        except SimulatedExchange.DoesNotExist:
            return Response(
                {'error': 'Exchange not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def daily_statistics(self, request):
        """Get daily trading statistics"""
        try:
            today = timezone.now().date()
            
            # Order statistics
            orders_today = SimulatedOrder.objects.filter(
                order_timestamp__date=today
            )
            
            order_stats = orders_today.aggregate(
                total_orders=Count('id'),
                filled_orders=Count('id', filter=Q(status='FILLED')),
                cancelled_orders=Count('id', filter=Q(status='CANCELLED')),
                rejected_orders=Count('id', filter=Q(status='REJECTED')),
                total_volume=Sum('quantity'),
                filled_volume=Sum('filled_quantity')
            )
            
            # Trade statistics
            trades_today = SimulatedTrade.objects.filter(
                trade_timestamp__date=today
            )
            
            trade_stats = trades_today.aggregate(
                total_trades=Count('id'),
                total_volume=Sum('quantity'),
                total_value=Sum('notional_value')
            )
            
            # Active users
            active_users = SimulatedOrder.objects.filter(
                order_timestamp__date=today
            ).values('user').distinct().count()
            
            return Response({
                'date': today,
                'order_statistics': order_stats,
                'trade_statistics': trade_stats,
                'active_users': active_users,
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
