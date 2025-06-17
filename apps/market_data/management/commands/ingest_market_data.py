# apps/market_data/management/commands/ingest_market_data.py
"""
Management command for ingesting market data from external sources
Usage:
    python manage.py ingest_market_data --symbols AAPL,GOOGL,MSFT --source yfinance
    python manage.py ingest_market_data --preset sp500_tech --period 1y
    python manage.py ingest_market_data --symbols AAPL --source alpha_vantage --fundamentals
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.market_data.services import DataIngestionService, YFinanceService, AlphaVantageService
from apps.market_data.models import DataIngestionLog, Ticker
import time


class Command(BaseCommand):
    help = 'Ingest market data from external sources (yfinance, Alpha Vantage)'
    
    def add_arguments(self, parser):
        # Symbol specification
        parser.add_argument(
            '--symbols',
            type=str,
            help='Comma-separated list of symbols (e.g., AAPL,GOOGL,MSFT)',
        )
        
        parser.add_argument(
            '--preset',
            type=str,
            choices=['sp500_tech', 'dow_jones', 'global_indices', 'crypto_major', 'uk_ftse100'],
            help='Use predefined symbol sets',
        )
        
        # Data source
        parser.add_argument(
            '--source',
            type=str,
            choices=['yfinance', 'alpha_vantage'],
            default='yfinance',
            help='Data source to use (default: yfinance)',
        )
        
        # Time period
        parser.add_argument(
            '--period',
            type=str,
            default='1y',
            help='Period to fetch (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)',
        )
        
        parser.add_argument(
            '--interval',
            type=str,
            default='1d',
            help='Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)',
        )
        
        # Additional options
        parser.add_argument(
            '--fundamentals',
            action='store_true',
            help='Also fetch fundamental data (Alpha Vantage only)',
        )
        
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing ticker information',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output',
        )
    
    def handle(self, *args, **options):
        start_time = time.time()
        
        # Determine symbols to process
        symbols = self._get_symbols(options)
        if not symbols:
            raise CommandError('No symbols specified. Use --symbols or --preset')
        
        self.stdout.write(f"Processing {len(symbols)} symbols: {', '.join(symbols)}")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be modified'))
            self._show_plan(symbols, options)
            return
        
        # Initialize services
        ingestion_service = DataIngestionService()
        
        # Run ingestion
        self.stdout.write(f"Starting data ingestion from {options['source']}...")
        
        try:
            log = ingestion_service.ingest_market_data(
                symbols=symbols,
                data_source=options['source'],
                period=options['period'],
                interval=options['interval']
            )
            
            # Show results
            self._show_results(log, options)
            
            # Handle fundamentals if requested
            if options['fundamentals'] and options['source'] == 'alpha_vantage':
                self.stdout.write("Fetching fundamental data...")
                self._fetch_fundamentals(symbols, options)
            
        except Exception as e:
            raise CommandError(f'Ingestion failed: {str(e)}')
        
        total_time = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(f'Command completed in {total_time:.2f} seconds')
        )
    
    def _get_symbols(self, options):
        """Get list of symbols to process"""
        if options['symbols']:
            return [s.strip().upper() for s in options['symbols'].split(',')]
        
        elif options['preset']:
            return self._get_preset_symbols(options['preset'])
        
        return []
    
    def _get_preset_symbols(self, preset):
        """Get predefined symbol sets"""
        presets = {
            'sp500_tech': [
                'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'META', 'NVDA',
                'NFLX', 'CRM', 'ORCL', 'ADBE', 'INTC', 'AMD', 'PYPL', 'UBER',
                'ZOOM', 'DOCU', 'SHOP', 'SQ'
            ],
            'dow_jones': [
                'AAPL', 'MSFT', 'UNH', 'GS', 'HD', 'CAT', 'MCD', 'V', 'BA',
                'AXP', 'JPM', 'IBM', 'JNJ', 'WMT', 'PG', 'CVX', 'MRK', 'DIS',
                'KO', 'MMM', 'CSCO', 'NKE', 'HON', 'CRM', 'INTC', 'VZ', 'WBA',
                'AMGN', 'TRV', 'DOW'
            ],
            'global_indices': [
                '^GSPC',  # S&P 500
                '^DJI',   # Dow Jones
                '^IXIC',  # NASDAQ
                '^RUT',   # Russell 2000
                '^FTSE',  # FTSE 100
                '^GDAXI', # DAX
                '^FCHI',  # CAC 40
                '^N225',  # Nikkei 225
                '^HSI',   # Hang Seng
                '^BVSP',  # Bovespa
            ],
            'crypto_major': [
                'BTC-USD', 'ETH-USD', 'BNB-USD', 'ADA-USD', 'XRP-USD',
                'SOL-USD', 'DOT-USD', 'DOGE-USD', 'AVAX-USD', 'LUNA-USD'
            ],
            'uk_ftse100': [
                'AZN.L', 'SHEL.L', 'LSEG.L', 'UU.L', 'ULVR.L', 'BP.L',
                'GSK.L', 'DGE.L', 'VOD.L', 'RIO.L', 'BT-A.L', 'TSCO.L',
                'LLOY.L', 'NWG.L', 'BARC.L'
            ]
        }
        
        return presets.get(preset, [])
    
    def _show_plan(self, symbols, options):
        """Show execution plan for dry run"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("EXECUTION PLAN")
        self.stdout.write("="*60)
        
        self.stdout.write(f"Symbols: {len(symbols)}")
        for i, symbol in enumerate(symbols):
            self.stdout.write(f"  {i+1:2d}. {symbol}")
        
        self.stdout.write(f"\nData Source: {options['source']}")
        self.stdout.write(f"Period: {options['period']}")
        self.stdout.write(f"Interval: {options['interval']}")
        
        if options['fundamentals']:
            self.stdout.write("Fundamentals: Yes")
        
        if options['update_existing']:
            self.stdout.write("Update Existing: Yes")
        
        # Check existing data
        existing_symbols = []
        for symbol in symbols:
            if Ticker.objects.filter(symbol=symbol).exists():
                existing_symbols.append(symbol)
        
        if existing_symbols:
            self.stdout.write(f"\nExisting tickers ({len(existing_symbols)}):")
            for symbol in existing_symbols:
                ticker = Ticker.objects.get(symbol=symbol)
                data_count = ticker.market_data.count()
                self.stdout.write(f"  - {symbol}: {data_count} data points")
    
    def _show_results(self, log, options):
        """Display ingestion results"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("INGESTION RESULTS")
        self.stdout.write("="*60)
        
        self.stdout.write(f"Status: {log.status}")
        self.stdout.write(f"Execution Time: {log.execution_time_seconds:.2f} seconds")
        self.stdout.write(f"Records Inserted: {log.records_inserted:,}")
        
        if log.symbols_successful:
            self.stdout.write(f"\nSuccessful ({len(log.symbols_successful)}):")
            for symbol in log.symbols_successful:
                self.stdout.write(f"  ✓ {symbol}")
        
        if log.symbols_failed:
            self.stdout.write(f"\nFailed ({len(log.symbols_failed)}):")
            for symbol in log.symbols_failed:
                self.stdout.write(f"  ✗ {symbol}")
        
        if log.error_message:
            self.stdout.write(f"\nErrors:")
            self.stdout.write(self.style.ERROR(log.error_message))
        
        # Performance metrics
        if log.execution_time_seconds and log.records_inserted > 0:
            records_per_second = log.records_inserted / float(log.execution_time_seconds)
            self.stdout.write(f"\nPerformance: {records_per_second:.1f} records/second")
    
    def _fetch_fundamentals(self, symbols, options):
        """Fetch fundamental data using Alpha Vantage"""
        alpha_vantage = AlphaVantageService()
        
        for i, symbol in enumerate(symbols):
            self.stdout.write(f"Fetching fundamentals for {symbol} ({i+1}/{len(symbols)})")
            
            try:
                overview = alpha_vantage.fetch_company_overview(symbol)
                if overview:
                    # Here you would save the fundamental data
                    # For now, just show a summary
                    if options['verbose']:
                        self.stdout.write(f"  - Market Cap: {overview.get('market_cap', 'N/A')}")
                        self.stdout.write(f"  - P/E Ratio: {overview.get('pe_ratio', 'N/A')}")
                        self.stdout.write(f"  - Sector: {overview.get('sector', 'N/A')}")
                else:
                    self.stdout.write(f"  ✗ No fundamental data for {symbol}")
                
                # Rate limiting for Alpha Vantage
                if i < len(symbols) - 1:  # Don't sleep on last iteration
                    time.sleep(12)  # 5 calls per minute limit
                    
            except Exception as e:
                self.stdout.write(f"  ✗ Error fetching {symbol}: {str(e)}")
