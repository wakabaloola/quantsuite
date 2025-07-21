# apps/trading_simulation/consumers.py
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import SimulatedInstrument, UserSimulationProfile
from apps.core.events import event_bus
from apps.market_data.streaming import streaming_engine
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
    
    async def disconnect(self, close_code):
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

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'data': event['event']
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
    
    async def disconnect(self, close_code):
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

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'data': event['event']
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
    
    async def disconnect(self, close_code):
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
    
    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'data': event['event']
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
    
    async def disconnect(self, close_code):
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

    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'data': event['event']
        }))


class RealTimeMarketDataConsumer(AsyncWebsocketConsumer):
    """Real-time market data streaming consumer"""
    
    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs'].get('symbol', 'ALL').upper()
        
        if self.symbol == 'ALL':
            self.group_name = 'market_data_global'
        else:
            self.group_name = f'market_{self.symbol}'
        
        # Join market data group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
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
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'subscribe':
            symbol = data.get('symbol', '').upper()
            if symbol:
                streaming_engine.subscribe_symbol(symbol, high_frequency=True)
                await self.send(text_data=json.dumps({
                    'type': 'subscription_confirmed',
                    'symbol': symbol
                }))
        
        elif message_type == 'unsubscribe':
            symbol = data.get('symbol', '').upper()
            if symbol:
                streaming_engine.unsubscribe_symbol(symbol)
                await self.send(text_data=json.dumps({
                    'type': 'unsubscription_confirmed',
                    'symbol': symbol
                }))
        
        elif message_type == 'get_metrics':
            metrics = streaming_engine.get_metrics()
            await self.send(text_data=json.dumps({
                'type': 'metrics',
                'data': metrics
            }))
    
    async def send_initial_data(self):
        """Send initial market data state"""
        if self.symbol != 'ALL':
            # Send current quote if available
            quote = await streaming_engine.get_current_quote(self.symbol)
            if quote:
                await self.send(text_data=json.dumps({
                    'type': 'initial_quote',
                    'data': {
                        'symbol': quote.symbol,
                        'price': float(quote.price),
                        'volume': quote.volume,
                        'timestamp': quote.timestamp.isoformat()
                    }
                }))
        
        # Send streaming status
        metrics = streaming_engine.get_metrics()
        await self.send(text_data=json.dumps({
            'type': 'streaming_status',
            'status': metrics['status'],
            'active_symbols': metrics['active_symbols'],
            'data_quality': metrics['performance']['data_quality']
        }))
    
    async def price_update(self, event):
        """Handle price update from streaming engine"""
        await self.send(text_data=json.dumps({
            'type': 'price_update',
            'data': event['data']
        }))
    
    async def event_message(self, event):
        """Handle events from event bus"""
        await self.send(text_data=json.dumps({
            'type': 'event',
            'data': event['event']
        }))
