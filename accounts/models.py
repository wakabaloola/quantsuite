from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Custom user model for quant finance platform with extended fields"""
    
    # Additional fields for financial applications
    timezone = models.CharField(max_length=50, default='UTC')
    data_permissions = models.JSONField(default=dict)
    computation_limits = models.JSONField(default=dict)
    
    # MFA and security settings
    requires_mfa = models.BooleanField(default=True)
    last_data_access = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'quant_users'
        
    def __str__(self):
        return f"{self.username} ({self.email})"
