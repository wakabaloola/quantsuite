# User Management - Docker Setup (QSuite)

## ✅ Current Docker-based User Management

**All user management operations now use the Docker containerized Django environment.**

---

## 🔧 Creating Users

### Create Superuser (Admin Access)
```bash
# Interactive superuser creation
docker-compose exec web python manage.py createsuperuser

# Follow prompts:
# Username: admin
# Email address: admin@qsuite.com  
# Password: (enter secure password)
# Password (again): (confirm password)
```

### Create Superuser via Django Shell
```bash
# Open Django shell
docker-compose exec web python manage.py shell
```

```python
# In Django shell:
from django.contrib.auth import get_user_model
User = get_user_model()

# Create superuser
superuser = User.objects.create_superuser(
    username='admin',
    email='admin@qsuite.com',
    password='secure_password_123'
)
print(f"Created superuser: {superuser.username}")

# Exit shell
exit()
```

### Create Regular User
```bash
# Via Django shell
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

user = User.objects.create_user(
    username='trader1',
    email='trader1@qsuite.com',
    password='user_password_123',
    first_name='John',
    last_name='Trader'
)
print(f'Created user: {user.username}')
"
```

---

## 🔑 Password Management

### Change Password for Existing User
```bash
# Via Django shell
docker-compose exec web python manage.py shell
```

```python
# In Django shell:
from django.contrib.auth import get_user_model
User = get_user_model()

# Get user by username
user = User.objects.get(username='admin')

# Set new password
user.set_password('new_secure_password_456')
user.save()

print(f"Password updated for user: {user.username}")
exit()
```

### One-liner Password Reset
```bash
# Change password in single command
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='admin')
user.set_password('new_password_789')
user.save()
print('Password updated successfully')
"
```

### Django Management Command for Password Reset
```bash
# Use Django's built-in changepassword command
docker-compose exec web python manage.py changepassword admin

# Follow prompts to enter new password
```

---

## 👥 User Management Operations

### List All Users
```bash
# Via Django shell
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

print('All users:')
for user in User.objects.all():
    print(f'- {user.username} ({user.email}) - Superuser: {user.is_superuser}')
"
```

### User Information and Stats
```bash
# Get detailed user information
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

total_users = User.objects.count()
superusers = User.objects.filter(is_superuser=True).count()
active_users = User.objects.filter(is_active=True).count()

print(f'Total users: {total_users}')
print(f'Superusers: {superusers}')
print(f'Active users: {active_users}')
print(f'Inactive users: {total_users - active_users}')
"
```

### Activate/Deactivate Users
```bash
# Deactivate user (soft delete - preserves data)
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='trader1')
user.is_active = False
user.save()
print(f'User {user.username} deactivated')
"

# Reactivate user
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='trader1')
user.is_active = True
user.save()
print(f'User {user.username} reactivated')
"
```

### Promote User to Superuser
```bash
# Make user a superuser
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='trader1')
user.is_superuser = True
user.is_staff = True
user.save()
print(f'User {user.username} promoted to superuser')
"

# Remove superuser privileges
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='trader1')
user.is_superuser = False
user.is_staff = False
user.save()
print(f'Superuser privileges removed from {user.username}')
"
```

---

## 🏢 Advanced User Management for QSuite

### Create Trading Team Users
```bash
# Create multiple users for trading team
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

trading_team = [
    {'username': 'equity_trader', 'email': 'equity@qsuite.com', 'first_name': 'Alice', 'last_name': 'Equity'},
    {'username': 'fx_trader', 'email': 'fx@qsuite.com', 'first_name': 'Bob', 'last_name': 'FX'},
    {'username': 'risk_manager', 'email': 'risk@qsuite.com', 'first_name': 'Carol', 'last_name': 'Risk'},
    {'username': 'quant_analyst', 'email': 'quant@qsuite.com', 'first_name': 'David', 'last_name': 'Quant'},
]

for user_data in trading_team:
    user, created = User.objects.get_or_create(
        username=user_data['username'],
        defaults={
            'email': user_data['email'],
            'first_name': user_data['first_name'],
            'last_name': user_data['last_name'],
            'is_active': True
        }
    )
    if created:
        user.set_password('temp_password_123')
        user.save()
        print(f'Created user: {user.username}')
    else:
        print(f'User already exists: {user.username}')
"
```

### User Groups and Permissions
```bash
# Create user groups for different roles
docker-compose exec web python manage.py shell -c "
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

# Create groups
traders_group, created = Group.objects.get_or_create(name='Traders')
analysts_group, created = Group.objects.get_or_create(name='Analysts')
managers_group, created = Group.objects.get_or_create(name='Risk Managers')

print('Created user groups:')
for group in Group.objects.all():
    print(f'- {group.name}')

# Add users to groups
equity_trader = User.objects.get(username='equity_trader')
quant_analyst = User.objects.get(username='quant_analyst')
risk_manager = User.objects.get(username='risk_manager')

equity_trader.groups.add(traders_group)
quant_analyst.groups.add(analysts_group)
risk_manager.groups.add(managers_group)

print('Users assigned to groups')
"
```

### User Profile Management
```bash
# Update user profiles
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

# Update user information
user = User.objects.get(username='equity_trader')
user.first_name = 'Alice'
user.last_name = 'Smith'
user.email = 'alice.smith@qsuite.com'
user.save()

print(f'Updated profile for {user.username}:')
print(f'- Name: {user.first_name} {user.last_name}')
print(f'- Email: {user.email}')
print(f'- Groups: {list(user.groups.values_list(\"name\", flat=True))}')
"
```

---

## 🔐 Authentication and Security

### Check User Authentication
```bash
# Test user authentication
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

User = get_user_model()

# Test authentication
username = 'admin'
password = 'your_password'

user = authenticate(username=username, password=password)
if user is not None:
    print(f'✅ Authentication successful for {username}')
    print(f'- Superuser: {user.is_superuser}')
    print(f'- Active: {user.is_active}')
    print(f'- Last login: {user.last_login}')
else:
    print(f'❌ Authentication failed for {username}')
"
```

### Password Validation
```bash
# Test password strength
docker-compose exec web python manage.py shell -c "
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()
user = User()

passwords_to_test = ['123', 'password', 'secure_password_123', 'VerySecure!Pass123']

for password in passwords_to_test:
    try:
        validate_password(password, user)
        print(f'✅ \"{password}\" is valid')
    except ValidationError as e:
        print(f'❌ \"{password}\" is invalid: {e}')
"
```

### Session Management
```bash
# Clear all user sessions (logs out all users)
docker-compose exec web python manage.py shell -c "
from django.contrib.sessions.models import Session
session_count = Session.objects.count()
Session.objects.all().delete()
print(f'Cleared {session_count} user sessions')
"

# View active sessions
docker-compose exec web python manage.py shell -c "
from django.contrib.sessions.models import Session
from django.utils import timezone

active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
print(f'Active sessions: {active_sessions.count()}')

for session in active_sessions[:5]:  # Show first 5
    print(f'- Session key: {session.session_key[:20]}...')
    print(f'  Expires: {session.expire_date}')
"
```

---

## 📊 User Analytics and Monitoring

### User Activity Report
```bash
# Generate user activity report
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

print('User Activity Report:')
print('=' * 50)

for user in User.objects.all():
    print(f'Username: {user.username}')
    print(f'Email: {user.email}')
    print(f'Active: {user.is_active}')
    print(f'Staff: {user.is_staff}')
    print(f'Superuser: {user.is_superuser}')
    print(f'Date joined: {user.date_joined.strftime(\"%Y-%m-%d %H:%M\")}')
    print(f'Last login: {user.last_login.strftime(\"%Y-%m-%d %H:%M\") if user.last_login else \"Never\"}')
    print(f'Groups: {list(user.groups.values_list(\"name\", flat=True))}')
    print('-' * 30)
"
```

### Database User Statistics
```bash
# Check user-related database statistics
docker-compose exec db psql -U qsuite -d qsuite -c "
SELECT 
    'Total Users' as metric,
    COUNT(*) as count
FROM auth_user
UNION ALL
SELECT 
    'Active Users',
    COUNT(*)
FROM auth_user 
WHERE is_active = true
UNION ALL
SELECT 
    'Superusers',
    COUNT(*)
FROM auth_user 
WHERE is_superuser = true
UNION ALL
SELECT 
    'Staff Users',
    COUNT(*)
FROM auth_user 
WHERE is_staff = true;"
```

---

## 🛠️ Bulk User Operations

### Import Users from CSV
```python
# Create users from CSV file
# First, create a CSV file: users.csv
# username,email,first_name,last_name,is_staff
# trader1,trader1@qsuite.com,John,Trader,false
# analyst1,analyst1@qsuite.com,Jane,Analyst,false

import csv
from django.contrib.auth import get_user_model

def import_users_from_csv(file_path):
    User = get_user_model()
    
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            user, created = User.objects.get_or_create(
                username=row['username'],
                defaults={
                    'email': row['email'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'is_staff': row['is_staff'].lower() == 'true',
                    'is_active': True
                }
            )
            if created:
                user.set_password('temp_password_123')
                user.save()
                print(f'Created user: {user.username}')
            else:
                print(f'User already exists: {user.username}')

# Run in Django shell:
# import_users_from_csv('/path/to/users.csv')
```

### Export Users to CSV
```bash
# Export user data
docker-compose exec web python manage.py shell -c "
import csv
from django.contrib.auth import get_user_model

User = get_user_model()

with open('/tmp/users_export.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['Username', 'Email', 'First Name', 'Last Name', 'Active', 'Staff', 'Superuser', 'Date Joined'])
    
    for user in User.objects.all():
        writer.writerow([
            user.username,
            user.email,
            user.first_name,
            user.last_name,
            user.is_active,
            user.is_staff,
            user.is_superuser,
            user.date_joined.strftime('%Y-%m-%d %H:%M:%S')
        ])

print('Users exported to /tmp/users_export.csv')
"

# Copy file from container to host
docker-compose cp web:/tmp/users_export.csv ./users_export.csv
```

---

## 🔧 Custom User Management Commands

### Create Custom Management Command
```python
# apps/core/management/commands/create_test_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

class Command(BaseCommand):
    help = 'Create test users for development'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5, help='Number of test users to create')

    def handle(self, *args, **options):
        User = get_user_model()
        count = options['count']
        
        for i in range(1, count + 1):
            username = f'testuser{i}'
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@qsuite.com',
                    'first_name': f'Test{i}',
                    'last_name': 'User',
                    'is_active': True
                }
            )
            
            if created:
                user.set_password('testpass123')
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Created user: {username}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User already exists: {username}')
                )
```

```bash
# Use the custom command
docker-compose exec web python manage.py create_test_users --count=10
```

---

## 🚨 Emergency Procedures

### Reset Admin Password (Emergency)
```bash
# If you're locked out of admin account
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

# Get or create admin user
admin, created = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@qsuite.com',
        'is_superuser': True,
        'is_staff': True,
        'is_active': True
    }
)

# Set new password
admin.set_password('emergency_password_123')
admin.is_superuser = True
admin.is_staff = True
admin.is_active = True
admin.save()

print(f'Emergency admin access restored')
print(f'Username: admin')
print(f'Password: emergency_password_123')
print(f'Please change this password immediately!')
"
```

### Delete All Test Users
```bash
# Remove test users (be careful!)
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()

# Delete test users (username starts with 'test')
test_users = User.objects.filter(username__startswith='test')
count = test_users.count()
test_users.delete()

print(f'Deleted {count} test users')
"
```

---

## 🎯 Integration with QSuite Features

### User Permissions for Market Data
```bash
# Set up permissions for market data access
docker-compose exec web python manage.py shell -c "
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from apps.market_data.models import MarketData, Ticker

User = get_user_model()

# Get content types
market_data_ct = ContentType.objects.get_for_model(MarketData)
ticker_ct = ContentType.objects.get_for_model(Ticker)

# Create traders group with market data permissions
traders, created = Group.objects.get_or_create(name='Traders')

# Add permissions to traders group
permissions = Permission.objects.filter(
    content_type__in=[market_data_ct, ticker_ct]
)
traders.permissions.set(permissions)

# Add user to traders group
trader = User.objects.get(username='equity_trader')
trader.groups.add(traders)

print(f'Set up market data permissions for traders group')
print(f'Added {trader.username} to traders group')
"
```

---

## Summary

✅ **All user management now uses Docker commands:**
- `docker-compose exec web python manage.py createsuperuser`
- `docker-compose exec web python manage.py shell` for advanced operations
- All user data stored in PostgreSQL 17 container
- Persistent user data across container restarts

🎯 **Quick reference for daily use:**
```bash
# Create admin user
docker-compose exec web python manage.py createsuperuser

# Change password
docker-compose exec web python manage.py changepassword username

# Access Django admin
open http://localhost:8000/admin/

# Django shell for advanced operations
docker-compose exec web python manage.py shell
```

Your user management system is fully integrated with the Docker setup and ready for production use!
