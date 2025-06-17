# apps/market_data/management/commands/setup_sample_data.py
"""
Management command to set up sample data for development and testing
Usage:
    python manage.py setup_sample_data
    python manage.py setup_sample_data --full
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.market_data.models import DataSource, Exchange, Sector, Industry, Ticker
from decimal import Decimal


class Command(BaseCommand):
    help = 'Set up sample data for development and testing'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--full',
            action='store_true',
            help='Create comprehensive sample data',
        )
        
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing data before creating new',
        )
    
    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write("Resetting existing data...")
            self._reset_data()
        
        self.stdout.write("Creating sample data...")
        
        # Create data sources
        self._create_data_sources()
        
        # Create exchanges
        self._create_exchanges()
        
        # Create sectors and industries
        self._create_sectors_industries()
        
        # Create sample tickers
        if options['full']:
            self._create_full_sample_tickers()
        else:
            self._create_basic_sample_tickers()
        
        self.stdout.write(
            self.style.SUCCESS('Sample data created successfully!')
        )
        
        # Show summary
        self._show_summary()
    
    def _reset_data(self):
        """Reset all data"""
        Ticker.objects.all().delete()
        Industry.objects.all().delete()
        Sector.objects.all().delete()
        Exchange.objects.all().delete()
        # Don't delete DataSource as it might be recreated by services
    
    def _create_data_sources(self):
        """Create data sources"""
        sources = [
            {
                'name': 'Yahoo Finance',
                'code': 'YFINANCE',
                'url': 'https://finance.yahoo.com',
                'requires_api_key': False,
                'supported_markets': ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'JP', 'HK'],
                'supported_timeframes': ['1m', '5m', '15m', '30m', '1h', '1d', '1wk', '1mo']
            },
            {
                'name': 'Alpha Vantage',
                'code': 'ALPHA_VANTAGE',
                'url': 'https://www.alphavantage.co',
                'api_endpoint': 'https://www.alphavantage.co/query',
                'requires_api_key': True,
                'rate_limit_per_minute': 5,
                'supported_markets': ['US'],
                'supported_timeframes': ['1min', '5min', '15min', '30min', '60min', 'daily']
            }
        ]
        
        for source_data in sources:
            source, created = DataSource.objects.get_or_create(
                code=source_data['code'],
                defaults=source_data
            )
            if created:
                self.stdout.write(f"  Created data source: {source.name}")
    
    def _create_exchanges(self):
        """Create exchanges"""
        exchanges = [
            {'name': 'NASDAQ', 'code': 'NASDAQ', 'country': 'US', 'currency': 'USD', 'timezone': 'America/New_York'},
            {'name': 'New York Stock Exchange', 'code': 'NYSE', 'country': 'US', 'currency': 'USD', 'timezone': 'America/New_York'},
            {'name': 'London Stock Exchange', 'code': 'LSE', 'country': 'GB', 'currency': 'GBP', 'timezone': 'Europe/London'},
            {'name': 'Athens Exchange', 'code': 'ATHEX', 'country': 'GR', 'currency': 'EUR', 'timezone': 'Europe/Athens'},
            {'name': 'Tokyo Stock Exchange', 'code': 'TSE', 'country': 'JP', 'currency': 'JPY', 'timezone': 'Asia/Tokyo'},
            {'name': 'Hong Kong Stock Exchange', 'code': 'HKEX', 'country': 'HK', 'currency': 'HKD', 'timezone': 'Asia/Hong_Kong'},
        ]
        
        for exchange_data in exchanges:
            exchange, created = Exchange.objects.get_or_create(
                code=exchange_data['code'],
                defaults=exchange_data
            )
            if created:
                self.stdout.write(f"  Created exchange: {exchange.name}")
    
    def _create_sectors_industries(self):
        """Create sectors and industries"""
        sectors_industries = {
            'Technology': ['Software', 'Hardware', 'Semiconductors', 'Internet', 'Cybersecurity'],
            'Healthcare': ['Pharmaceuticals', 'Biotechnology', 'Medical Devices', 'Healthcare Services'],
            'Financial': ['Banks', 'Insurance', 'Investment Services', 'Real Estate'],
            'Consumer Discretionary': ['Automotive', 'Retail', 'Media', 'Hotels & Restaurants'],
            'Consumer Staples': ['Food & Beverages', 'Household Products', 'Personal Care'],
            'Energy': ['Oil & Gas', 'Renewable Energy', 'Utilities'],
            'Materials': ['Mining', 'Chemicals', 'Construction Materials'],
            'Industrials': ['Aerospace & Defense', 'Construction', 'Transportation', 'Manufacturing'],
            'Telecommunications': ['Telecom Services', 'Wireless', 'Internet Services'],
            'Real Estate': ['REITs', 'Real Estate Development', 'Real Estate Services']
        }
        
        for sector_name, industries in sectors_industries.items():
            sector, created = Sector.objects.get_or_create(
                name=sector_name,
                defaults={'code': sector_name[:10].upper()}
            )
            if created:
                self.stdout.write(f"  Created sector: {sector_name}")
            
            for industry_name in industries:
                industry, created = Industry.objects.get_or_create(
                    name=industry_name,
                    sector=sector
                )
                if created and created:
                    self.stdout.write(f"    Created industry: {industry_name}")
    
    def _create_basic_sample_tickers(self):
        """Create basic sample tickers"""
        # Get required objects
        nasdaq = Exchange.objects.get(code='NASDAQ')
        nyse = Exchange.objects.get(code='NYSE')
        lse = Exchange.objects.get(code='LSE')
        yfinance_source = DataSource.objects.get(code='YFINANCE')
        
        tech_sector = Sector.objects.get(name='Technology')
        software_industry = Industry.objects.get(name='Software', sector=tech_sector)
        
        tickers = [
            {
                'symbol': 'AAPL',
                'name': 'Apple Inc.',
                'exchange': nasdaq,
                'sector': tech_sector,
                'industry': Industry.objects.get(name='Hardware', sector=tech_sector),
                'market_cap': 3000000000000,
                'description': 'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories.'
            },
            {
                'symbol': 'GOOGL',
                'name': 'Alphabet Inc.',
                'exchange': nasdaq,
                'sector': tech_sector,
                'industry': software_industry,
                'market_cap': 1800000000000,
                'description': 'Alphabet Inc. provides online advertising services in the United States, Europe, the Middle East, Africa, the Asia-Pacific, Canada, and Latin America.'
            },
            {
                'symbol': 'MSFT',
                'name': 'Microsoft Corporation',
                'exchange': nasdaq,
                'sector': tech_sector,
                'industry': software_industry,
                'market_cap': 2800000000000,
                'description': 'Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions worldwide.'
            },
            {
                'symbol': 'TSLA',
                'name': 'Tesla, Inc.',
                'exchange': nasdaq,
                'sector': Sector.objects.get(name='Consumer Discretionary'),
                'industry': Industry.objects.get(name='Automotive'),
                'market_cap': 800000000000,
                'description': 'Tesla, Inc. designs, develops, manufactures, leases, and sells electric vehicles, and energy generation and storage systems.'
            },
            {
                'symbol': 'AMZN',
                'name': 'Amazon.com, Inc.',
                'exchange': nasdaq,
                'sector': Sector.objects.get(name='Consumer Discretionary'),
                'industry': Industry.objects.get(name='Retail'),
                'market_cap': 1500000000000,
                'description': 'Amazon.com, Inc. engages in the retail sale of consumer products and subscriptions in North America and internationally.'
            }
        ]
        
        for ticker_data in tickers:
            ticker, created = Ticker.objects.get_or_create(
                symbol=ticker_data['symbol'],
                exchange=ticker_data['exchange'],
                defaults={
                    **ticker_data,
                    'data_source': yfinance_source,
                    'currency': 'USD',
                    'country': 'US',
                    'yfinance_symbol': ticker_data['symbol'],
                    'last_updated': timezone.now()
                }
            )
            if created:
                self.stdout.write(f"  Created ticker: {ticker.symbol} - {ticker.name}")
    
    def _create_full_sample_tickers(self):
        """Create comprehensive sample tickers"""
        self._create_basic_sample_tickers()
        
        # Add more international and diverse tickers
        # This would include more exchanges, sectors, etc.
        # Implementation would be similar but more extensive
        
        self.stdout.write("  Full sample data creation would be implemented here")
    
    def _show_summary(self):
        """Show summary of created data"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("DATA SUMMARY")
        self.stdout.write("="*50)
        
        self.stdout.write(f"Data Sources: {DataSource.objects.count()}")
        self.stdout.write(f"Exchanges: {Exchange.objects.count()}")
        self.stdout.write(f"Sectors: {Sector.objects.count()}")
        self.stdout.write(f"Industries: {Industry.objects.count()}")
        self.stdout.write(f"Tickers: {Ticker.objects.count()}")
        
        self.stdout.write("\nNext steps:")
        self.stdout.write("1. Run: python manage.py ingest_market_data --symbols AAPL,GOOGL,MSFT --period 1y")
        self.stdout.write("2. Access API docs at: http://localhost:8000/api/docs/")
        self.stdout.write("3. Test endpoints at: http://localhost:8000/api/v1/tickers/")
