#!/bin/bash
# scripts/docker_test_commands.sh

# Docker Test Commands for QSuite Dashboard System
echo "🐳 QSuite Docker Test Commands"
echo "=============================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to run command with status
run_command() {
    echo -e "${YELLOW}Running: $1${NC}"
    if eval $1; then
        echo -e "${GREEN}✅ SUCCESS${NC}"
        return 0
    else
        echo -e "${RED}❌ FAILED${NC}"
        return 1
    fi
}

# Check Docker services
echo -e "\n🔍 Checking Docker Services..."
run_command "docker-compose ps"

# Individual test commands for Docker
echo -e "\n📋 Individual Test Commands:"

echo -e "\n1️⃣  WebSocket Manager Tests:"
echo "docker-compose exec web python manage.py test apps.core.tests.test_websocket_manager --keepdb"

echo -e "\n2️⃣  Portfolio Analytics Tests:"
echo "docker-compose exec web python manage.py test apps.trading_analytics.tests.test_portfolio_analytics --keepdb"

echo -e "\n3️⃣  Dashboard Service Tests:"
echo "docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_service --keepdb"

echo -e "\n4️⃣  Dashboard Consumer Tests:"
echo "docker-compose exec web python manage.py test apps.trading_simulation.tests.test_dashboard_consumer --keepdb"

echo -e "\n5️⃣  Dashboard API Tests:"
echo "docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_api --keepdb"

echo -e "\n6️⃣  Integration Tests:"
echo "docker-compose exec web python manage.py test tests.integration.test_dashboard_integration --keepdb"

echo -e "\n7️⃣  Performance Tests (Docker-optimized):"
echo "docker-compose exec web python manage.py test tests.integration.test_performance --keepdb"

echo -e "\n8️⃣  Background Tasks Tests:"
echo "docker-compose exec web python manage.py test apps.trading_analytics.tests.test_dashboard_tasks --keepdb"

# Quick test commands
echo -e "\n⚡ Quick Test Commands:"

echo -e "\n🔸 Run ALL tests:"
echo "docker-compose exec web python scripts/run_comprehensive_tests.py"

echo -e "\n🔸 Run specific test file:"
echo "docker-compose exec web python manage.py test <test_file> --keepdb"

echo -e "\n🔸 Run with pytest:"
echo "docker-compose exec web pytest tests/integration/ -v"

echo -e "\n🔸 Run performance tests only:"
echo "docker-compose exec web python tests/integration/test_performance.py"

# Debugging commands
echo -e "\n🐛 Debugging Commands:"

echo -e "\n🔹 Check logs:"
echo "docker-compose logs web"
echo "docker-compose logs celery"
echo "docker-compose logs redis"

echo -e "\n🔹 Interactive shell:"
echo "docker-compose exec web python manage.py shell"

echo -e "\n🔹 Database shell:"
echo "docker-compose exec db psql -U postgres -d qsuite"

echo -e "\n🔹 Redis CLI:"
echo "docker-compose exec redis redis-cli"

echo -e "\n🔹 Container bash:"
echo "docker-compose exec web bash"

# Environment setup
echo -e "\n⚙️  Environment Setup:"

echo -e "\n🔧 Setup database:"
echo "docker-compose exec web python manage.py migrate --run-syncdb"

echo -e "\n🔧 Create superuser:"
echo "docker-compose exec web python manage.py createsuperuser"

echo -e "\n🔧 Collect static files:"
echo "docker-compose exec web python manage.py collectstatic --noinput"

echo -e "\n🔧 Load test fixtures:"
echo "docker-compose exec web python manage.py loaddata test_fixtures.json"

# Service management
echo -e "\n🔄 Service Management:"

echo -e "\n🔸 Start services:"
echo "docker-compose up -d"

echo -e "\n🔸 Restart services:"
echo "docker-compose restart"

echo -e "\n🔸 Stop services:"
echo "docker-compose down"

echo -e "\n🔸 View service status:"
echo "docker-compose ps"

echo -e "\n🔸 Rebuild services:"
echo "docker-compose build"

echo -e "\n📝 Note: Add --keepdb flag to Django tests to reuse database between test runs"
echo -e "📝 Note: Use -v flag with pytest for verbose output"
echo -e "📝 Note: Performance thresholds are adjusted for Docker overhead"

# Make script executable if run directly
if [ "$1" = "run" ]; then
    echo -e "\n🚀 Running comprehensive Docker tests..."
    run_command "docker-compose exec web python scripts/run_comprehensive_tests.py"
fi
