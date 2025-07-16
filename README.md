# QSuite - Quantitative Finance Platform

QSuite is a Django-based platform for quantitative finance analysis and algorithmic trading. It provides:

- Market data storage and processing
- REST API for data access
- Real-time trading simulation
- Quantitative analysis tools
- GPU-accelerated computations (macOS supported via Metal)
- Risk management and compliance monitoring
- Trading performance analytics

## Project Structure

```
qsuite/
├── apps/
│   ├── accounts/          # Custom user management and authentication
│   ├── core/              # Shared functionality and utilities
│   ├── market_data/       # Financial data models and API
│   ├── order_management/  # Algorithmic order execution
│   ├── risk_management/   # Risk assessment and compliance
│   ├── trading_analytics/ # Performance reporting and metrics
│   └── trading_simulation/ # Real-time trading simulation
├── config/                # Django project configuration
├── docs/                  # Project documentation
├── logs/                  # Application logs
├── media/                 # User-uploaded files
├── requirements/          # Dependency management
├── scripts/               # Utility scripts
├── static/                # Static files
└── tests/                 # Comprehensive test suite
```

## Key Components

### Models
- **accounts.User**: Custom user model with financial permissions
- **market_data.DataSource**: Market data providers (exchanges, APIs)
- **market_data.Ticker**: Financial instruments
- **market_data.MarketData**: Time-series OHLCV data
- **order_management.AlgorithmicOrder**: Algorithm-generated orders
- **risk_management.RiskProfile**: User risk tolerance profiles
- **trading_analytics.PerformanceMetric**: Trading performance metrics
- **trading_simulation.Simulation**: Trading simulation scenarios

### Services
- **FinancialDataService**: Data normalization, volatility calculations
- **ComputationService**: GPU-accelerated matrix operations
- **RiskAssessmentService**: Real-time risk monitoring
- **SimulationService**: Trading scenario simulation
- **OrderExecutionService**: Algorithmic order processing

### API Endpoints
- `/api/accounts/` - User authentication and management
- `/api/market-data/` - Market data access
- `/api/orders/` - Order management
- `/api/risk/` - Risk management
- `/api/analytics/` - Trading performance
- `/api/simulation/` - Trading simulation

## Development Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 17+
- Redis 7+
- Docker (optional)

### Installation (Traditional)
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

### Installation (Docker)
```bash
docker-compose up --build
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
REDIS_URL=redis://localhost:6379

# Optional
USE_GPU=True  # Enable Metal acceleration on macOS
```

## Development Workflow

### Running the Server
```bash
python manage.py runserver
```

### Running Celery Worker
```bash
celery -A config worker -l info
```

### Testing
```bash
python manage.py test
```

### API Documentation
Browseable API available at `http://localhost:8000/api/`

### Real-time WebSocket Endpoint
`ws://localhost:8000/ws/simulation/` - For trading simulation updates

## Working with Market Data

### Fetching Data
```python
from apps.market_data.services import MarketDataService
data = MarketDataService.get_historical_data('AAPL', '2024-01-01', '2024-12-31')
```

### Calculating Technical Indicators
```python
from apps.market_data.technical_analysis import calculate_rsi
rsi = calculate_rsi(data['close'], period=14)
```

### Running a Trading Simulation
```python
from apps.trading_simulation.services import SimulationService
simulation = SimulationService.run_simulation(
    strategy='mean_reversion',
    symbols=['AAPL', 'MSFT'],
    start_date='2025-01-01',
    end_date='2025-03-31',
    capital=100000
)
```

## Extending the System

### Adding New Data Sources
1. Create a new DataSource record
2. Implement fetcher in `market_data/services.py`
3. Add API endpoint in `market_data/views.py`

### Creating New Trading Strategies
1. Add strategy implementation in `order_management/algorithm_services.py`
2. Create serializer in `order_management/algorithm_serializers.py`
3. Add API endpoint in `order_management/algorithm_views.py`

### Adding Risk Management Rules
1. Create new model in `risk_management/models.py`
2. Implement rule checking in `risk_management/services.py`
3. Add API endpoint in `risk_management/views.py`

## Deployment Considerations

- Use PostgreSQL connection pooling
- Configure proper CORS settings
- Set up Celery for async tasks with Redis backend
- Implement monitoring for quantitative workloads
- Use production-ready WebSocket server (Daphne or similar)
- Set up log rotation for application logs

## Performance Tips

- Use `select_related` and `prefetch_related` for API queries
- Utilize materialized views for common aggregations
- Implement caching for frequently accessed data
- Offload computationally intensive tasks to Celery
- Use GPU acceleration for technical indicator calculations

## Testing
The project includes comprehensive tests:
- Unit tests for models and services
- Integration tests for API endpoints
- WebSocket communication tests
- Celery task tests

Run all tests with:
```bash
python manage.py test
```

## Documentation
Additional documentation is available in the `docs/` directory:
- `api_notes.md` - API design and implementation details
- `docker_workflow.md` - Docker setup and deployment
- `real-time_data_feeds_and_websocket_implementation.md` - Real-time data architecture
- `regulatory_requirements_notes.md` - Compliance considerations

## License
Proprietary - © 2025 QSuite Technologies
