# PostgreSQL 17 Setup for QSuite

This comprehensive guide covers PostgreSQL 17 installation, database management, user administration, and Django integration for the QSuite quantitative finance application.

## Installation (macOS)

### 1. Install PostgreSQL 17
```bash
# Install PostgreSQL 17 (latest stable version)
brew install postgresql@17
```

### 2. Start PostgreSQL Service
```bash
brew services start postgresql@17
```

### 3. Add PostgreSQL to PATH
```bash
# For Apple Silicon Macs (M1/M2/M3)
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc

# For Intel Macs
echo 'export PATH="/usr/local/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc

# Apply changes
source ~/.zshrc
```

### 4. Clean Up Old Versions
After confirming PostgreSQL 17 works perfectly:
```bash
# Remove old versions to save space
brew services stop postgresql@16
brew uninstall postgresql@16
```

# Clean up leftover files
brew cleanup --prune-prefix

### 4. Verify Installation
```bash
# Check PostgreSQL version
psql --version  # Should show PostgreSQL 17.x

# Check if PostgreSQL is running
brew services list | grep postgresql
```

## Database and User Setup

### Understanding PostgreSQL Connection Types

| Command | Database | User | Use Case |
|---------|----------|------|----------|
| `psql postgres` | postgres | system user | Administrative tasks |
| `psql qsuite_dev` | qsuite_dev | system user | Full database access |
| `psql qsuite_dev -U qsuite_user` | qsuite_dev | qsuite_user | Django app access |

### 1. Create Database User
```bash
# Connect as admin
psql postgres
```

```sql
-- Create dedicated user for Django app
CREATE USER qsuite_user WITH PASSWORD 'your_secure_password';

-- Check users were created
\du

-- Exit
\q
```

### 2. Create Development Database
```bash
# Connect as admin to create database
psql postgres
```

```sql
-- Create the database with qsuite_user as owner (PostgreSQL 17 best practice)
CREATE DATABASE qsuite_dev OWNER qsuite_user;

-- Connect to the new database
\c qsuite_dev

-- Grant schema permissions (REQUIRED for PostgreSQL 15+)
-- This fixes the "permission denied for schema public" error
GRANT USAGE ON SCHEMA public TO qsuite_user;
GRANT CREATE ON SCHEMA public TO qsuite_user;
GRANT ALL ON SCHEMA public TO qsuite_user;

-- Grant default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO qsuite_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO qsuite_user;

-- Exit
\q
```

### 3. Verify Database Creation
```bash
# List all databases
psql postgres -c "\l"

# Test connection as Django user
psql qsuite_dev -U qsuite_user -c "SELECT current_database(), current_user;"
```

## Django Configuration

### 1. Install PostgreSQL Adapter
```bash
# Activate your virtual environment first
source venv/bin/activate

# Install the PostgreSQL adapter
pip install psycopg2-binary
```

### 2. Configure Environment Variables
Create or update your `.env` file:
```env
# Database Configuration
DB_NAME=qsuite_dev
DB_USER=qsuite_user
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# Performance settings for quantitative workloads
DB_CONN_MAX_AGE=600
DB_OPTIONS={"options": "-c default_transaction_isolation=read_committed"}

# Django Secret Key
SECRET_KEY=your_50_character_secret_key_here
```

### 3. Apply Django Migrations
```bash
# Create all Django tables from your models
python manage.py migrate

# Verify tables were created
psql qsuite_dev -c "\dt"

# Create Django superuser
python manage.py createsuperuser
```

## Database Management Commands

### Connection Commands
```bash
# Connect to postgres database for admin tasks
psql postgres

# Connect to your app database as owner
psql qsuite_dev

# Connect to your app database as Django user
psql qsuite_dev -U qsuite_user

# Connect and run single command
psql qsuite_dev -c "SELECT COUNT(*) FROM market_data_marketdata;"
```

### Database Operations
```bash
# List all databases
psql postgres -c "\l"

# Create database with specific owner
psql postgres -c "CREATE DATABASE new_db_name OWNER qsuite_user;"

# Drop database (CAUTION: Irreversible!)
psql postgres -c "DROP DATABASE database_name;"

# Rename database
psql postgres -c "ALTER DATABASE old_name RENAME TO new_name;"
```

### User Management
```bash
# List all users and their roles
psql postgres -c "\du"

# Create user with specific permissions
psql postgres -c "CREATE USER username WITH PASSWORD 'password';"

# Grant database access
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE qsuite_dev TO username;"

# Change user password
psql postgres -c "ALTER USER username WITH PASSWORD 'new_password';"

# Drop user
psql postgres -c "DROP USER username;"
```

### Table and Data Operations
```bash
# List tables in current database
psql qsuite_dev -c "\dt"

# Show table structure
psql qsuite_dev -c "\d table_name"

# Show table data with details
psql qsuite_dev -c "\dt+"

# Count records in all main tables
psql qsuite_dev -c "
SELECT 'DataSources' as table_name, COUNT(*) as records FROM market_data_datasource
UNION ALL
SELECT 'Tickers', COUNT(*) FROM market_data_ticker  
UNION ALL
SELECT 'MarketData', COUNT(*) FROM market_data_marketdata
UNION ALL
SELECT 'Users', COUNT(*) FROM quant_users;"
```

## Backup and Restore

### Database Backup
```bash
# Full database backup
pg_dump qsuite_dev > qsuite_backup_$(date +%Y%m%d).sql

# Schema-only backup (structure without data)
pg_dump -s qsuite_dev > qsuite_schema_$(date +%Y%m%d).sql

# Data-only backup
pg_dump -a qsuite_dev > qsuite_data_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -Fc qsuite_dev > qsuite_backup_$(date +%Y%m%d).dump
```

### Database Restore
```bash
# Restore from SQL file (database must exist)
psql qsuite_dev < qsuite_backup.sql

# Restore from compressed backup
pg_restore -d qsuite_dev qsuite_backup.dump

# Restore to a new database
createdb qsuite_restored
psql qsuite_restored < qsuite_backup.sql
```

## Database Reset (Development)

### Clean Slate Approach
```bash
# 1. Backup current data (optional)
pg_dump qsuite_dev > backup_before_reset.sql

# 2. Drop and recreate database with proper permissions
psql postgres -c "DROP DATABASE IF EXISTS qsuite_dev;"
psql postgres -c "CREATE DATABASE qsuite_dev OWNER qsuite_user;"

# 3. Grant schema permissions (PostgreSQL 17 requirement)
psql qsuite_dev -c "
GRANT USAGE ON SCHEMA public TO qsuite_user;
GRANT CREATE ON SCHEMA public TO qsuite_user;
GRANT ALL ON SCHEMA public TO qsuite_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO qsuite_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO qsuite_user;"

# 4. Recreate Django tables
python manage.py migrate

# 5. Create new superuser
python manage.py createsuperuser
```

### Selective Table Reset
```bash
# Reset specific Django app tables (CAUTION: Data loss!)
python manage.py migrate market_data zero  # Remove all market_data tables
python manage.py migrate market_data       # Recreate them
```

## Common PostgreSQL psql Commands

### Inside psql Session
```sql
-- Database and connection info
\l                          -- List databases
\c database_name            -- Connect to database
\conninfo                   -- Show connection info
SELECT current_database();  -- Show current database

-- Tables and schema
\dt                         -- List tables
\dt+                        -- List tables with sizes
\d table_name              -- Describe table structure
\di                         -- List indexes
\du                         -- List users/roles

-- Schema permissions (useful for debugging)
\dn+                        -- List schemas with permissions
SELECT * FROM information_schema.schema_privileges WHERE grantee = 'qsuite_user';

-- Queries and data
\x                          -- Toggle expanded display
SELECT version();           -- Show PostgreSQL version
\timing                     -- Toggle query timing

-- Exit
\q                          -- Quit psql
```

## Troubleshooting

### PostgreSQL 17 Permission Issues

**Problem**: `permission denied for schema public` error during Django migrations.

**Solution**: PostgreSQL 15+ changed default permissions for security. Grant explicit schema permissions:

```bash
psql postgres
```

```sql
\c qsuite_dev
GRANT USAGE ON SCHEMA public TO qsuite_user;
GRANT CREATE ON SCHEMA public TO qsuite_user;
GRANT ALL ON SCHEMA public TO qsuite_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO qsuite_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO qsuite_user;
\q
```

### Connection Issues
```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL if stopped
brew services start postgresql@17

# Check PostgreSQL logs
tail -f /usr/local/var/log/postgresql@17.log  # Intel Mac
tail -f /opt/homebrew/var/log/postgresql@17.log  # Apple Silicon Mac
```

### Django Connection Issues
```bash
# Test Django database connection
python manage.py check --database default

# Test with Django shell
python manage.py dbshell

# Verify environment variables are loaded
python -c "from decouple import config; print('DB_NAME:', config('DB_NAME'))"
```

### Permission Debugging
```bash
# Check current user permissions on schema
psql qsuite_dev -c "
SELECT schema_name, schema_owner 
FROM information_schema.schemata 
WHERE schema_name = 'public';"

# Check specific user privileges
psql qsuite_dev -c "
SELECT grantee, privilege_type 
FROM information_schema.schema_privileges 
WHERE schema_name = 'public' AND grantee = 'qsuite_user';"
```

## Working with Market Data Models

### Basic Model Operations
```python
# In Django shell: python manage.py shell
from apps.market_data.models import DataSource, Ticker, MarketData

# Check existing data sources
print("Existing data sources:")
for source in DataSource.objects.all():
    print(f"- {source.name} ({source.code})")

# Get app label
print(f"App label: {DataSource._meta.app_label}")
```

### Create Data Source
```python
# Create new data source
yahoo_source = DataSource.objects.create(
    name="Yahoo Finance",
    code="YAHOO",
    url="https://finance.yahoo.com",
    is_active=True
)
print(f"Created: {yahoo_source}")

# Alternative: get_or_create (prevents duplicates)
yahoo_source, created = DataSource.objects.get_or_create(
    code="YAHOO",
    defaults={
        'name': "Yahoo Finance",
        'url': "https://finance.yahoo.com",
        'is_active': True
    }
)
print(f"{'Created' if created else 'Found existing'}: {yahoo_source}")
```

### Query Data Sources
```python
# Get specific data source
try:
    yahoo_source = DataSource.objects.get(code="YAHOO")
    print(f"Found existing source: {yahoo_source}")
except DataSource.DoesNotExist:
    print("No source with code 'YAHOO' found.")

# Filter active sources
active_sources = DataSource.objects.filter(is_active=True)
print(f"Active sources: {active_sources.count()}")
```

### Update Data Sources
```python
# Update existing source
yahoo_source = DataSource.objects.get(code="YAHOO")
yahoo_source.name = "Yahoo Finance (Updated)"
yahoo_source.save()
print(f"Updated: {yahoo_source}")

# Bulk update
DataSource.objects.filter(code="YAHOO").update(
    name="Yahoo Finance API",
    url="https://query1.finance.yahoo.com"
)
```

### Complete Market Data Example
```python
from datetime import date, datetime, time, timezone, timedelta
from decimal import Decimal
import random

# First create a data source (required for ticker)
yahoo_source, created = DataSource.objects.get_or_create(
    code="YAHOO",
    defaults={
        'name': "Yahoo Finance",
        'url': "https://finance.yahoo.com",
        'is_active': True
    }
)

# Create ticker with all available fields
apple_ticker = Ticker.objects.create(
    symbol="AAPL",
    name="Apple Inc.",
    description="Technology company specializing in consumer electronics, software, and online services",
    currency="USD",
    data_source=yahoo_source,  # Required foreign key
    is_active=True
)

# Add single market data record with all available fields
MarketData.objects.create(
    ticker=apple_ticker,                                                # Required foreign key
    timestamp=datetime(2024, 1, 15, 21, 0, 0, tzinfo=timezone.utc),   # Market close (4 PM EST = 9 PM UTC)
    open=Decimal('185.50'),                                             # Opening price (numeric 20,6)
    high=Decimal('188.20'),                                             # Day's high price
    low=Decimal('184.30'),                                              # Day's low price
    close=Decimal('187.45'),                                            # Closing price
    volume=Decimal('45000000.00'),                                      # Trading volume (numeric 20,2)
    adjusted_close=Decimal('186.89'),                                   # Adjusted for splits/dividends (nullable)
    is_active=True                                                      # Active flag (inherited from BaseModel)
    # Note: created_at and updated_at are auto-populated by Django
)

# Create multiple days of realistic market data
base_date = date(2024, 1, 15)
base_price = Decimal('185.50')

for i in range(5):  # 5 trading days
    current_date = base_date + timedelta(days=i)
    
    # Skip weekends (simple approach)
    if current_date.weekday() >= 5:
        continue
    
    # Generate realistic OHLC data following market patterns
    daily_change = Decimal(str(random.uniform(-0.05, 0.05)))          # ±5% daily change
    volatility = abs(daily_change) + Decimal(str(random.uniform(0.01, 0.03)))
    
    # Calculate OHLC prices
    open_price = base_price * (1 + Decimal(str(random.uniform(-0.02, 0.02))))
    close_price = base_price * (1 + daily_change)
    
    # High and low must respect OHLC relationships
    high_price = max(open_price, close_price) * (1 + volatility)
    low_price = min(open_price, close_price) * (1 - volatility)
    
    # Adjusted close (typically very close to close, accounts for corporate actions)
    adjusted_close = close_price * Decimal(str(random.uniform(0.995, 1.005)))
    
    # Create the market data record
    MarketData.objects.create(
        ticker=apple_ticker,
        timestamp=datetime.combine(current_date, time(21, 0), tzinfo=timezone.utc),  # 4 PM EST
        open=open_price.quantize(Decimal('0.000001')),               # 6 decimal places
        high=high_price.quantize(Decimal('0.000001')),
        low=low_price.quantize(Decimal('0.000001')),
        close=close_price.quantize(Decimal('0.000001')),
        volume=Decimal(str(random.randint(30_000_000, 80_000_000))), # Volume in shares
        adjusted_close=adjusted_close.quantize(Decimal('0.000001')),
        is_active=True
    )
    
    # Use current close as base for next day
    base_price = close_price

# Query and display the data
print(f"Market data records for {apple_ticker.symbol}: {apple_ticker.marketdata_set.count()}")

# Show recent data with all fields
recent_data = apple_ticker.marketdata_set.all().order_by('-timestamp')[:5]
for data in recent_data:
    print(f"{data.timestamp.strftime('%Y-%m-%d %H:%M %Z')}: "
          f"O=${data.open} H=${data.high} L=${data.low} C=${data.close} "
          f"V={data.volume:,.0f} AC=${data.adjusted_close}")

# Demonstrate relationship queries
print(f"\nData source: {apple_ticker.data_source.name} ({apple_ticker.data_source.code})")
print(f"Currency: {apple_ticker.currency}")
print(f"Latest close: ${apple_ticker.marketdata_set.latest('timestamp').close}")
```

## Performance Tips

### Database Optimization
```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('qsuite_dev'));

-- Monitor table sizes
SELECT 
    schemaname,
