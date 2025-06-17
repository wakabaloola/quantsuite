# apps/core/urls.py
"""Core application URLs"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.health_check, name='health_check'),
    path('system/', views.system_metrics, name='system_metrics'),
    path('database/', views.database_health, name='database_health'),
    path('cache/', views.cache_health, name='cache_health'),
    path('services/', views.services_health, name='services_health'),
]
