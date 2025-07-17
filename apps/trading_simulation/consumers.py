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
        try:
            orders = await self.get_user_orders()
            await self.send(text_data=json.dumps({
                'type': 'initial_orders',
                'orders': orders
            }))
        except Exception as e:
            await self.handle_error(f"Failed to fetch orders: {str(e)}", 'FETCH_ORDERS_ERROR')
    
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
        try:
            portfolio = await self.get_user_portfolio()
            if 'error' in portfolio:
                await self.handle_error(f"Failed to fetch portfolio: {portfolio['error']}", 'FETCH_PORTFOLIO_ERROR')
            else:
                await self.send(text_data=json.dumps({
                    'type': 'initial_portfolio',
                    'portfolio': portfolio
                }))
        except Exception as e:
            await self.handle_error(f"Failed to fetch portfolio: {str(e)}", 'FETCH_PORTFOLIO_ERROR')
    
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
            return {'error': str(e)}


class MarketDataConsumer(AsyncWebsocketConsumer):
    """Enhanced WebSocket consumer for real-time market data with algorithm integration"""

    async def connect(self):
        self.symbol = self.scope['url_route']['kwargs']['symbol']
        self.market_group_name = f'market_{self.symbol}'

        # Join market data group
        await self.channel_layer.group_add(
            self.market_group_name,
            self.channel_name
        )

        await self.accept()

        # Send initial market data from market_data app
        await self.send_initial_market_data()

    async def disconnect(self, close_code):
        # Leave market data group
        await self.channel_layer.group_discard(
            self.market_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)

            if data.get('type') == 'subscribe_indicators':
                # Subscribe to technical indicators updates
                indicators = data.get('indicators', ['rsi', 'macd'])
                await self.subscribe_to_indicators(indicators)

            elif data.get('type') == 'request_algorithm_data':
                # Send algorithm-specific market data
                await self.send_algorithm_market_data()

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")

    async def send_initial_market_data(self):
        """Send initial market data from market_data app"""
        try:
            from apps.market_data.models import MarketData, TechnicalIndicator
            from apps.market_data.services import YFinanceService
            from apps.trading_simulation.models import SimulatedInstrument
            from asgiref.sync import sync_to_async

            # Get ticker from symbol
            instrument = await sync_to_async(SimulatedInstrument.objects.select_related('real_ticker').get)(
                real_ticker__symbol=self.symbol
            )

            # Get real-time quote
            yfinance_service = YFinanceService()
            real_time_data = await sync_to_async(yfinance_service.get_real_time_quote)(self.symbol)

            # Get latest technical indicators
            latest_indicators = await sync_to_async(list)(
                TechnicalIndicator.objects.filter(
                    ticker=instrument.real_ticker,
                    timeframe='1d'
                ).order_by('-timestamp')[:10]
            )

            # Build comprehensive market data
            market_data = {
                'type': 'market_data_update',
                'symbol': self.symbol,
                'timestamp': timezone.now().isoformat(),
                'real_time_data': real_time_data,
                'technical_indicators': [
                    {
                        'name': indicator.indicator_name,
                        'value': float(indicator.value) if indicator.value else None,
                        'timestamp': indicator.timestamp.isoformat()
                    }
                    for indicator in latest_indicators
                ],
                'algorithm_metrics': {
                    'volatility_score': await self.calculate_volatility_score(instrument),
                    'liquidity_score': await self.calculate_liquidity_score(instrument),
                    'execution_favorability': await self.calculate_execution_favorability(instrument)
                }
            }

            await self.send(text_data=json.dumps(market_data))

        except Exception as e:
            await self.send_error(f"Failed to load initial market data: {str(e)}")

    async def calculate_volatility_score(self, instrument):
        """Calculate volatility score for algorithm execution"""
        try:
            from apps.market_data.models import MarketData
            from asgiref.sync import sync_to_async

            # Get recent price data
            recent_data = await sync_to_async(list)(
                MarketData.objects.filter(
                    ticker=instrument.real_ticker,
                    timeframe='1d'
                ).order_by('-timestamp')[:20]
            )

            if len(recent_data) < 10:
                return 0.5  # Neutral score

            # Calculate volatility (simplified)
            prices = [float(data.close) for data in recent_data]
            import statistics
            volatility = statistics.stdev(prices) / statistics.mean(prices)

            # Normalize to 0-1 scale
            return min(volatility * 10, 1.0)

        except Exception:
            return 0.5

    async def calculate_liquidity_score(self, instrument):
        """Calculate liquidity score for algorithm execution"""
        try:
            # Use order book data from simulation
            order_book = instrument.order_book

            # Calculate bid-ask spread as liquidity proxy
            if order_book.best_bid_price and order_book.best_ask_price:
                spread = float(order_book.best_ask_price - order_book.best_bid_price)
                mid_price = float(order_book.best_bid_price + order_book.best_ask_price) / 2
                spread_pct = spread / mid_price if mid_price > 0 else 1.0

                # Lower spread = higher liquidity score
                return max(0, 1.0 - (spread_pct * 100))

            return 0.5  # Neutral score

        except Exception:
            return 0.5

    async def calculate_execution_favorability(self, instrument):
        """Calculate overall execution favorability score"""
        try:
            volatility_score = await self.calculate_volatility_score(instrument)
            liquidity_score = await self.calculate_liquidity_score(instrument)

            # Combine scores (lower volatility + higher liquidity = better execution)
            favorability = (liquidity_score + (1.0 - volatility_score)) / 2
            return favorability

        except Exception:
            return 0.5

    # WebSocket message handlers
    async def market_data_update(self, event):
        """Handle market data updates"""
        await self.send(text_data=json.dumps(event))

    async def algorithm_market_update(self, event):
        """Handle algorithm-specific market updates"""
        await self.send(text_data=json.dumps(event))

    async def send_error(self, message):
        """Send error message"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))


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
        try:
            algorithms = await self.get_user_algorithms()
            await self.send(text_data=json.dumps({
                'type': 'initial_algorithms',
                'algorithms': algorithms
            }))
        except Exception as e:
            await self.handle_error(f"Failed to fetch algorithms: {str(e)}", 'FETCH_ALGORITHMS_ERROR')
    
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
            return []
