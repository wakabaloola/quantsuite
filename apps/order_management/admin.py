from django.contrib import admin
from .models import SimulatedOrder, OrderBookLevel, OrderQueue

# Register your models here.

# This line tells Django to show the SimulatedOrder model in the admin
admin.site.register(SimulatedOrder)

# It is also useful to register these related models for debugging
admin.site.register(OrderBookLevel)
admin.site.register(OrderQueue)
