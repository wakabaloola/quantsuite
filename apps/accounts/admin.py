# apps/accounts/admin.py
"""Admin configuration for custom user model"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'requires_mfa', 'last_data_access']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'requires_mfa', 'timezone']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('QSuite Settings', {
            'fields': ('timezone', 'requires_mfa', 'last_data_access')
        }),
        ('Permissions', {
            'fields': ('data_permissions', 'computation_limits'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('QSuite Settings', {
            'fields': ('timezone', 'requires_mfa')
        }),
    )
    
    readonly_fields = ['last_data_access']
