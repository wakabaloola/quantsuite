# Development stage
FROM python:3.11-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/ .
RUN pip install --upgrade pip && \
    pip install -r development.txt

COPY . .

# Production stage
FROM development AS production

RUN pip install gunicorn && \
    pip uninstall -y django-debug-toolbar

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
