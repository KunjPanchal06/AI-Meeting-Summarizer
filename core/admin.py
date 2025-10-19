# core/admin.py
from django.contrib import admin
from .models import Meeting, Task

class MeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'created_at', 'user']
    list_filter = ['status', 'created_at']
    search_fields = ['title']

class TaskAdmin(admin.ModelAdmin):
    list_display = ['description', 'assignee', 'status', 'meeting']
    list_filter = ['status']  # Removed 'deadline' since it doesn't exist
    search_fields = ['description', 'assignee']

admin.site.register(Meeting, MeetingAdmin)
admin.site.register(Task, TaskAdmin)
