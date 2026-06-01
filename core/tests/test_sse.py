"""
Tests for core.sse — Server-Sent Events progress endpoint.

Verifies:
- Writing progress data to Redis and reading it via the SSE endpoint
- Response content type is text/event-stream
- Streamed data contains the correct stage and percentage
"""

import json

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client

from core.models import Meeting
from core.tasks import PROGRESS_KEY


@pytest.mark.django_db
class TestSSEProgressEndpoint:
    """Tests for the /meetings/<id>/progress/ SSE endpoint."""

    def setup_method(self):
        """Create a test user, log in, and create a meeting."""
        self.user = User.objects.create_user(
            username="sseuser", password="ssepass123"
        )
        self.client = Client()
        self.client.login(username="sseuser", password="ssepass123")

        self.meeting = Meeting.objects.create(
            title="SSE Test Meeting",
            status="processing",
            user=self.user,
        )

    def test_sse_streams_progress_data(self):
        """
        Write a progress payload to Redis, then GET the SSE endpoint.
        Assert content type and streamed data.
        """
        # Write progress data directly to Redis cache
        progress_data = {
            "stage": "summarization",
            "pct": 55,
            "message": "Summary generated!",
            "done": False,
            "error": False,
        }
        key = PROGRESS_KEY.format(id=self.meeting.pk)
        cache.set(key, json.dumps(progress_data), timeout=60)

        # Make GET request to the SSE endpoint
        response = self.client.get(
            f"/meetings/{self.meeting.pk}/progress/"
        )

        # Content type should be text/event-stream
        assert response["Content-Type"] == "text/event-stream"

        # Read the first chunk of streamed content
        content = b""
        for chunk in response.streaming_content:
            content += chunk
            # Only read the first data event, then break
            if b"data:" in content:
                break

        decoded = content.decode("utf-8")

        # Should contain an SSE data event
        assert "data:" in decoded

        # Parse the JSON from the SSE data line
        for line in decoded.strip().split("\n"):
            if line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
                assert payload["stage"] == "summarization"
                assert payload["pct"] == 55
                assert payload["message"] == "Summary generated!"
                break

    def test_sse_streams_done_event(self):
        """When progress is done=True, the stream should include a done event."""
        progress_data = {
            "stage": "done",
            "pct": 100,
            "message": "Processing complete!",
            "done": True,
            "error": False,
        }
        key = PROGRESS_KEY.format(id=self.meeting.pk)
        cache.set(key, json.dumps(progress_data), timeout=60)

        response = self.client.get(
            f"/meetings/{self.meeting.pk}/progress/"
        )

        assert response["Content-Type"] == "text/event-stream"

        content = b""
        for chunk in response.streaming_content:
            content += chunk
            if b"data:" in content:
                break

        decoded = content.decode("utf-8")

        for line in decoded.strip().split("\n"):
            if line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
                assert payload["pct"] == 100
                assert payload["done"] is True
                assert payload["stage"] == "done"
                break

    def test_sse_requires_authentication(self):
        """Unauthenticated requests to the SSE endpoint should redirect to login."""
        anon_client = Client()
        response = anon_client.get(
            f"/meetings/{self.meeting.pk}/progress/"
        )
        assert response.status_code == 302
        assert "login" in response.url
