# apps/market_data/management/commands/demo_real_market_data.py

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone
from apps.market_data.services import DataIngestionService
from apps.market_data.models import DataSource, Exchange, Ticker, MarketData
from decimal import Decimal
import time


class Command(BaseCommand):
    help = 'Demonstrate real market data ingestion using YFinance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbols',
            type=str,
            default='AAPL,GOOGL,MSFT,TSLA,SPY,QQQ,VTI,NVDA,META,AMZN',
            help='Comma-separated list of symbols to ingest'
        )
        parser.add_argument(
            '--period',
            type=str,
            default='6mo',
            help='Data period (1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max)'
        )
        parser.add_argument(
            '--interval',
            type=str,
            default='1d',
            help='Data interval (1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo)'
        )


    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== REAL MARKET DATA INGESTION DEMO ===\n'))
        
        # Parse symbols
        symbols = [s.strip().upper() for s in options['symbols'].split(',')]
        period = options['period']
        interval = options['interval']
        
        self.stdout.write(f"Symbols: {', '.join(symbols)}")
        self.stdout.write(f"Period: {period}, Interval: {interval}\n")
        
        # Initialize services
        ingestion_service = DataIngestionService()
        
        # Show current data sources
        self.show_data_sources()
        
        # Show existing data before ingestion
        self.show_existing_data(symbols)
        
        # Perform real data ingestion
        self.stdout.write(self.style.WARNING('Starting REAL market data ingestion...'))
        start_time = time.time()
        
        ingestion_log = ingestion_service.ingest_market_data(
            symbols=symbols,
            data_source='yfinance',
            period=period,
            interval=interval
        )
        
        end_time = time.time()
        
        # Show results
        self.show_ingestion_results(ingestion_log, end_time - start_time)
        
        # Show updated data
        self.show_final_statistics(symbols)


    def show_data_sources(self):
        self.stdout.write(self.style.HTTP_INFO('--- Data Sources ---'))
        sources = DataSource.objects.all()
        for source in sources:
            status = "✓ Active" if source.is_active else "✗ Inactive"
            self.stdout.write(f"{source.code}: {source.name} ({status})")
        self.stdout.write()


    def show_existing_data(self, symbols):
        self.stdout.write(self.style.HTTP_INFO('--- Existing Data Check ---'))
        for symbol in symbols:
            try:
                ticker = Ticker.objects.get(symbol=symbol)
                data_count = ticker.market_data.count()
                last_update = ticker.last_updated.strftime('%Y-%m-%d %H:%M:%S') if ticker.last_updated else 'Never'
                self.stdout.write(f"{symbol}: {data_count} records, Last update: {last_update}")
            except Ticker.DoesNotExist:
                self.stdout.write(f"{symbol}: No ticker found (will be created)")
        self.stdout.write()


    def show_ingestion_results(self, log, execution_time):
        self.stdout.write(self.style.SUCCESS('--- INGESTION RESULTS ---'))
        self.stdout.write(f"Status: {log.status}")
        self.stdout.write(f"Execution time: {execution_time:.2f} seconds")
        self.stdout.write(f"Records inserted: {log.records_inserted}")
        self.stdout.write(f"Successful symbols: {len(log.symbols_successful)}")
        self.stdout.write(f"Failed symbols: {len(log.symbols_failed)}")
        
        if log.symbols_successful:
            self.stdout.write(f"✓ Success: {', '.join(log.symbols_successful)}")
        if log.symbols_failed:
            self.stdout.write(self.style.ERROR(f"✗ Failed: {', '.join(log.symbols_failed)}"))
        
        if log.error_message:
            self.stdout.write(self.style.ERROR(f"Error: {log.error_message}"))
        self.stdout.write()


    def show_final_statistics(self, symbols):
        self.stdout.write(self.style.SUCCESS('--- FINAL DATA STATISTICS ---'))
        total_records = 0
        
        for symbol in symbols:
            try:
                ticker = Ticker.objects.get(symbol=symbol)
                data_count = ticker.market_data.count()
                total_records += data_count
                
                # Get latest data point
                latest = ticker.market_data.first()
                if latest:
                    price_info = f"Latest: ${latest.close} ({latest.timestamp.strftime('%Y-%m-%d')})"
                else:
                    price_info = "No data"
                    
                # Basic stats
                if data_count > 0:
                    high = ticker.market_data.aggregate(max_high=models.Max('high'))['max_high']
                    low = ticker.market_data.aggregate(min_low=models.Min('low'))['min_low']
                    stats = f"Range: ${low}-${high}"
                else:
                    stats = "No range data"
                
                self.stdout.write(f"{symbol}: {data_count} records | {price_info} | {stats}")
                
            except Ticker.DoesNotExist:
                self.stdout.write(f"{symbol}: Still not available")
        
        self.stdout.write(f"\nTotal market data records: {total_records}")
        self.stdout.write(f"Total tickers: {Ticker.objects.count()}")
        self.stdout.write(f"Total exchanges: {Exchange.objects.count()}")
