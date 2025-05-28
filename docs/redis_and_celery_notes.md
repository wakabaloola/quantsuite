## ✅ Step-by-Step Integration of Celery and Redis into Django

### 1. **Install Required Packages**

First, ensure that you have Celery and Redis installed. You can install them using pip:([AlmaBetter][2])

```zsh
pip install celery redis
```

### 2. **Install and Start Redis**

On macOS, you can install Redis using Homebrew:

```zsh
brew install redis
```

After installation, start the Redis server:([ChemiCloud][3])

```zsh
brew services start redis
```

To verify that Redis is running:([GeeksforGeeks][4])

```zsh
redis-cli ping
```

You should receive a `PONG` response.

### 3. **Configure Celery in Your Django Project**

In your Django project's main directory (where `settings.py` resides), create a new file named `celery.py`:([YouTube][1])

```python
# myproject/celery.py

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
```

Replace `'myproject'` with the actual name of your Django project.

### 4. **Initialize Celery in `__init__.py`**

In the same directory as `celery.py`, modify the `__init__.py` file to ensure Celery is loaded when Django starts:

```python
# myproject/__init__.py

from .celery import app as celery_app

__all__ = ('celery_app',)
```

### 5. **Configure Celery Settings**

In your `settings.py`, add the following configuration to specify Redis as the broker and result backend:

```python
# settings.py

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

### 6. **Create a Sample Task**

Within one of your Django apps, create a `tasks.py` file and define a simple task:

```python
# myapp/tasks.py

from celery import shared_task

@shared_task
def add(x, y):
    return x + y
```

### 7. **Run Celery Worker**

In your terminal, navigate to your project's directory and start the Celery worker:

```zsh
celery -A myproject worker --loglevel=info
```

Ensure you replace `myproject` with your actual project name.

### 8. **Execute the Task**

You can now call the task from Django's shell or views:

```python
# Using Django shell
from myapp.tasks import add
add.delay(4, 6)
```

This will execute the `add` task asynchronously using Celery and Redis.([YouTube][1])

---

[1]: https://www.youtube.com/watch?v=CkR_gjlDH-4&utm_source=chatgpt.com "How to set up Celery and Redis - Django Background Tasks - Part 2"
[2]: https://www.almabetter.com/bytes/tutorials/django/install-django?utm_source=chatgpt.com "How to install Django - AlmaBetter"
[3]: https://chemicloud.com/kb/article/install-and-setup-django-application/?utm_source=chatgpt.com "How to Install and Set up a Django Application - ChemiCloud"
[4]: https://www.geeksforgeeks.org/djnago-installation-and-setup/?utm_source=chatgpt.com "Django Installation and Setup | GeeksforGeeks"

