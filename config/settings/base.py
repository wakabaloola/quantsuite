# config/settings/base.py
from pathlib import Path
from decouple import config

# Build paths like this: BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

# SECRET KEY from environment
SECRET_KEY = config('SECRET_KEY')

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    # API and REST Framework
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',
    'drf_yasg',
    
    # Cache and sessions
    'django_redis',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.core',
    'apps.market_data',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Security settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = config('ENABLE_HTTPS', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('ENABLE_HTTPS', default=False, cast=bool)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'  # Critical for financial data - always use UTC
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# JWT Configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
}

# Redis/Cache configuration
REDIS_URL = config('REDIS_URL', default='redis://redis:6379')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 100,
                'retry_on_timeout': True,
            },
        }
    }
}

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 hours

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=f'{REDIS_URL}/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=f'{REDIS_URL}/0')

CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

CELERY_TASK_ROUTES = {
    'apps.market_data.tasks.ingest_market_data_async': {'queue': 'data_ingestion'},
    'apps.market_data.tasks.calculate_technical_indicators_*': {'queue': 'analytics'},
    'apps.market_data.tasks.update_portfolio_analytics': {'queue': 'portfolio'},
    'apps.market_data.tasks.cleanup_old_data': {'queue': 'maintenance'},
}

CELERY_TASK_ANNOTATIONS = {
    'apps.market_data.tasks.ingest_market_data_async': {'rate_limit': '10/m'},
    'apps.market_data.tasks.refresh_real_time_quotes': {'rate_limit': '100/m'},
}

# External API Configuration
ALPHA_VANTAGE_API_KEY = config('ALPHA_VANTAGE_API_KEY', default='')

# Data ingestion settings
DATA_INGESTION_SETTINGS = {
    'DEFAULT_BATCH_SIZE': 1000,
    'MAX_RETRIES': 3,
    'RETRY_DELAY_SECONDS': 60,
    'YFINANCE_RATE_LIMIT': 2000,  # requests per hour
    'ALPHA_VANTAGE_RATE_LIMIT': 5,  # requests per minute
}

# Technical analysis settings
TECHNICAL_ANALYSIS_SETTINGS = {
    'DEFAULT_INDICATORS': ['rsi', 'macd', 'sma_20', 'sma_50', 'bollinger_bands'],
    'CACHE_TIMEOUT_SECONDS': 3600,  # 1 hour
    'MAX_CALCULATION_PERIODS': 1000,
}

# Portfolio analytics settings
PORTFOLIO_SETTINGS = {
    'UPDATE_FREQUENCY_MINUTES': 60,
    'RISK_FREE_RATE': 0.02,  # 2% annual risk-free rate
    'BENCHMARK_SYMBOL': '^GSPC',  # S&P 500 as default benchmark
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'qsuite.log',
            'maxBytes': 1024*1024*50,  # 50MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Performance settings
DATABASE_CONNECTION_POOLING = True
DATABASE_CONN_MAX_AGE = 600  # 10 minutes

# GPU Acceleration (optional)
USE_GPU = config('USE_GPU', default=False, cast=bool)

# API Documentation settings
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'SUPPORTED_SUBMIT_METHODS': [
        'get',
        'post',
        'put',
        'delete',
        'patch'
    ],
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DOC_EXPANSION': 'none',
    'DEEP_LINKING': True,
    'SHOW_EXTENSIONS': True,
    'DEFAULT_MODEL_RENDERING': 'model',
}

# Create logs directory if it doesn't exist
import os
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
