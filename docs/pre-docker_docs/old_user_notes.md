# Users

## Create a New Superuser
To create a new superuser, first open the shell,
```bash
python manage.py shell
```
and then,
```python
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.create_superuser('username', 'email_address', 'new_password')
```
where `username`, `email_address` and `new_password` can be chosen at will, provided `username` does not already exist. Type `exit()` to exist shell.

## Change Password of Existing Superuser
If the username already exists but the password needs to be reset,
```python
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='dps')
user.set_password('newpassword123')
user.save()
```
To exist the shell type `exit()`. You may now log into the admin panel with `username` and `new_password`.
