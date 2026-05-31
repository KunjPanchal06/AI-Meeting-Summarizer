"""
Celery application configuration for meeting_summarizer.

This module initializes the Celery app and configures it to use
Django settings. It auto-discovers tasks in all installed apps.
"""

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meeting_summarizer.settings')

app = Celery('meeting_summarizer')

# Load task-related settings from Django settings, using the CELERY_ prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in all registered Django apps.
app.autodiscover_tasks()
