# Makefile for QSuite Docker Testing

.PHONY: help test test-all test-unit test-integration test-performance test-api

help:
	@echo "🐳 QSuite Docker Test Commands"
	@echo "=============================="
	@echo "make test           - Run the COMPLETE test suite for all apps"
	@echo "make test-unit      - Run specific unit tests"
	@echo "make test-integration - Run dashboard integration tests"
	@echo "make test-performance - Run performance tests only"
	@echo "make test-api       - Run API tests only"
	@echo "make test-quick     - Run quick smoke tests"
	@echo "make setup-test     - Setup test environment"
	@echo "make clean-test     - Clean test environment"

# Comprehensive test suite - This now runs ALL tests Django can find.
test:
	@echo "🚀 Running comprehensive test suite for all apps..."
	docker-compose exec web python manage.py test --keepdb

test-all: test

# Unit tests
test-unit:
	@echo "🔬 Running unit tests..."
	docker-compose exec web python manage.py test apps.core.tests.test_websocket_manager --keepdb
	docker-compose exec web python manage.py test apps.trading_analytics.tests.test_portfolio_analytics --keepdb
	docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_service --keepdb
	docker-compose exec web python manage.py test apps.trading_simulation.tests.test_dashboard_consumer --keepdb

# Integration tests
test-integration:
	@echo "🔗 Running integration tests..."
	docker-compose exec web python manage.py test tests.integration.test_dashboard_integration --keepdb

# Performance tests
test-performance:
	@echo "⚡ Running performance tests..."
	docker-compose exec web python manage.py test tests.integration.test_performance --keepdb

# API tests
test-api:
	@echo "🌐 Running API tests..."
	docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_api --keepdb

# Quick smoke tests
test-quick:
	@echo "💨 Running quick smoke tests..."
	docker-compose exec web python manage.py test apps.core.tests.test_websocket_manager.TestConnectionManager.test_connection_manager_initialization --keepdb
	docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_service.TestDashboardService.test_service_initialization --keepdb

# Setup test environment
setup-test:
	@echo "🔧 Setting up test environment..."
	docker-compose exec web python manage.py migrate --run-syncdb
	docker-compose exec web python manage.py collectstatic --noinput
	@echo "✅ Test environment ready"

# Clean test environment
clean-test:
	@echo "🧹 Cleaning test environment..."
	docker-compose exec web python manage.py flush --noinput
	docker-compose exec redis redis-cli FLUSHALL
	@echo "✅ Test environment cleaned"

# Debug commands
debug-logs:
	docker-compose logs web | tail -50

debug-db:
	docker-compose exec db psql -U postgres -d qsuite

debug-redis:
	docker-compose exec redis redis-cli

debug-shell:
	docker-compose exec web python manage.py shell

# Service management
start:
	docker-compose up -d

stop:
	docker-compose down

restart:
	docker-compose restart

status:
	docker-compose ps

rebuild:
	docker-compose build
