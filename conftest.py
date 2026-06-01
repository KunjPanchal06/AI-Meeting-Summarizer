"""
Root-level pytest configuration for the Meeting Summarizer project.

Provides:
- Django settings configuration
- Redis client fixture for direct cache manipulation in tests
- Celery ALWAYS_EAGER fixture so tasks run synchronously without a worker
"""


import pytest
import redis
from django.conf import settings


@pytest.fixture
def redis_client():
    """
    Provide a Redis client connected to the test Redis instance.

    Flushes the test database on teardown to avoid cross-test pollution.
    """
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def celery_eager(settings):
    """
    Force Celery tasks to execute synchronously (in-process).

    This removes the need for a running Celery worker during tests.
    Errors inside tasks will propagate immediately as exceptions.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
