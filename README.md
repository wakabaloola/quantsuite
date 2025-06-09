# QSuite - Quantitative Finance Platform

This `README.md` is currently under construction. A lot of the developments already implemented and in the pipeline are explained more fully in the `docs` directory.

## Project Overview
QSuite is a Django-based platform for quantitative finance analysis and algorithmic trading. It provides:

- Market data storage and processing
- REST API for data access
- Quantitative analysis tools
- GPU-accelerated computations (macOS supported via Metal)

## Project Structure

```
qsuite/
├── apps/
│   ├── accounts/          # Custom user management
│   ├── core/             # Shared functionality
│   └── market_data/       # Financial data models and API
├── config/               # Django project config
├── requirements/         # Dependency management
├── static/               # Static files
└── media/                # User-uploaded files
```

## Key Components

### Models
- **accounts.User**: Custom user model with financial permissions
- **market_data.DataSource**: Market data providers (exchanges, APIs)
- **market_data.Ticker**: Financial instruments
- **market_data.MarketData**: Time-series OHLCV data

### Services
- **FinancialDataService**: Data normalization, volatility calculations
- **ComputationService**: GPU-accelerated matrix operations

### API Endpoints
- `/api/market-data/sources/` - Data sources management
- `/api/market-data/tickers/` - Financial instruments
- `/api/market-data/prices/` - Historical price data

## Development Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 17+
- Redis (for future Celery integration)

### Installation
1. Clone the repository
2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements/base.txt
   pip install -r requirements/development.txt
   ```
4. Set up PostgreSQL (see Database Configuration below)
5. Create `.env` file from `.env.example`
6. Run migrations:
   ```bash
   python manage.py migrate
   ```

### Database Configuration
Configure PostgreSQL with:
```bash
createdb qsuite_dev
psql qsuite_dev -c "CREATE USER qsuite_user WITH PASSWORD 'your_password';"
psql qsuite_dev -c "GRANT ALL PRIVILEGES ON DATABASE qsuite_dev TO qsuite_user;"
psql qsuite_dev -c "ALTER USER qsuite_user WITH SUPERUSER;"
```

### Environment Variables
Required in `.env`:
```ini
SECRET_KEY=your-secret-key
DB_NAME=qsuite_dev
DB_USER=qsuite_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Optional
USE_GPU=True  # Enable Metal acceleration on macOS
```

## Development Workflow

### Running the Server
```bash
python manage.py runserver
```

### Testing
```bash
python manage.py test
```

### API Documentation
Browseable API available at `http://localhost:8000/api/`

### Working with Market Data

#### Fetching Data
```python
from apps.market_data.services import MarketDataService
data = MarketDataService.get_historical_data('AAPL', '2024-01-01', '2024-12-31')
```

#### Calculating Volatility
```python
from apps.core.services import FinancialDataService
volatility = FinancialDataService.calculate_volatility(data['close'])
```

## Extending the System

### Adding New Data Sources
1. Create a new DataSource record
2. Implement fetcher in `market_data/services.py`
3. Add API endpoint if needed

### Creating New Analysis Tools
1. Add methods to `FinancialDataService`
2. Consider GPU acceleration via `ComputationService`

### Adding New Models
1. Create model in appropriate app
2. Add serializers and views
3. Create and run migrations

## Deployment Considerations

- Use PostgreSQL connection pooling
- Configure proper CORS settings
- Set up Celery for async tasks
- Implement proper monitoring for quantitative workloads

## Performance Tips

- Use `select_related` and `prefetch_related` for API queries
- Consider materialized views for common aggregations
- Utilize GPU acceleration for matrix operations
- Implement caching for frequently accessed data

## License
Proprietary - © 2025 QSuite Technologies
