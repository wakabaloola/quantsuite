# apps/trading_simulation/consumers.py
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Set
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import SimulatedInstrument, UserSimulationProfile
from apps.core.events import event_bus
from apps.core.websockets.monitoring import WebSocketMonitoringConsumer
from apps.core.websockets.middleware import ConnectionTrackingMixin
from apps.core.websockets.permissions import (
    WebSocketPermissionMixin,
    IsAuthenticated,
    IsOwnerOrReadOnly,
    HasTradingPermission,
    CanAccessMarketData,
    CanControlAlgorithms
)
from apps.market_data.analysis import enhanced_ta_service
from apps.market_data.streaming import streaming_engine
from apps.order_management.models import SimulatedOrder
from apps.risk_management.models import SimulatedPosition
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class OrderUpdatesConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), IsOwnerOrReadOnly()]   # Adjust permissions as necessary

    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.user_group_name = f'orders_{self.user_id}'
        
        # Use enhanced connect with permission and connection tracking
        await super().connect()

        # Join user-specific group with tracking
        await self.join_tracked_group(self.user_group_name)
        
        # Send initial order status
        await self.send_initial_orders()
    
    async def disconnect(self, close_code):
        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code) 

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_orders':
            await self.send_initial_orders()
        elif message_type == 'heartbeat':
            await self.send_tracked_message({
                'type': 'heartbeat_response',
                'timestamp': timezone.now().isoformat()
            })
    
    async def send_initial_orders(self):
        orders = await self.get_user_orders()
        await self.send_tracked_message({
            'type': 'initial_orders',
            'orders': orders
        })
    
    async def order_update(self, event):
        await self.send_tracked_message({
            'type': 'order_update',
            'order': event['order']
        })
    
    async def order_filled(self, event):
        await self.send_tracked_message({
            'type': 'order_filled',
            'order': event['order'],
            'fill_details': event['fill_details']
        })

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event']
        })
    
    @database_sync_to_async
    def get_user_orders(self):
        try:
            user = User.objects.get(id=self.user_id)
            orders = user.simulated_orders.filter(
                status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
            ).order_by('-order_timestamp')[:50]
            
            return [{
                'order_id': str(order.order_id),
                'symbol': order.instrument.real_ticker.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'price': float(order.price) if order.price else None,
                'status': order.status,
                'filled_quantity': order.filled_quantity,
                'timestamp': order.order_timestamp.isoformat()
            } for order in orders]
        except Exception as e:
            return []

class PortfolioUpdatesConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), IsOwnerOrReadOnly()]

    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.user_group_name = f'portfolio_{self.user_id}'
        
        # Use enhanced connect with permission and connection tracking
        await super().connect()

        # Join user-specific group with tracking
        await self.join_tracked_group(self.user_group_name)

        await self.send_initial_portfolio()
    
    async def disconnect(self, close_code):
        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_portfolio':
            await self.send_initial_portfolio()
    
    async def send_initial_portfolio(self):
        portfolio = await self.get_user_portfolio()
        await self.send_tracked_message({
            'type': 'initial_portfolio',
            'portfolio': portfolio
        })
    
    async def portfolio_update(self, event):
        await self.send_tracked_message({
            'type': 'portfolio_update',
            'portfolio': event['portfolio']
        })
    
    async def position_update(self, event):
        await self.send_tracked_message({
            'type': 'position_update',
            'position': event['position']
        })

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event']
        })
    
    @database_sync_to_async
    def get_user_portfolio(self):
        try:
            user = User.objects.get(id=self.user_id)
            profile = user.simulation_profile
            positions = user.simulated_positions.all()
            
            return {
                'cash_balance': float(profile.virtual_cash_balance),
                'portfolio_value': float(profile.current_portfolio_value),
                'total_return': profile.calculate_total_return_percentage(),
                'positions': [{
                    'symbol': pos.instrument.real_ticker.symbol,
                    'quantity': float(pos.quantity),
                    'current_price': float(pos.current_price) if pos.current_price else None,
                    'market_value': float(pos.market_value),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'daily_pnl': float(pos.daily_pnl)
                } for pos in positions]
            }
        except Exception as e:
            return {'error': str(e)}

class MarketDataConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), CanAccessMarketData()]

    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs']['symbol']
        self.market_group_name = f'market_{self.symbol}'
        
        await super().connect()
        await self.join_tracked_group(self.market_group_name)
        await self.send_initial_market_data()
    
    async def disconnect(self, close_code):
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_market':
            await self.send_initial_market_data()
    
    async def send_initial_market_data(self):
        market_data = await self.get_market_data()
        await self.send_tracked_message({
            'type': 'initial_market_data',
            'data': market_data
        })
    
    async def price_update(self, event):
        await self.send_tracked_message({
            'type': 'price_update',
            'data': event['data']
        })
    
    async def orderbook_update(self, event):
        await self.send_tracked_message({
            'type': 'orderbook_update',
            'data': event['data']
        })
    
    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event']
        })

    @database_sync_to_async
    def get_market_data(self):
        try:
            instrument = SimulatedInstrument.objects.get(
                real_ticker__symbol=self.symbol
            )
            order_book = instrument.order_book
            
            return {
                'symbol': self.symbol,
                'last_price': float(order_book.last_trade_price) if order_book.last_trade_price else None,
                'bid_price': float(order_book.best_bid_price) if order_book.best_bid_price else None,
                'ask_price': float(order_book.best_ask_price) if order_book.best_ask_price else None,
                'volume': order_book.daily_volume,
                'timestamp': timezone.now().isoformat()
            }
        except Exception as e:
            return {'error': str(e)}

class RiskAlertsConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), IsOwnerOrReadOnly()]

    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.risk_group_name = f'risk_{self.user_id}'
        
        # Use enhanced connect with permission and connection tracking
        await super().connect()
        
        # Join user-specific group with tracking
        await self.join_tracked_group(self.risk_group_name)
    
    async def disconnect(self, close_code):
        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code)
    
    async def risk_alert(self, event):
        await self.send_tracked_message({
            'type': 'risk_alert',
            'alert': event['alert']
        })
    
    async def compliance_alert(self, event):
        await self.send_tracked_message({
            'type': 'compliance_alert',
            'alert': event['alert']
        })

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event']
        })


class RealTimeMarketDataConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), CanAccessMarketData()]
    """Real-time market data streaming consumer"""
    
    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs'].get('symbol', 'ALL').upper()
        
        if self.symbol == 'ALL':
            self.group_name = 'market_data_global'
        else:
            self.group_name = f'market_{self.symbol}'
        
        # Join market data group
        # Use enhanced connect with permission and connection tracking
        await super().connect()
        
        # Join user-specific group with tracking
        await self.join_tracked_group(self.group_name)
        
        # Subscribe to symbol if specific
        if self.symbol != 'ALL':
            streaming_engine.subscribe_symbol(self.symbol, high_frequency=True)
        
        # Send initial data
        await self.send_initial_data()
    
    async def disconnect(self, close_code):
        # Unsubscribe from symbol
        if self.symbol != 'ALL':
            streaming_engine.unsubscribe_symbol(self.symbol)
        
        # Leave group
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe':
            symbol = data.get('symbol', '').upper()
            if symbol:
                streaming_engine.subscribe_symbol(symbol, high_frequency=True)
                await self.send_tracked_message({
                    'type': 'subscription_confirmed',
                    'symbol': symbol
                })
        
        elif message_type == 'unsubscribe':
            symbol = data.get('symbol', '').upper()
            if symbol:
                streaming_engine.unsubscribe_symbol(symbol)
                await self.send_tracked_message({
                    'type': 'unsubscription_confirmed',
                    'symbol': symbol
                })
        
        elif message_type == 'get_metrics':
            metrics = streaming_engine.get_metrics()
            await self.send_tracked_message({
                'type': 'metrics',
                'data': metrics
            })
    
    async def send_initial_data(self):
        """Send initial market data state"""
        if self.symbol != 'ALL':
            # Send current quote if available
            quote = await streaming_engine.get_current_quote(self.symbol)
            if quote:
                await self.send_tracked_message({
                    'type': 'initial_quote',
                    'data': {
                        'symbol': quote.symbol,
                        'price': float(quote.price),
                        'volume': quote.volume,
                        'timestamp': quote.timestamp.isoformat()
                    }
                })
        
        # Send streaming status
        metrics = streaming_engine.get_metrics()
        await self.send_tracked_message({
            'type': 'streaming_status',
            'status': metrics['status'],
            'active_symbols': metrics['active_symbols'],
            'data_quality': metrics['performance']['data_quality']
        })
    
    async def price_update(self, event):
        """Handle price update from streaming engine"""
        await self.send_tracked_message({
            'type': 'price_update',
            'data': event['data']
        })
    
    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event']
        })


class TechnicalSignalsConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    permission_classes = [IsAuthenticated(), CanAccessMarketData()]
    """Real-time technical signals consumer"""
    
    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs'].get('symbol', 'ALL').upper()
        
        if self.symbol == 'ALL':
            self.group_name = 'technical_signals_global'
        else:
            self.group_name = f'technical_signals_{self.symbol}'
        
        # Join technical signals group
        # Use enhanced connect with permission and connection tracking
        await super().connect()
        
        # Join user-specific group with tracking
        await self.join_tracked_group(self.group_name)
        
        # Send initial signal if available
        await self.send_initial_signal()
    
    async def disconnect(self, close_code):
        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'get_signal':
            symbol = data.get('symbol', self.symbol)
            if symbol != 'ALL':
                signal = enhanced_ta_service.get_cached_signal(symbol)
                if signal:
                    await self.send_tracked_message({
                        'type': 'cached_signal',
                        'signal': signal.to_dict()
                    })
        
        elif message_type == 'get_metrics':
            metrics = enhanced_ta_service.get_service_metrics()
            await self.send_tracked_message({
                'type': 'service_metrics',
                'metrics': metrics
            })
    
    async def send_initial_signal(self):
        """Send initial signal state"""
        if self.symbol != 'ALL':
            signal = enhanced_ta_service.get_cached_signal(self.symbol)
            if signal:
                await self.send_tracked_message({
                    'type': 'initial_signal',
                    'signal': signal.to_dict()
                })
        
        # Send service status
        metrics = enhanced_ta_service.get_service_metrics()
        await self.send_tracked_message({
            'type': 'service_status',
            'metrics': metrics
        })
    
    async def technical_signal(self, event):
        """Handle technical signal from enhanced TA service"""
        await self.send_tracked_message({
            'type': 'technical_signal',
            'signal': event['signal']
        })


class AlgorithmExecutionConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    """Real-time algorithm execution status and progress consumer"""
    permission_classes = [IsAuthenticated(), IsOwnerOrReadOnly(), CanControlAlgorithms()]

    
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.algo_group_name = f'algorithm_execution_{self.user_id}'
        
        # Use enhanced connect with permission and connection tracking
        await super().connect()
        
        # Join algorithm execution group with tracking
        await self.join_tracked_group(self.algo_group_name)
        
        # Send initial algorithm status
        await self.send_initial_algorithm_status()
    
    async def disconnect(self, close_code):
        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_algorithms':
            await self.send_initial_algorithm_status()
        elif message_type == 'get_algorithm_details':
            algo_order_id = data.get('algo_order_id')
            if algo_order_id:
                await self.send_algorithm_details(algo_order_id)
        elif message_type == 'pause_algorithm':
            algo_order_id = data.get('algo_order_id')
            if algo_order_id:
                await self.handle_algorithm_control(algo_order_id, 'PAUSE')
        elif message_type == 'resume_algorithm':
            algo_order_id = data.get('algo_order_id')
            if algo_order_id:
                await self.handle_algorithm_control(algo_order_id, 'RESUME')
        elif message_type == 'cancel_algorithm':
            algo_order_id = data.get('algo_order_id')
            if algo_order_id:
                await self.handle_algorithm_control(algo_order_id, 'CANCEL')
        elif message_type == 'heartbeat':
            await self.send_tracked_message({
                'type': 'heartbeat_response',
                'timestamp': timezone.now().isoformat()
            })
    
    async def send_initial_algorithm_status(self):
        """Send current status of all user's active algorithms"""
        algorithms = await self.get_user_active_algorithms()
        await self.send_tracked_message({
            'type': 'initial_algorithm_status',
            'algorithms': algorithms,
            'timestamp': timezone.now().isoformat()
        })
    
    async def send_algorithm_details(self, algo_order_id: str):
        """Send detailed information about a specific algorithm"""
        details = await self.get_algorithm_details(algo_order_id)
        await self.send_tracked_message({
            'type': 'algorithm_details',
            'algo_order_id': algo_order_id,
            'details': details,
            'timestamp': timezone.now().isoformat()
        })
    
    async def handle_algorithm_control(self, algo_order_id: str, action: str):
        """Handle algorithm control actions (pause, resume, cancel)"""
        try:
            success = await self.execute_algorithm_control(algo_order_id, action)
            await self.send_tracked_message({
                'type': 'algorithm_control_response',
                'algo_order_id': algo_order_id,
                'action': action,
                'success': success,
                'timestamp': timezone.now().isoformat()
            })
        except Exception as e:
            await self.send_tracked_message({
                'type': 'algorithm_control_error',
                'algo_order_id': algo_order_id,
                'action': action,
                'error': str(e),
                'timestamp': timezone.now().isoformat()
            })
    
    # Event handlers for algorithm execution events
    async def algorithm_execution_started(self, event):
        """Handle algorithm execution started event"""
        await self.send_tracked_message({
            'type': 'algorithm_started',
            'data': event['data'],
            'timestamp': timezone.now().isoformat()
        })
    
    async def algorithm_execution_progress(self, event):
        """Handle algorithm execution progress event"""
        await self.send_tracked_message({
            'type': 'algorithm_progress',
            'data': event['data'],
            'timestamp': timezone.now().isoformat()
        })
    
    async def algorithm_execution_completed(self, event):
        """Handle algorithm execution completed event"""
        await self.send_tracked_message({
            'type': 'algorithm_completed',
            'data': event['data'],
            'timestamp': timezone.now().isoformat()
        })
    
    async def algorithm_execution_error(self, event):
        """Handle algorithm execution error event"""
        await self.send_tracked_message({
            'type': 'algorithm_error',
            'data': event['data'],
            'timestamp': timezone.now().isoformat()
        })
    
    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send_tracked_message({
            'type': 'event',
            'data': event['event'],
            'timestamp': timezone.now().isoformat()
        })
    
    @database_sync_to_async
    def get_user_active_algorithms(self):
        """Get all active algorithms for the user"""
        try:
            from apps.order_management.models import AlgorithmicOrder
            
            user = User.objects.get(id=self.user_id)
            algorithms = user.algorithmic_orders.filter(
                status__in=['PENDING', 'RUNNING', 'PAUSED']
            ).order_by('-created_timestamp')[:20]
            
            return [{
                'algo_order_id': str(algo.algo_order_id),
                'algorithm_type': algo.algorithm_type,
                'symbol': algo.instrument.real_ticker.symbol,
                'side': algo.side,
                'total_quantity': algo.total_quantity,
                'executed_quantity': algo.executed_quantity,
                'remaining_quantity': algo.remaining_quantity,
                'status': algo.status,
                'progress_percentage': algo.fill_ratio,
                'average_execution_price': float(algo.average_execution_price) if algo.average_execution_price else None,
                'created_timestamp': algo.created_timestamp.isoformat(),
                'started_timestamp': algo.started_timestamp.isoformat() if algo.started_timestamp else None,
                'estimated_completion': algo.end_time.isoformat() if algo.end_time else None
            } for algo in algorithms]
            
        except Exception as e:
            logger.error(f"Error getting user algorithms: {e}")
            return []
    
    @database_sync_to_async
    def get_algorithm_details(self, algo_order_id: str):
        """Get detailed information about a specific algorithm"""
        try:
            from apps.order_management.models import AlgorithmicOrder, AlgorithmExecution
            
            algo = AlgorithmicOrder.objects.get(
                algo_order_id=algo_order_id,
                user_id=self.user_id
            )
            
            # Get execution history
            executions = algo.executions.order_by('execution_step')[:50]
            
            return {
                'algo_order_id': str(algo.algo_order_id),
                'algorithm_type': algo.algorithm_type,
                'symbol': algo.instrument.real_ticker.symbol,
                'side': algo.side,
                'total_quantity': algo.total_quantity,
                'executed_quantity': algo.executed_quantity,
                'remaining_quantity': algo.remaining_quantity,
                'status': algo.status,
                'progress_percentage': algo.fill_ratio,
                'average_execution_price': float(algo.average_execution_price) if algo.average_execution_price else None,
                'total_slippage': float(algo.total_slippage),
                'implementation_shortfall': float(algo.implementation_shortfall) if algo.implementation_shortfall else None,
                'algorithm_parameters': algo.algorithm_parameters,
                'start_time': algo.start_time.isoformat(),
                'end_time': algo.end_time.isoformat(),
                'created_timestamp': algo.created_timestamp.isoformat(),
                'executions': [{
                    'step': exec.execution_step,
                    'executed_quantity': exec.executed_quantity,
                    'execution_price': float(exec.execution_price) if exec.execution_price else None,
                    'market_price': float(exec.market_price),
                    'slippage_bps': float(exec.slippage_bps),
                    'scheduled_time': exec.scheduled_time.isoformat(),
                    'execution_time': exec.execution_time.isoformat() if exec.execution_time else None
                } for exec in executions]
            }
            
        except Exception as e:
            logger.error(f"Error getting algorithm details for {algo_order_id}: {e}")
            return {'error': str(e)}
    
    @database_sync_to_async
    def execute_algorithm_control(self, algo_order_id: str, action: str) -> bool:
        """Execute algorithm control action"""
        try:
            from apps.order_management.models import AlgorithmicOrder
            
            algo = AlgorithmicOrder.objects.get(
                algo_order_id=algo_order_id,
                user_id=self.user_id
            )
            
            if action == 'PAUSE' and algo.status == 'RUNNING':
                algo.status = 'PAUSED'
                algo.save()
                return True
            elif action == 'RESUME' and algo.status == 'PAUSED':
                algo.status = 'RUNNING'
                algo.save()
                return True
            elif action == 'CANCEL' and algo.status in ['PENDING', 'RUNNING', 'PAUSED']:
                algo.status = 'CANCELLED'
                algo.completed_timestamp = timezone.now()
                algo.save()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error executing algorithm control {action} for {algo_order_id}: {e}")
            return False


class IntegratedMarketDashboardConsumer(WebSocketPermissionMixin, ConnectionTrackingMixin, AsyncWebsocketConsumer):
    """
    Unified market dashboard consumer that aggregates:
    - Real-time market data and quotes
    - Technical signals and analysis
    - Algorithm execution status
    - Portfolio analytics and P&L
    - Risk alerts and notifications
    - News and market events

    Provides a single WebSocket feed for comprehensive trading dashboards
    """
    permission_classes = [IsAuthenticated(), HasTradingPermission()]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribed_symbols: Set[str] = set()
        self.dashboard_config: Dict[str, Any] = {}
        self.update_frequencies: Dict[str, int] = {
            'market_data': 1,  # Every second
            'portfolio': 5,    # Every 5 seconds
            'analytics': 30,   # Every 30 seconds
            'risk': 60,        # Every minute
        }
        self.last_updates: Dict[str, datetime] = {}

    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        
        # Multiple group subscriptions for comprehensive data
        self.dashboard_group = f'dashboard_{self.user_id}'
        self.user_groups = [
            f'portfolio_{self.user_id}',
            f'orders_{self.user_id}',
            f'algorithm_execution_{self.user_id}',
            f'risk_{self.user_id}',
            'market_data_global',
            'technical_signals_global',
            'dashboard_global'  # ADD THIS LINE
        ]
        
        # Use enhanced connect with permission and connection tracking
        await super().connect()
        
        # Join all relevant groups
        await self.join_tracked_group(self.dashboard_group)
        for group in self.user_groups:
            await self.join_tracked_group(group)
        
        # Send initial dashboard state
        await self.send_initial_dashboard()
        
        # Start periodic updates
        asyncio.create_task(self.periodic_updates_loop())

    async def disconnect(self, close_code):
        # Unsubscribe from streaming symbols
        for symbol in self.subscribed_symbols:
            streaming_engine.unsubscribe_symbol(symbol)

        # Use enhanced disconnect with cleanup
        await super().disconnect(close_code)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'configure_dashboard':
                await self.configure_dashboard(data.get('config', {}))
            elif message_type == 'subscribe_symbol':
                symbol = data.get('symbol', '').upper()
                if symbol:
                    await self.subscribe_to_symbol(symbol)
            elif message_type == 'unsubscribe_symbol':
                symbol = data.get('symbol', '').upper()
                if symbol:
                    await self.unsubscribe_from_symbol(symbol)
            elif message_type == 'request_snapshot':
                await self.send_complete_snapshot()
            elif message_type == 'update_frequency':
                component = data.get('component')
                frequency = data.get('frequency', 5)
                if component in self.update_frequencies:
                    self.update_frequencies[component] = max(1, min(300, frequency))
            elif message_type == 'request_historical':
                await self.send_historical_data(data)
            elif message_type == 'heartbeat':
                await self.send_tracked_message({
                    'type': 'heartbeat_response',
                    'timestamp': timezone.now().isoformat()
                })

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Dashboard receive error: {e}")
            await self.send_error(f"Processing error: {str(e)}")

    async def configure_dashboard(self, config: Dict[str, Any]):
        """Configure dashboard display preferences"""
        self.dashboard_config = {
            'layout': config.get('layout', 'standard'),
            'watchlist': config.get('watchlist', []),
            'show_portfolio': config.get('show_portfolio', True),
            'show_orders': config.get('show_orders', True),
            'show_algorithms': config.get('show_algorithms', True),
            'show_risk': config.get('show_risk', True),
            'show_news': config.get('show_news', False),
            'theme': config.get('theme', 'dark'),
            'update_mode': config.get('update_mode', 'real_time'),
        }

        # Subscribe to watchlist symbols
        for symbol in self.dashboard_config.get('watchlist', []):
            await self.subscribe_to_symbol(symbol.upper())

        await self.send_tracked_message({
            'type': 'dashboard_configured',
            'config': self.dashboard_config,
            'timestamp': timezone.now().isoformat()
        })

    async def subscribe_to_symbol(self, symbol: str):
        """Subscribe to market data for a symbol"""
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols.add(symbol)
            streaming_engine.subscribe_symbol(symbol, high_frequency=True)

            # Send current data for the symbol
            await self.send_symbol_snapshot(symbol)

            await self.send_tracked_message({
                'type': 'symbol_subscribed',
                'symbol': symbol,
                'timestamp': timezone.now().isoformat()
            })

    async def unsubscribe_from_symbol(self, symbol: str):
        """Unsubscribe from market data for a symbol"""
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols.remove(symbol)
            streaming_engine.unsubscribe_symbol(symbol)

            await self.send_tracked_message({
                'type': 'symbol_unsubscribed',
                'symbol': symbol,
                'timestamp': timezone.now().isoformat()
            })

    async def send_initial_dashboard(self):
        """Send initial dashboard state"""
        try:
            # Get initial data from all services
            portfolio_data = await self.get_portfolio_summary()
            orders_data = await self.get_active_orders()
            algorithms_data = await self.get_active_algorithms()
            market_overview = await self.get_market_overview()
            risk_summary = await self.get_risk_summary()

            dashboard_state = {
                'type': 'dashboard_initial',
                'data': {
                    'portfolio': portfolio_data,
                    'orders': orders_data,
                    'algorithms': algorithms_data,
                    'market_overview': market_overview,
                    'risk_summary': risk_summary,
                    'subscribed_symbols': list(self.subscribed_symbols),
                    'update_frequencies': self.update_frequencies,
                    'server_time': timezone.now().isoformat()
                },
                'timestamp': timezone.now().isoformat()
            }

            await self.send_tracked_message(dashboard_state)

        except Exception as e:
            logger.error(f"Error sending initial dashboard: {e}")
            await self.send_error("Failed to load dashboard data")

    async def send_complete_snapshot(self):
        """Send complete dashboard snapshot"""
        try:
            # Comprehensive snapshot with all current data
            snapshot_data = {
                'type': 'dashboard_snapshot',
                'data': {
                    'portfolio': await self.get_detailed_portfolio(),
                    'positions': await self.get_position_details(),
                    'orders': await self.get_detailed_orders(),
                    'algorithms': await self.get_detailed_algorithms(),
                    'market_data': await self.get_subscribed_market_data(),
                    'technical_signals': await self.get_technical_signals(),
                    'risk_metrics': await self.get_comprehensive_risk(),
                    'performance': await self.get_performance_summary(),
                },
                'metadata': {
                    'snapshot_time': timezone.now().isoformat(),
                    'data_freshness': await self.calculate_data_freshness(),
                    'active_subscriptions': len(self.subscribed_symbols),
                    'dashboard_config': self.dashboard_config
                }
            }

            await self.send_tracked_message(snapshot_data)

        except Exception as e:
            logger.error(f"Error sending dashboard snapshot: {e}")
            await self.send_error("Failed to generate snapshot")

    async def send_symbol_snapshot(self, symbol: str):
        """Send current data snapshot for a specific symbol"""
        try:
            # Get current quote
            quote = await streaming_engine.get_current_quote(symbol)

            # Get technical signal
            signal = enhanced_ta_service.get_cached_signal(symbol)

            # Get user's position in this symbol
            position = await self.get_user_position(symbol)

            symbol_data = {
                'type': 'symbol_snapshot',
                'symbol': symbol,
                'data': {
                    'quote': {
                        'price': float(quote.price) if quote else None,
                        'volume': quote.volume if quote else 0,
                        'timestamp': quote.timestamp.isoformat() if quote else None
                    },
                    'technical_signal': signal.to_dict() if signal else None,
                    'position': position,
                    'market_status': 'OPEN'  # Would determine actual market status
                },
                'timestamp': timezone.now().isoformat()
            }

            await self.send_tracked_message(symbol_data)

        except Exception as e:
            logger.error(f"Error sending symbol snapshot for {symbol}: {e}")

    async def periodic_updates_loop(self):
        """Background task for periodic dashboard updates"""
        while True:
            try:
                now = timezone.now()

                # Check each component's update frequency
                for component, frequency in self.update_frequencies.items():
                    last_update = self.last_updates.get(component)

                    if not last_update or (now - last_update).total_seconds() >= frequency:
                        await self.send_component_update(component)
                        self.last_updates[component] = now

                # Sleep for 1 second (minimum update interval)
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic updates loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def send_component_update(self, component: str):
        """Send update for a specific dashboard component"""
        try:
            if component == 'portfolio':
                data = await self.get_portfolio_summary()
                message_type = 'portfolio_update'
            elif component == 'market_data':
                data = await self.get_market_updates()
                message_type = 'market_update'
            elif component == 'analytics':
                data = await self.get_analytics_update()
                message_type = 'analytics_update'
            elif component == 'risk':
                data = await self.get_risk_update()
                message_type = 'risk_update'
            else:
                return

            await self.send_tracked_message({
                'type': message_type,
                'data': data,
                'timestamp': timezone.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Error sending {component} update: {e}")

    # Event handlers for incoming data from other consumers
    async def portfolio_update(self, event):
        """Handle portfolio updates from PortfolioUpdatesConsumer"""
        await self.send_tracked_message({
            'type': 'dashboard_portfolio_update',
            'data': event.get('portfolio', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def portfolio_analytics_update(self, event):
        """Handle portfolio analytics updates from tasks"""
        await self.send_tracked_message({
            'type': 'dashboard_analytics_update',
            'data': event.get('analytics', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def position_analytics_update(self, event):
        """Handle position analytics updates from tasks"""
        await self.send_tracked_message({
            'type': 'dashboard_positions_update',
            'data': event.get('analytics', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def order_update(self, event):
        """Handle order updates"""
        await self.send_tracked_message({
            'type': 'dashboard_order_update',
            'data': event.get('order', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def algorithm_execution_progress(self, event):
        """Handle algorithm execution updates"""
        await self.send_tracked_message({
            'type': 'dashboard_algorithm_update',
            'data': event.get('data', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def price_update(self, event):
        """Handle market data price updates"""
        price_data = event.get('data', {})
        symbol = price_data.get('symbol')

        if symbol in self.subscribed_symbols:
            await self.send_tracked_message({
                'type': 'dashboard_price_update',
                'data': price_data,
                'timestamp': timezone.now().isoformat()
            })

    async def technical_signal(self, event):
        """Handle technical signal updates"""
        signal_data = event.get('signal', {})
        symbol = signal_data.get('symbol')

        if symbol in self.subscribed_symbols:
            await self.send_tracked_message({
                'type': 'dashboard_signal_update',
                'data': signal_data,
                'timestamp': timezone.now().isoformat()
            })

    async def risk_alert(self, event):
        """Handle risk alerts"""
        await self.send_tracked_message({
            'type': 'dashboard_risk_alert',
            'data': event.get('alert', {}),
            'timestamp': timezone.now().isoformat()
        })

    async def event_message(self, event):
        """Handle general events from event bus"""
        event_data = event.get('event', {})
        event_type = event_data.get('event_type', '')

        # Filter relevant events for dashboard
        relevant_events = [
            'market_data.updated',
            'technical.signal',
            'order.filled',
            'algorithm.execution.progress',
            'risk.alert'
        ]

        if event_type in relevant_events:
            await self.send_tracked_message({
                'type': 'dashboard_event',
                'data': event_data,
                'timestamp': timezone.now().isoformat()
            })

    async def send_error(self, message: str, error_code: str = "DASHBOARD_ERROR"):
        """Send error message to dashboard"""
        await self.send_tracked_message({
            'type': 'dashboard_error',
            'error': {
                'code': error_code,
                'message': message,
                'timestamp': timezone.now().isoformat()
            }
        })

    # Helper methods for data aggregation
    @database_sync_to_async
    def get_portfolio_summary(self):
        """Get portfolio summary data"""
        try:
            user = User.objects.get(id=self.user_id)
            profile = user.simulation_profile

            return {
                'total_value': float(profile.current_portfolio_value),
                'cash_balance': float(profile.virtual_cash_balance),
                'daily_pnl': 0.0,  # Would calculate from positions
                'total_return_pct': profile.calculate_total_return_percentage(),
                'positions_count': user.simulated_positions.count(),
                'orders_count': user.simulated_orders.filter(
                    status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
                ).count()
            }
        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return {}

    @database_sync_to_async
    def get_detailed_portfolio(self):
        """Get detailed portfolio information"""
        try:
            from apps.trading_analytics.portfolio_analytics import portfolio_analytics_service

            # This would normally be async, but we're in a sync context
            # analytics = await portfolio_analytics_service.calculate_comprehensive_analytics(self.user_id)

            user = User.objects.get(id=self.user_id)
            profile = user.simulation_profile
            positions = user.simulated_positions.all()

            return {
                'summary': {
                    'total_value': float(profile.current_portfolio_value),
                    'cash_balance': float(profile.virtual_cash_balance),
                    'invested_value': float(profile.current_portfolio_value - profile.virtual_cash_balance),
                    'total_return_pct': profile.calculate_total_return_percentage()
                },
                'positions': [{
                    'symbol': pos.instrument.real_ticker.symbol,
                    'quantity': float(pos.quantity),
                    'current_price': float(pos.current_price) if pos.current_price else None,
                    'market_value': float(pos.market_value),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'unrealized_pnl_pct': (float(pos.unrealized_pnl) / float(pos.market_value) * 100) if pos.market_value else 0,
                    'weight_pct': (float(pos.market_value) / float(profile.current_portfolio_value) * 100) if profile.current_portfolio_value else 0
                } for pos in positions],
                'allocation': self._calculate_allocation_summary(positions, profile.current_portfolio_value)
            }
        except Exception as e:
            logger.error(f"Error getting detailed portfolio: {e}")
            return {}

    def _calculate_allocation_summary(self, positions, total_value):
        """Calculate portfolio allocation summary"""
        try:
            if not total_value or total_value == 0:
                return {}

            # Group by sector (simplified - would use real sector data)
            sector_allocation = {}
            for pos in positions:
                sector = 'Technology'  # Would get real sector from ticker data
                current_value = sector_allocation.get(sector, 0)
                sector_allocation[sector] = current_value + float(pos.market_value)

            # Convert to percentages
            allocation_pct = {}
            for sector, value in sector_allocation.items():
                allocation_pct[sector] = (value / float(total_value)) * 100

            return {
                'by_sector': allocation_pct,
                'largest_position': max([
                    (float(pos.market_value) / float(total_value) * 100)
                    for pos in positions
                ], default=0),
                'top_5_concentration': sum(sorted([
                    (float(pos.market_value) / float(total_value) * 100)
                    for pos in positions
                ], reverse=True)[:5])
            }
        except Exception as e:
            logger.error(f"Error calculating allocation: {e}")
            return {}

    @database_sync_to_async
    def get_position_details(self):
        """Get detailed position information"""
        try:
            user = User.objects.get(id=self.user_id)
            positions = user.simulated_positions.select_related('instrument__real_ticker').all()

            position_details = []
            for pos in positions:
                position_details.append({
                    'symbol': pos.instrument.real_ticker.symbol,
                    'name': pos.instrument.real_ticker.name,
                    'quantity': float(pos.quantity),
                    'average_cost': float(pos.average_cost),
                    'current_price': float(pos.current_price) if pos.current_price else None,
                    'market_value': float(pos.market_value),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'daily_pnl': float(pos.daily_pnl),
                    'unrealized_pnl_pct': (float(pos.unrealized_pnl) / (float(pos.quantity) * float(pos.average_cost)) * 100) if pos.average_cost and pos.quantity else 0,
                    'last_updated': pos.last_trade_timestamp.isoformat() if pos.last_trade_timestamp else None
                })

            return position_details
        except Exception as e:
            logger.error(f"Error getting position details: {e}")
            return []

    @database_sync_to_async
    def get_active_orders(self):
        """Get active orders summary"""
        try:
            user = User.objects.get(id=self.user_id)
            orders = user.simulated_orders.filter(
                status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
            ).order_by('-order_timestamp')[:10]

            return [{
                'order_id': str(order.order_id),
                'symbol': order.instrument.real_ticker.symbol,
                'side': order.side,
                'order_type': order.order_type,
                'quantity': order.quantity,
                'filled_quantity': order.filled_quantity,
                'price': float(order.price) if order.price else None,
                'status': order.status,
                'timestamp': order.order_timestamp.isoformat()
            } for order in orders]
        except Exception as e:
            logger.error(f"Error getting active orders: {e}")
            return []

    @database_sync_to_async
    def get_detailed_orders(self):
        """Get detailed orders including recent history"""
        try:
            user = User.objects.get(id=self.user_id)

            # Get active orders
            active_orders = user.simulated_orders.filter(
                status__in=['PENDING', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED']
            ).order_by('-order_timestamp')

            # Get recent completed orders
            recent_orders = user.simulated_orders.filter(
                status__in=['FILLED', 'CANCELLED'],
                order_timestamp__gte=timezone.now() - timedelta(hours=24)
            ).order_by('-order_timestamp')[:20]

            def serialize_order(order):
                return {
                    'order_id': str(order.order_id),
                    'symbol': order.instrument.real_ticker.symbol,
                    'side': order.side,
                    'order_type': order.order_type,
                    'quantity': order.quantity,
                    'filled_quantity': order.filled_quantity,
                    'remaining_quantity': order.remaining_quantity,
                    'price': float(order.price) if order.price else None,
                    'average_fill_price': float(order.average_fill_price) if order.average_fill_price else None,
                    'status': order.status,
                    'order_timestamp': order.order_timestamp.isoformat(),
                    'completion_timestamp': order.completion_timestamp.isoformat() if order.completion_timestamp else None
                }

            return {
                'active': [serialize_order(order) for order in active_orders],
                'recent': [serialize_order(order) for order in recent_orders]
            }
        except Exception as e:
            logger.error(f"Error getting detailed orders: {e}")
            return {'active': [], 'recent': []}

    @database_sync_to_async
    def get_active_algorithms(self):
        """Get active algorithmic orders"""
        try:
            from apps.order_management.models import AlgorithmicOrder

            user = User.objects.get(id=self.user_id)
            algorithms = user.algorithmic_orders.filter(
                status__in=['PENDING', 'RUNNING', 'PAUSED']
            ).order_by('-created_timestamp')[:5]

            return [{
                'algo_order_id': str(algo.algo_order_id),
                'algorithm_type': algo.algorithm_type,
                'symbol': algo.instrument.real_ticker.symbol,
                'side': algo.side,
                'total_quantity': algo.total_quantity,
                'executed_quantity': algo.executed_quantity,
                'progress_pct': algo.fill_ratio,
                'status': algo.status,
                'start_time': algo.start_time.isoformat() if algo.start_time else None,
                'estimated_completion': algo.end_time.isoformat() if algo.end_time else None
            } for algo in algorithms]
        except Exception as e:
            logger.error(f"Error getting active algorithms: {e}")
            return []

    @database_sync_to_async
    def get_detailed_algorithms(self):
        """Get detailed algorithm information"""
        try:
            from apps.order_management.models import AlgorithmicOrder

            user = User.objects.get(id=self.user_id)
            algorithms = user.algorithmic_orders.order_by('-created_timestamp')[:10]

            detailed_algorithms = []
            for algo in algorithms:
                detailed_algorithms.append({
                    'algo_order_id': str(algo.algo_order_id),
                    'algorithm_type': algo.algorithm_type,
                    'symbol': algo.instrument.real_ticker.symbol,
                    'side': algo.side,
                    'total_quantity': algo.total_quantity,
                    'executed_quantity': algo.executed_quantity,
                    'remaining_quantity': algo.remaining_quantity,
                    'progress_pct': algo.fill_ratio,
                    'status': algo.status,
                    'average_execution_price': float(algo.average_execution_price) if algo.average_execution_price else None,
                    'total_slippage': float(algo.total_slippage),
                    'algorithm_parameters': algo.algorithm_parameters,
                    'created_timestamp': algo.created_timestamp.isoformat(),
                    'started_timestamp': algo.started_timestamp.isoformat() if algo.started_timestamp else None,
                    'completed_timestamp': algo.completed_timestamp.isoformat() if algo.completed_timestamp else None,
                    'execution_count': algo.executions.count()
                })

            return detailed_algorithms
        except Exception as e:
            logger.error(f"Error getting detailed algorithms: {e}")
            return []

    async def get_market_overview(self):
        """Get market overview data"""
        try:
            # Get market status and key indices
            market_data = {}

            # Major indices (would get real data)
            indices = ['SPY', 'QQQ', 'IWM', 'VIX']
            for index in indices:
                quote = await streaming_engine.get_current_quote(index)
                if quote:
                    market_data[index] = {
                        'price': float(quote.price),
                        'change': float(quote.change_24h) if quote.change_24h else 0,
                        'change_pct': quote.change_pct_24h or 0
                    }

            return {
                'indices': market_data,
                'market_status': 'OPEN',  # Would determine actual status
                'session_info': {
                    'trading_session': 'REGULAR',
                    'next_open': None,
                    'next_close': None
                },
                'market_sentiment': {
                    'fear_greed_index': 50,  # Would get real data
                    'vix_level': market_data.get('VIX', {}).get('price', 20),
                    'advance_decline': {'advancing': 1500, 'declining': 1200}
                }
            }
        except Exception as e:
            logger.error(f"Error getting market overview: {e}")
            return {}

    async def get_subscribed_market_data(self):
        """Get current market data for subscribed symbols"""
        try:
            market_data = {}

            for symbol in self.subscribed_symbols:
                quote = await streaming_engine.get_current_quote(symbol)
                signal = enhanced_ta_service.get_cached_signal(symbol)

                if quote:
                    market_data[symbol] = {
                        'quote': {
                            'price': float(quote.price),
                            'volume': quote.volume,
                            'bid': float(quote.bid) if quote.bid else None,
                            'ask': float(quote.ask) if quote.ask else None,
                            'change_24h': float(quote.change_24h) if quote.change_24h else None,
                            'change_pct_24h': quote.change_pct_24h,
                            'timestamp': quote.timestamp.isoformat()
                        },
                        'technical_signal': signal.to_dict() if signal else None
                    }

            return market_data
        except Exception as e:
            logger.error(f"Error getting subscribed market data: {e}")
            return {}

    async def get_technical_signals(self):
        """Get technical signals for subscribed symbols"""
        try:
            signals = {}

            for symbol in self.subscribed_symbols:
                signal = enhanced_ta_service.get_cached_signal(symbol)
                if signal:
                    signals[symbol] = signal.to_dict()

            return signals
        except Exception as e:
            logger.error(f"Error getting technical signals: {e}")
            return {}

    async def get_risk_summary(self):
        """Get risk metrics summary"""
        try:
            # Get basic risk metrics
            user_positions_count = await self._get_positions_count()
            portfolio_value = await self._get_portfolio_value()

            # Simplified risk calculation
            risk_summary = {
                'portfolio_var_1d': portfolio_value * 0.02,  # 2% daily VaR estimate
                'largest_position_pct': 0,  # Would calculate actual
                'positions_count': user_positions_count,
                'leverage_ratio': 1.0,  # No leverage in simulation
                'risk_score': 'LOW',  # GREEN/YELLOW/RED
                'alerts_count': await self._get_active_alerts_count()
            }

            return risk_summary
        except Exception as e:
            logger.error(f"Error getting risk summary: {e}")
            return {}

    async def get_comprehensive_risk(self):
        """Get comprehensive risk metrics"""
        try:
            from apps.trading_analytics.portfolio_analytics import portfolio_analytics_service

            # This would integrate with the portfolio analytics service
            # analytics = await portfolio_analytics_service.calculate_comprehensive_analytics(self.user_id)

            return {
                'var_metrics': {
                    'var_1d_95': 1000,  # Would calculate actual VaR
                    'var_1d_99': 1500,
                    'expected_shortfall': 2000
                },
                'concentration_risk': {
                    'largest_position_pct': 0,
                    'top_5_concentration': 0,
                    'herfindahl_index': 0
                },
                'correlation_risk': {
                    'avg_correlation': 0.3,
                    'max_correlation': 0.8
                },
                'liquidity_risk': {
                    'illiquid_positions_pct': 0,
                    'avg_bid_ask_spread': 0.01
                }
            }
        except Exception as e:
            logger.error(f"Error getting comprehensive risk: {e}")
            return {}

    async def get_performance_summary(self):
        """Get performance summary"""
        try:
            user = await self._get_user()
            profile = user.simulation_profile

            return {
                'current_performance': {
                    'total_return_pct': profile.calculate_total_return_percentage(),
                    'daily_pnl': 0,  # Would calculate
                    'weekly_pnl': 0,
                    'monthly_pnl': 0,
                    'ytd_pnl': 0
                },
                'risk_adjusted': {
                    'sharpe_ratio': None,  # Would calculate
                    'max_drawdown': None,
                    'volatility': None
                },
                'trading_activity': {
                    'trades_today': 0,  # Would calculate
                    'win_rate': profile.get_win_rate(),
                    'avg_hold_time': None
                }
            }
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}

    async def get_market_updates(self):
        """Get latest market updates"""
        return await self.get_subscribed_market_data()

    async def get_analytics_update(self):
        """Get analytics updates"""
        try:
            return {
                'portfolio_summary': await self.get_portfolio_summary(),
                'performance_summary': await self.get_performance_summary()
            }
        except Exception as e:
            logger.error(f"Error getting analytics update: {e}")
            return {}

    async def get_risk_update(self):
        """Get risk updates"""
        return await self.get_risk_summary()

    async def calculate_data_freshness(self):
        """Calculate overall data freshness score"""
        try:
            # Simple freshness calculation based on last updates
            scores = []

            # Check streaming data freshness
            for symbol in list(self.subscribed_symbols)[:5]:  # Sample a few symbols
                quote = await streaming_engine.get_current_quote(symbol)
                if quote:
                    age_seconds = (timezone.now() - quote.timestamp).total_seconds()
                    freshness = max(0, 100 - (age_seconds / 60 * 10))  # Decrease by 10 per minute
                    scores.append(freshness)

            return sum(scores) / len(scores) if scores else 0
        except Exception as e:
            logger.error(f"Error calculating data freshness: {e}")
            return 0

    # Utility helper methods
    @database_sync_to_async
    def _get_user(self):
        return User.objects.get(id=self.user_id)

    @database_sync_to_async
    def _get_positions_count(self):
        user = User.objects.get(id=self.user_id)
        return user.simulated_positions.count()

    @database_sync_to_async
    def _get_portfolio_value(self):
        user = User.objects.get(id=self.user_id)
        return float(user.simulation_profile.current_portfolio_value)

    @database_sync_to_async
    def _get_active_alerts_count(self):
        try:
            from apps.trading_analytics.models import RiskAlert
            user = User.objects.get(id=self.user_id)
            return user.real_time_risk_alerts.filter(status='ACTIVE').count()
        except Exception:
            return 0

    @database_sync_to_async
    def get_user_position(self, symbol: str):
        """Get user's position in a specific symbol"""
        try:
            user = User.objects.get(id=self.user_id)
            position = user.simulated_positions.filter(
                instrument__real_ticker__symbol=symbol
            ).first()

            if position:
                return {
                    'quantity': float(position.quantity),
                    'average_cost': float(position.average_cost),
                    'market_value': float(position.market_value),
                    'unrealized_pnl': float(position.unrealized_pnl),
                    'daily_pnl': float(position.daily_pnl)
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user position for {symbol}: {e}")
            return None

    async def market_summary_broadcast(self, event):
        """Handle global market summary broadcasts"""
        await self.send_tracked_message(event['data'])

