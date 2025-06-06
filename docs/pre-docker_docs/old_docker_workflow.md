# Django Development Workflow: Pre-Docker vs Docker

## Table of Contents
0. [Quick Reference](#quick-reference)
1. [Initial Setup](#initial-setup)
2. [Running the Development Server](#running-the-development-server)
3. [Database Operations](#database-operations)
4. [Package Management](#package-management)
5. [Django Management Commands](#django-management-commands)
6. [Testing](#testing)
7. [Debugging](#debugging)
8. [Logs and Monitoring](#logs-and-monitoring)
9. [Shell Access](#shell-access)
10. [Static Files](#static-files)
11. [Celery Operations](#celery-operations)
12. [Environment Management](#environment-management)
13. [Useful Docker Commands](#useful-docker-commands)

---

## Quick Reference

```bash
# Instead of: python manage.py migrate
docker-compose exec web python manage.py migrate

# Instead of: pip install package
# Edit requirements/development.txt, then:
docker-compose build web

# Instead of: python manage.py shell
docker-compose exec web python manage.py shell
```

## Initial Setup

### Pre-Docker
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv/bin/activate` on macOS/Linux

# Install dependencies
pip install -r requirements/development.txt

# Install and start PostgreSQL locally
brew install postgresql
brew services start postgresql
createdb qsuite

# Install and start Redis locally
brew install redis
brew services start redis

# Set up environment variables
cp .env.example .env
# Edit .env with local database settings

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### With Docker
```bash
# Build and start all services
docker-compose up --build

# Run migrations (in another terminal)
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

---

## Running the Development Server

### Pre-Docker
```bash
# Activate virtual environment
source venv/bin/activate

# Ensure PostgreSQL and Redis are running
brew services start postgresql
brew services start redis

# Start Django development server
python manage.py runserver

# Start Celery worker (separate terminal)
celery -A config worker -l INFO

# Start Celery beat (if using periodic tasks)
celery -A config beat -l INFO
```

### With Docker
```bash
# Start all services (Django, PostgreSQL, Redis, Celery)
docker-compose up

# Or run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f web
docker-compose logs -f celery
```

---

## Database Operations

### Pre-Docker
```bash
# Activate virtual environment first
source venv/bin/activate

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database
python manage.py flush

# Create superuser
python manage.py createsuperuser

# Database shell
python manage.py dbshell

# Load fixtures
python manage.py loaddata fixtures/sample_data.json

# Dump data
python manage.py dumpdata > backup.json
```

### With Docker
```bash
# Create migrations
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Reset database
docker-compose exec web python manage.py flush

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Database shell
docker-compose exec web python manage.py dbshell

# Load fixtures
docker-compose exec web python manage.py loaddata fixtures/sample_data.json

# Dump data
docker-compose exec web python manage.py dumpdata > backup.json

# Direct PostgreSQL access
docker-compose exec db psql -U qsuite -d qsuite
```

---

## Package Management

### Pre-Docker
```bash
# Activate virtual environment
source venv/bin/activate

# Install new package
pip install django-extensions
echo "django-extensions" >> requirements/development.txt

# Update requirements
pip freeze > requirements/development.txt

# Install from requirements
pip install -r requirements/development.txt

# Remove package
pip uninstall django-extensions
# Manually remove from requirements files
```

### With Docker
```bash
# Add package to requirements/development.txt
echo "django-extensions" >> requirements/development.txt

# Rebuild container with new dependencies
docker-compose build web

# Or rebuild and restart
docker-compose up --build

# For temporary testing (not persistent)
docker-compose exec web pip install django-extensions
```

---

## Django Management Commands

### Pre-Docker
```bash
source venv/bin/activate

# Standard commands
python manage.py collectstatic
python manage.py startapp newapp
python manage.py shell
python manage.py showmigrations
python manage.py check
python manage.py runserver 0.0.0.0:8080

# Custom commands
python manage.py your_custom_command
```

### With Docker
```bash
# Standard commands
docker-compose exec web python manage.py collectstatic
docker-compose exec web python manage.py startapp newapp
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py showmigrations
docker-compose exec web python manage.py check

# Run server on different port (modify docker-compose.yml)
# Or use docker run with port mapping

# Custom commands
docker-compose exec web python manage.py your_custom_command
```

---

## Testing

### Pre-Docker
```bash
source venv/bin/activate

# Run all tests
python manage.py test

# Run specific app tests
python manage.py test apps.accounts

# Run with pytest
pytest

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html

# Run specific test file
python manage.py test apps.accounts.tests.test_models
```

### With Docker
```bash
# Run all tests
docker-compose exec web python manage.py test

# Run specific app tests
docker-compose exec web python manage.py test apps.accounts

# Run with pytest
docker-compose exec web pytest

# Run with coverage
docker-compose exec web coverage run --source='.' manage.py test
docker-compose exec web coverage report
docker-compose exec web coverage html

# Run specific test file
docker-compose exec web python manage.py test apps.accounts.tests.test_models

# Run tests with test database
docker-compose run --rm web python manage.py test
```

---

## Debugging

### Pre-Docker
```bash
source venv/bin/activate

# Using pdb
# Add: import pdb; pdb.set_trace() in your code
python manage.py runserver

# Using Django shell
python manage.py shell

# Using ipython (if installed)
python manage.py shell -i ipython

# Using Django shell_plus (django-extensions)
python manage.py shell_plus
```

### With Docker
```bash
# Using pdb (requires stdin_open: true and tty: true in docker-compose.yml)
# Add: import pdb; pdb.set_trace() in your code
docker-compose up

# Using Django shell
docker-compose exec web python manage.py shell

# Using ipython
docker-compose exec web python manage.py shell -i ipython

# Using Django shell_plus
docker-compose exec web python manage.py shell_plus

# Access interactive container
docker-compose exec web bash
```

---

## Logs and Monitoring

### Pre-Docker
```bash
# Django logs appear in terminal where runserver is running
python manage.py runserver

# Celery logs
celery -A config worker -l INFO

# PostgreSQL logs
tail -f /usr/local/var/log/postgresql@14.log  # Homebrew path

# Redis logs
redis-cli monitor
```

### With Docker
```bash
# View all logs
docker-compose logs

# Follow logs
docker-compose logs -f

# Specific service logs
docker-compose logs web
docker-compose logs celery
docker-compose logs db
docker-compose logs redis

# Follow specific service
docker-compose logs -f web

# Last N lines
docker-compose logs --tail=50 web
```

---

## Shell Access

### Pre-Docker
```bash
# Python shell with Django
source venv/bin/activate
python manage.py shell

# System shell (already in your terminal)
# Database shell
python manage.py dbshell

# Redis CLI
redis-cli
```

### With Docker
```bash
# Python shell with Django
docker-compose exec web python manage.py shell

# System shell inside container
docker-compose exec web bash

# Database shell
docker-compose exec web python manage.py dbshell

# Direct database access
docker-compose exec db psql -U qsuite -d qsuite

# Redis CLI
docker-compose exec redis redis-cli
```

---

## Static Files

### Pre-Docker
```bash
source venv/bin/activate

# Collect static files
python manage.py collectstatic

# Find static files
python manage.py findstatic admin/css/base.css

# Clear static files
rm -rf staticfiles/
```

### With Docker
```bash
# Collect static files
docker-compose exec web python manage.py collectstatic

# Find static files
docker-compose exec web python manage.py findstatic admin/css/base.css

# Clear static files (from host)
rm -rf staticfiles/

# Or from container
docker-compose exec web rm -rf staticfiles/
```

---

## Celery Operations

### Pre-Docker
```bash
source venv/bin/activate

# Start worker
celery -A config worker -l INFO

# Start beat scheduler
celery -A config beat -l INFO

# Monitor tasks
celery -A config flower

# Inspect workers
celery -A config inspect active
celery -A config inspect stats

# Purge all tasks
celery -A config purge
```

### With Docker
```bash
# Worker runs automatically with docker-compose up

# Access worker logs
docker-compose logs -f celery

# Execute Celery commands
docker-compose exec celery celery -A config inspect active
docker-compose exec celery celery -A config inspect stats
docker-compose exec celery celery -A config purge

# Start flower (add to docker-compose.yml)
docker-compose exec celery celery -A config flower

# Scale workers
docker-compose up --scale celery=3
```

---

## Environment Management

### Pre-Docker
```bash
# Activate/deactivate virtual environment
source venv/bin/activate
deactivate

# Environment variables
export DEBUG=True
export DATABASE_URL=postgresql://user:pass@localhost/db

# Or use .env file with python-decouple
# Edit .env file manually
```

### With Docker
```bash
# Environment variables managed through:
# 1. .env file (automatic with docker-compose)
# 2. docker-compose.yml env_file directive
# 3. Direct environment variables in docker-compose.yml

# Edit environment
vim .env

# Override environment for single command
docker-compose run -e DEBUG=False web python manage.py check

# Use different env file
docker-compose --env-file .env.production up
```

---

## Useful Docker Commands

### Container Management
```bash
# View running containers
docker-compose ps

# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes database data)
docker-compose down -v

# Restart specific service
docker-compose restart web

# View resource usage
docker-compose top
```

### Building and Updating
```bash
# Build without cache
docker-compose build --no-cache

# Build specific service
docker-compose build web

# Pull latest images
docker-compose pull

# Remove unused images
docker image prune
```

### File Operations
```bash
# Copy files from container to host
docker-compose cp web:/app/file.txt ./file.txt

# Copy files from host to container
docker-compose cp ./file.txt web:/app/file.txt

# Edit files in container
docker-compose exec web vi /app/manage.py
```

### Troubleshooting
```bash
# Check container status
docker-compose ps

# View detailed logs
docker-compose logs --details web

# Execute commands in one-off container
docker-compose run --rm web python manage.py shell

# Access container with root privileges
docker-compose exec --user root web bash

# Inspect container
docker-compose exec web env  # View environment variables
docker-compose exec web ps aux  # View running processes
```

---

## Key Differences Summary

| Operation | Pre-Docker | Docker |
|-----------|------------|---------|
| **Environment Setup** | Manual virtual env, local services | `docker-compose up --build` |
| **Running Server** | `python manage.py runserver` | `docker-compose up` |
| **Django Commands** | Direct: `python manage.py migrate` | Prefixed: `docker-compose exec web python manage.py migrate` |
| **Dependencies** | `pip install` + rebuild | Edit requirements + `docker-compose build` |
| **Services** | Start individually (PostgreSQL, Redis, Celery) | All start together |
| **Debugging** | Direct pdb access | Requires tty configuration |
| **Environment Variables** | Export or .env + manual load | Automatic via docker-compose |
| **Database Access** | Direct connection | Through container |
| **Logs** | Separate terminals/files | Centralized via `docker-compose logs` |

## Tips for Smooth Transition

1. **Always use `docker-compose exec web` prefix** for Django commands
2. **Use `docker-compose run --rm web`** for one-off commands
3. **Edit files on your host machine** - they sync automatically via volumes
4. **Use `docker-compose logs -f`** instead of multiple terminal windows
5. **Remember to rebuild** after changing requirements files
6. **Use `.env` files** for environment configuration instead of exports
7. **Keep databases running** - use `docker-compose down` instead of `docker-compose down -v`
