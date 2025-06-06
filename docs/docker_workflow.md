# QSuite Development Guide - Complete Docker Workflow

## Table of Contents
1. [Quick Start](#quick-start)
2. [Daily Development Commands](#daily-development-commands)
3. [Database Operations](#database-operations)
4. [Django Management](#django-management)
5. [Celery & Background Tasks](#celery--background-tasks)
6. [Testing & Quality Assurance](#testing--quality-assurance)
7. [Package Management](#package-management)
8. [Debugging & Troubleshooting](#debugging--troubleshooting)
9. [Production Deployment](#production-deployment)
10. [Advanced Development](#advanced-development)

---

## Quick Start

### 🚀 Initial Setup (One-time)
```bash
# Clone and navigate to project
git clone <repository-url>
cd qsuite

# Copy environment template (if needed)
cp .env.example .env

# Build and start all services
docker-compose up --build

# In a new terminal - run migrations
docker-compose exec web python manage.py migrate

# Create superuser for admin access
docker-compose exec web python manage.py createsuperuser

# Access your application
open http://localhost:8000
```

### ✅ Verify Everything Works
```bash
# Check all services are running
docker-compose ps

# Test database connection
docker-compose exec web python manage.py check --database default

# Test Celery task
docker-compose exec web python manage.py shell
>>> from apps.core.tasks import test_task
>>> result = test_task.delay()
>>> result.get()
>>> exit()
```

---

## Daily Development Commands

### 🔄 Starting/Stopping Development

**Start development (most common):**
```bash
# Start all services (web, db, redis, celery)
docker-compose up

# Start in background (detached mode)
docker-compose up -d

# View logs while running detached
docker-compose logs -f
```

**Stop development:**
```bash
# Stop all services (preserves data)
docker-compose down

# Stop and remove volumes (⚠️ DELETES DATABASE DATA)
docker-compose down -v
```

**Restart specific services:**
```bash
# Restart web service only
docker-compose restart web

# Restart web and celery
docker-compose restart web celery
```

### 📊 Monitoring Services

**View logs:**
```bash
# All services logs
docker-compose logs -f

# Specific service logs
docker-compose logs -f web        # Django app
docker-compose logs -f celery     # Background tasks
docker-compose logs -f db         # PostgreSQL
docker-compose logs -f redis      # Redis cache

# Last 50 lines only
docker-compose logs --tail=50 web
```

**Check service status:**
```bash
# List running services
docker-compose ps

# Check resource usage
docker-compose top

# View detailed service info
docker-compose exec web env | grep -E "(DB_|REDIS_|CELERY_)"
```

---

## Database Operations

### 🗄️ Django Migrations

**Creating and applying migrations:**
```bash
# Create migrations after model changes
docker-compose exec web python manage.py makemigrations

# Apply migrations to database
docker-compose exec web python manage.py migrate

# Check migration status
docker-compose exec web python manage.py showmigrations

# Migrate specific app
docker-compose exec web python manage.py migrate market_data
```

**Reset migrations (development only):**
```bash
# Reset specific app migrations
docker-compose exec web python manage.py migrate market_data zero
docker-compose exec web python manage.py migrate market_data

# Reset all migrations (nuclear option)
docker-compose down -v  # Destroys database
docker-compose up -d db redis
docker-compose exec web python manage.py migrate
```

### 🐘 Direct PostgreSQL Access

**Database shell and queries:**
```bash
# Django database shell
docker-compose exec web python manage.py dbshell

# Direct PostgreSQL connection
docker-compose exec db psql -U qsuite_user -d qsuite_dev

# Run SQL commands from host
docker-compose exec db psql -U qsuite_user -d qsuite_dev -c "SELECT COUNT(*) FROM auth_user;"

# View database structure
docker-compose exec db psql -U qsuite_user -d qsuite_dev -c "\dt"
```

**Backup and restore:**
```bash
# Create backup
docker-compose exec db pg_dump -U qsuite_user qsuite_dev > backup_$(date +%Y%m%d).sql

# Restore from backup (database must exist)
cat backup_20241206.sql | docker-compose exec -T db psql -U qsuite_user -d qsuite_dev

# Create compressed backup
docker-compose exec db pg_dump -U qsuite_user -Fc qsuite_dev > backup_$(date +%Y%m%d).dump
```

### 🔄 Database Utilities

**Common database tasks:**
```bash
# Check database size and table counts
docker-compose exec web python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT COUNT(*) FROM auth_user')
print(f'Users: {cursor.fetchone()[0]}')
"

# Load fixtures/sample data
docker-compose exec web python manage.py loaddata fixtures/sample_data.json

# Create data fixtures from current data
docker-compose exec web python manage.py dumpdata --indent=2 market_data > fixtures/market_data.json
```

---

## Django Management

### 🐍 Django Shell & Management Commands

**Interactive shell:**
```bash
# Standard Django shell
docker-compose exec web python manage.py shell

# Shell with auto-imports (if django-extensions installed)
docker-compose exec web python manage.py shell_plus

# Execute Python code directly
docker-compose exec web python manage.py shell -c "
from apps.market_data.models import DataSource
print(f'Data sources: {DataSource.objects.count()}')
"
```

**User management:**
```bash
# Create superuser
docker-compose exec web python manage.py createsuperuser

# Change user password via shell
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='admin')
user.set_password('newpassword123')
user.save()
print('Password updated successfully')
"
```

**Application management:**
```bash
# Create new Django app
docker-compose exec web python manage.py startapp new_app_name

# Check for issues
docker-compose exec web python manage.py check

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Clear cache
docker-compose exec web python manage.py shell -c "
from django.core.cache import cache
cache.clear()
print('Cache cleared')
"
```

### 📋 Model Operations (Market Data Examples)

**Working with your models:**
```bash
# Interactive model exploration
docker-compose exec web python manage.py shell
```

```python
# Market data operations
from apps.market_data.models import DataSource, Ticker, MarketData
from decimal import Decimal
from datetime import datetime, timezone

# Create data source
yahoo, created = DataSource.objects.get_or_create(
    code="YAHOO",
    defaults={
        'name': "Yahoo Finance",
        'url': "https://finance.yahoo.com",
        'is_active': True
    }
)

# Create ticker
aapl = Ticker.objects.create(
    symbol="AAPL",
    name="Apple Inc.",
    currency="USD",
    data_source=yahoo,
    is_active=True
)

# Add market data
MarketData.objects.create(
    ticker=aapl,
    timestamp=datetime.now(timezone.utc),
    open=Decimal('150.00'),
    high=Decimal('155.00'),
    low=Decimal('149.50'),
    close=Decimal('154.25'),
    volume=Decimal('45000000')
)

# Query data
print(f"AAPL records: {aapl.marketdata_set.count()}")
latest = aapl.marketdata_set.latest('timestamp')
print(f"Latest close: ${latest.close}")
```

---

## Celery & Background Tasks

### 🔄 Celery Operations

**Monitor Celery:**
```bash
# View Celery worker logs
docker-compose logs -f celery

# Check Celery worker status
docker-compose exec celery celery -A config inspect active

# View worker statistics
docker-compose exec celery celery -A config inspect stats

# List registered tasks
docker-compose exec celery celery -A config inspect registered
```

**Task management:**
```bash
# Purge all pending tasks
docker-compose exec celery celery -A config purge

# Monitor tasks in real-time (if flower installed)
docker-compose exec celery celery -A config flower

# Execute task manually
docker-compose exec web python manage.py shell -c "
from apps.core.tasks import test_task
result = test_task.delay()
print(f'Task ID: {result.id}')
print(f'Result: {result.get()}')
"
```

**Celery Beat (Scheduled Tasks):**
```bash
# If you add beat service to docker-compose.yml
docker-compose exec beat celery -A config beat --loglevel=info
```

### 📨 Redis Operations

**Redis management:**
```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Check Redis info
docker-compose exec redis redis-cli info

# Monitor Redis commands
docker-compose exec redis redis-cli monitor

# Clear Redis cache
docker-compose exec redis redis-cli flushall

# Check specific keys
docker-compose exec redis redis-cli keys "*celery*"
```

---

## Testing & Quality Assurance

### 🧪 Running Tests

**Django tests:**
```bash
# Run all tests
docker-compose exec web python manage.py test

# Run specific app tests
docker-compose exec web python manage.py test apps.market_data

# Run specific test class
docker-compose exec web python manage.py test apps.market_data.tests.TestMarketDataModel

# Run with pytest (if installed)
docker-compose exec web pytest

# Run with coverage
docker-compose exec web coverage run --source='.' manage.py test
docker-compose exec web coverage report
docker-compose exec web coverage html
```

**Performance testing:**
```bash
# Django shell performance testing
docker-compose exec web python manage.py shell -c "
import time
from apps.market_data.models import MarketData

start = time.time()
count = MarketData.objects.count()
print(f'Query took {time.time() - start:.3f}s for {count} records')
"
```

### 🔍 Code Quality

**Linting and formatting (if tools installed):**
```bash
# Black formatting
docker-compose exec web black .

# Flake8 linting
docker-compose exec web flake8 .

# isort import sorting
docker-compose exec web isort .

# Security check with bandit
docker-compose exec web bandit -r apps/
```

---

## Package Management

### 📦 Adding Dependencies

**Installing new packages:**
```bash
# 1. Add package to requirements/development.txt
echo "django-extensions" >> requirements/development.txt

# 2. Rebuild container with new dependencies
docker-compose build web

# 3. Restart services
docker-compose up --build

# For quick testing (not persistent):
docker-compose exec web pip install django-extensions
```

**Updating requirements:**
```bash
# Generate current pip freeze (temporary container)
docker-compose run --rm web pip freeze > requirements/current.txt

# Compare with existing requirements
diff requirements/development.txt requirements/current.txt
```

### 🛠️ Development Tools

**Installing development tools:**
```bash
# Add to requirements/development.txt:
# django-extensions
# django-debug-toolbar  
# ipython
# pytest-django
# factory-boy

# Rebuild
docker-compose build web

# Verify installation
docker-compose exec web python -c "import django_extensions; print('✅ Extensions installed')"
```

---

## Debugging & Troubleshooting

### 🐛 Common Issues

**Container won't start:**
```bash
# Check logs for errors
docker-compose logs web

# Check if ports are in use
lsof -i :8000
lsof -i :5432

# Rebuild without cache
docker-compose build --no-cache web

# Check Docker system resources
docker system df
docker system prune  # Clean up space
```

**Database connection issues:**
```bash
# Test database connection
docker-compose exec web python manage.py check --database default

# Check database is running
docker-compose exec db pg_isready -U qsuite

# Verify environment variables
docker-compose exec web env | grep DB_

# Test connection manually
docker-compose exec web python -c "
import psycopg2
conn = psycopg2.connect(
    host='db', 
    database='qsuite', 
    user='qsuite', 
    password='qsuite123'
)
print('✅ Database connection successful')
conn.close()
"
```

**Performance issues:**
```bash
# Check container resource usage
docker stats

# Monitor database performance
docker-compose exec db psql -U qsuite_user -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;
"

# Check Redis memory usage
docker-compose exec redis redis-cli info memory
```

### 🔧 Interactive Debugging

**Debugging with pdb:**
```python
# Add to your code where you want to debug:
import pdb; pdb.set_trace()

# Make sure docker-compose.yml has:
# stdin_open: true
# tty: true

# Then run:
docker-compose up
# Debugger will pause when it hits the breakpoint
```

**File system access:**
```bash
# Access container shell
docker-compose exec web bash

# Navigate Django project
cd /app
ls -la
cat manage.py

# Edit files (or use host editor - files sync automatically)
vi apps/market_data/models.py
```

---

## Production Deployment

### 🚀 Production Considerations

**Environment setup:**
```bash
# Create production environment file
cp .env .env.production

# Edit production settings:
# DEBUG=False
# ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
# SECRET_KEY=your-super-secret-production-key
# DB_HOST=your-production-db-host
```

**Production commands:**
```bash
# Use production environment
docker-compose --env-file .env.production up

# Collect static files for production
docker-compose exec web python manage.py collectstatic --noinput

# Create production database backup before deployment
docker-compose exec db pg_dump -U qsuite_user qsuite_dev > pre_deploy_backup.sql
```

**Security checklist:**
```bash
# Run Django security checks
docker-compose exec web python manage.py check --deploy

# Check for security issues
docker-compose exec web python manage.py diffsettings
```

---

## Advanced Development

### 🎯 JPMorgan Requirements Implementation

**Microservices structure:**
```bash
# Create new microservice apps
docker-compose exec web python manage.py startapp execution_engine
docker-compose exec web python manage.py startapp risk_management  
docker-compose exec web python manage.py startapp analytics

# API development
docker-compose exec web python manage.py shell -c "
from rest_framework.test import APIClient
client = APIClient()
response = client.get('/api/v1/market-data/')
print(f'API Status: {response.status_code}')
"
```

**Performance optimization:**
```bash
# Database query optimization
docker-compose exec web python manage.py shell -c "
from django.db import connection
from apps.market_data.models import MarketData

# Enable query logging
connection.queries = []
MarketData.objects.select_related('ticker__data_source').all()[:10]
print(f'Queries executed: {len(connection.queries)}')
for query in connection.queries:
    print(query['sql'][:100])
"

# Redis caching test
docker-compose exec web python manage.py shell -c "
from django.core.cache import cache
cache.set('test_key', 'test_value', 300)
print(f'Cache test: {cache.get(\"test_key\")}')
"
```

### 📊 Data Science Integration

**ML/Analytics pipeline:**
```bash
# Install data science packages (add to requirements):
# pandas>=2.0.0
# numpy>=1.24.0
# scikit-learn>=1.3.0

# Test data science integration
docker-compose exec web python manage.py shell -c "
import pandas as pd
import numpy as np
from apps.market_data.models import MarketData

# Convert Django QuerySet to DataFrame
data = MarketData.objects.values('timestamp', 'close', 'volume')
df = pd.DataFrame(data)
print(f'DataFrame shape: {df.shape}')
print(df.head())
"
```

**Automated backtesting:**
```bash
# Create custom management command for backtesting
docker-compose exec web python manage.py shell -c "
# Example: Create backtesting task
from apps.core.tasks import backtest_strategy
result = backtest_strategy.delay('AAPL', '2024-01-01', '2024-12-31')
print(f'Backtest task ID: {result.id}')
"
```

---

## Environment Variables Reference

**Required `.env` variables:**
```env
# Django Settings
SECRET_KEY=your-50-character-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database Configuration  
DB_NAME=qsuite
DB_USER=qsuite
DB_PASSWORD=qsuite123
DB_HOST=db
DB_PORT=5432

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# External APIs (if needed)
ALPHA_VANTAGE_API_KEY=your-api-key
YAHOO_FINANCE_API_KEY=your-api-key
```

---

## Quick Command Reference

**Most Used Commands:**
```bash
# Start development
docker-compose up

# Stop development  
docker-compose down

# View logs
docker-compose logs -f web

# Django shell
docker-compose exec web python manage.py shell

# Run migrations
docker-compose exec web python manage.py migrate

# Run tests
docker-compose exec web python manage.py test

# Database shell
docker-compose exec web python manage.py dbshell

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Rebuild after requirements change
docker-compose build web && docker-compose up --build
```

**Emergency Commands:**
```bash
# Nuclear reset (destroys all data)
docker-compose down -v
docker system prune -a
docker-compose up --build

# Clean rebuild
docker-compose build --no-cache
docker-compose up --build

# Check space usage
docker system df

# Clean up space
docker system prune -a
```

---

This guide covers all regular development workflows for your QSuite Django project. Bookmark this for daily reference and update it as your project evolves!
