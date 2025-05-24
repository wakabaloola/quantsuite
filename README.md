
# PostgreSQL Setup for QSuite

This guide explains how to set up PostgreSQL for the QSuite application.

## Installation (macOS)

1. Install PostgreSQL using Homebrew:
   ```bash
   brew install postgresql@14
   ```

2. Start the PostgreSQL service:
   ```bash
   brew services start postgresql@14
   ```

3. Add PostgreSQL binaries to your PATH:
   ```bash
   echo 'export PATH="/usr/local/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

## Database Setup

1. Connect to PostgreSQL:
   ```bash
   psql postgres
   ```

2. Create the development database:
   ```sql
   CREATE DATABASE qsuite_dev;
   ```
  If a specific user is needed (should match with details found in .env):
  ```sql
  CREATE USER qsuite_user WITH PASSWORD 'your_password';
  GRANT ALL PRIVILEGES ON DATABASE qsuite_dev TO qsuite_user;
  \q
  ```
  For better security, after creating the user we can instead restrict permissions more granularly:
  ```sql
  GRANT CONNECT ON DATABASE qsuite_dev TO qsuite_user;
  GRANT USAGE ON SCHEMA public TO qsuite_user;
  GRANT CREATE ON SCHEMA public TO qsuite_user;
  ```

3. Verify the database was created:
   ```bash
   psql -l
   ```
   You should see `qsuite_dev` in the list of databases.

## Django Configuration

1. Install the PostgreSQL adapter for Python:
   ```bash
   pip install psycopg2-binary
   ```

2. Configure database settings in your `.env` file:
   ```
   DB_NAME=qsuite_dev
   DB_USER=qsuite_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   ```

3. Apply migrations:
   ```bash
   python manage.py migrate
   ```

## Useful PostgreSQL Commands

- Connect to a specific database:
  ```bash
  psql qsuite_dev
  ```

- List all databases:
  ```bash
  psql postgres -c "\l"
  ```

- List all tables in current database:
  ```bash
  psql qsuite_dev -c "\dt"
  ```

- Show database schema:
  ```bash
  pg_dump -s qsuite_dev
  ```

- Backup database:
  ```bash
  pg_dump qsuite_dev > qsuite_backup.sql
  ```

- Restore database:
  ```bash
  psql qsuite_dev < qsuite_backup.sql
  ```


# How to Create a New Data Source

```python
from apps.accounts.models import User
from apps.market_data.models import DataSource
```
Can check existings data sources,
```python
for source in DataSource.objects.all():
    print(f"- {source.name} ({source.code})")
```
The app label is given by `User._meta.app_label`.  We can create a data source as follows,
```python
yahoo_source = DataSource.objets.create(
    name="Yahoo Finance",
    code="YAHOO",
    url="https://finance.yahoo.com"
)
print(f"Created: {yahoo_source}")
```
Can then get the existing data source with code "YAHOO" as follows,
```python
try:
    yahoo_source = DataSource.objects.get(code="YAHOO")
    print(f"Found existing source: {yahoo_source}")
except DataSource.DoesNotExist:
    print(f"No source with code 'YAHOO' found.")
```
Finally, to update the existing Yahoo source,
```python
yahoo_source = DataSource.objects.get(code="YAHOO")
yahoo_source.name = "Yahoo Finance (Updated)"
yahoo_source.save()
print(f"Updated: {yahoo_source}")
```
