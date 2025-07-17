# apps/trading_simulation/consumers.py
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import SimulatedInstrument, UserSimulationProfile
from apps.order_management.models import SimulatedOrder
from apps.risk_management.models import SimulatedPosition

User = get_user_model()

class OrderUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.user_group_name = f'orders_{self.user_id}'
        
        # Join user-specific group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial order status
        await self.send_initial_orders()

        await self.start_heartbeat() # Start heartbeat
    
    async def disconnect(self, close_code):
        await self.stop_heartbeat() # Stop heartbeat

        await self.channel_layer.group_discard(
            self.user_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_orders':
            await self.send_initial_orders()
        elif message_type == 'heartbeat':
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_response',
                'timestamp': timezone.now().isoformat()
            }))
    
    async def send_initial_orders(self):
        orders = await self.get_user_orders()
        await self.send(text_data=json.dumps({
            'type': 'initial_orders',
            'orders': orders
        }))
    
    async def order_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'order_update',
            'order': event['order']
        }))
    
    async def order_filled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'order_filled',
            'order': event['order'],
            'fill_details': event['fill_details']
        }))

    async def algorithm_update(self, event):
        """Handle algorithm status updates"""
        await self.send(text_data=json.dumps({
            'type': 'algorithm_update',
            'algorithm': event['algorithm']
        }))

    async def execution_update(self, event):
        """Handle algorithm execution updates"""
        await self.send(text_data=json.dumps({
            'type': 'execution_update',
            'execution': event['execution']
        }))

    async def algorithm_started(self, event):
        """Handle algorithm start notifications"""
        await self.send(text_data=json.dumps({
            'type': 'algorithm_started',
            'algorithm': event['algorithm']
        }))

    async def algorithm_completed(self, event):
        """Handle algorithm completion notifications"""
        await self.send(text_data=json.dumps({
            'type': 'algorithm_completed',
            'algorithm': event['algorithm'],
            'performance': event.get('performance', {})
        }))
    
    async def start_heartbeat(self):
        """Start heartbeat task"""
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

    async def heartbeat_loop(self):
        """Send periodic heartbeat"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            pass

    async def handle_error(self, error_message: str, error_code: str = 'GENERAL_ERROR'):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error_code': error_code,
            'message': error_message,
            'timestamp': timezone.now().isoformat()
        }))

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
            await self.handle_error(f"Failed to fetch orders: {str(e)}", 'FETCH_ORDERS_ERROR')
            return []


class PortfolioUpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.user_group_name = f'portfolio_{self.user_id}'
        
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        await self.send_initial_portfolio()

        await self.start_heartbeat() # Start heartbeat
    
    async def disconnect(self, close_code):
        await self.stop_heartbeat() # Stop heartbeat

        await self.channel_layer.group_discard(
            self.user_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_portfolio':
            await self.send_initial_portfolio()
    
    async def send_initial_portfolio(self):
        portfolio = await self.get_user_portfolio()
        await self.send(text_data=json.dumps({
            'type': 'initial_portfolio',
            'portfolio': portfolio
        }))
    
    async def portfolio_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'portfolio_update',
            'portfolio': event['portfolio']
        }))
    
    async def position_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'position_update',
            'position': event['position']
        }))
    
    async def start_heartbeat(self):
        """Start heartbeat task"""
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

    async def heartbeat_loop(self):
        """Send periodic heartbeat"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            pass

    async def handle_error(self, error_message: str, error_code: str = 'GENERAL_ERROR'):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error_code': error_code,
            'message': error_message,
            'timestamp': timezone.now().isoformat()
        }))

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
            await self.handle_error(f"Failed to fetch user portfolio: {str(e)}", 'FETCH_PORTFOLIO_ERROR')
            return {'error': str(e)}


class MarketDataConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs']['symbol']
        self.market_group_name = f'market_{self.symbol}'
        
        await self.channel_layer.group_add(
            self.market_group_name,
            self.channel_name
        )
        
        await self.accept()
        await self.send_initial_market_data()
    
        await self.start_heartbeat() # Start heartbeat

    async def disconnect(self, close_code):
        await self.stop_heartbeat() # Stop heartbeat
        await self.channel_layer.group_discard(
            self.market_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_market':
            await self.send_initial_market_data()
    
    async def send_initial_market_data(self):
        market_data = await self.get_market_data()
        await self.send(text_data=json.dumps({
            'type': 'initial_market_data',
            'data': market_data
        }))
    
    async def price_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'price_update',
            'data': event['data']
        }))
    
    async def orderbook_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'orderbook_update',
            'data': event['data']
        }))
    
    async def start_heartbeat(self):
        """Start heartbeat task"""
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

    async def heartbeat_loop(self):
        """Send periodic heartbeat"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            pass

    async def handle_error(self, error_message: str, error_code: str = 'GENERAL_ERROR'):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error_code': error_code,
            'message': error_message,
            'timestamp': timezone.now().isoformat()
        }))

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
            await self.handle_error(f"Failed to fetch market data: {str(e)}", 'FETCH_MARKET_DATA_ERROR')
            return {'error': str(e)}


class RiskAlertsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.risk_group_name = f'risk_{self.user_id}'
        
        await self.channel_layer.group_add(
            self.risk_group_name,
            self.channel_name
        )
        
        await self.accept()
        await self.start_heartbeat() # Start heartbeat
    
    async def disconnect(self, close_code):
        await self.stop_heartbeat() # Stop heartbeat
        await self.channel_layer.group_discard(
            self.risk_group_name,
            self.channel_name
        )
    
    async def risk_alert(self, event):
        await self.send(text_data=json.dumps({
            'type': 'risk_alert',
            'alert': event['alert']
        }))
    
    async def compliance_alert(self, event):
        await self.send(text_data=json.dumps({
            'type': 'compliance_alert',
            'alert': event['alert']
        }))

    async def algorithm_risk_alert(self, event):
        """Handle algorithm-specific risk alerts"""
        await self.send(text_data=json.dumps({
            'type': 'algorithm_risk_alert',
            'alert': event['alert'],
            'algorithm_id': event.get('algorithm_id'),
            'severity': event.get('severity', 'MEDIUM')
        }))

    async def algorithm_rejected(self, event):
        """Handle algorithm rejection notifications"""
        await self.send(text_data=json.dumps({
            'type': 'algorithm_rejected',
            'algorithm_id': event['algorithm_id'],
            'rejection_reason': event['rejection_reason'],
            'violations': event.get('violations', [])
        }))

    async def start_heartbeat(self):
        """Start heartbeat task"""
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

    async def heartbeat_loop(self):
        """Send periodic heartbeat"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            pass

    async def handle_error(self, error_message: str, error_code: str = 'GENERAL_ERROR'):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error_code': error_code,
            'message': error_message,
            'timestamp': timezone.now().isoformat()
        }))


class AlgorithmUpdatesConsumer(AsyncWebsocketConsumer):
    """Dedicated consumer for algorithm execution updates"""
    
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.algorithm_group_name = f'algorithms_{self.user_id}'
        
        # Join user-specific algorithm group
        await self.channel_layer.group_add(
            self.algorithm_group_name,
            self.channel_name
        )
        
        await self.accept()
        await self.send_initial_algorithms()
        await self.start_heartbeat() # Start heartbeat

    async def disconnect(self, close_code):
        await self.stop_heartbeat() # Stop heartbeat
        await self.channel_layer.group_discard(
            self.algorithm_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe_algorithms':
            await self.send_initial_algorithms()
        elif message_type == 'heartbeat':
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_response',
                'timestamp': timezone.now().isoformat()
            }))
    
    async def send_initial_algorithms(self):
        algorithms = await self.get_user_algorithms()
        await self.send(text_data=json.dumps({
            'type': 'initial_algorithms',
            'algorithms': algorithms
        }))
    
    async def algorithm_update(self, event):
        await self.send(text_data=json.dumps(event))
    
    async def execution_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def start_heartbeat(self):
        """Start heartbeat task"""
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

    async def heartbeat_loop(self):
        """Send periodic heartbeat"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            pass

    async def handle_error(self, error_message: str, error_code: str = 'GENERAL_ERROR'):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error_code': error_code,
            'message': error_message,
            'timestamp': timezone.now().isoformat()
        }))
    
    @database_sync_to_async
    def get_user_algorithms(self):
        try:
            from apps.order_management.models import AlgorithmicOrder
            user = User.objects.get(id=self.user_id)
            algorithms = user.algorithmic_orders.filter(
                status__in=['PENDING', 'RUNNING', 'PAUSED']
            ).order_by('-created_timestamp')[:20]
            
            return [{
                'algo_order_id': str(algo.algo_order_id),
                'algorithm_type': algo.algorithm_type,
                'status': algo.status,
                'symbol': algo.instrument.real_ticker.symbol,
                'total_quantity': algo.total_quantity,
                'executed_quantity': algo.executed_quantity,
                'fill_ratio': algo.fill_ratio,
                'created_timestamp': algo.created_timestamp.isoformat(),
                'started_timestamp': algo.started_timestamp.isoformat() if algo.started_timestamp else None
            } for algo in algorithms]
        except Exception as e:
            await self.handle_error(f"Failed to fetch user algorithms: {str(e)}", 'FETCH_USER_ALGORITHMS_ERROR')
            return []
