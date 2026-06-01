"""
Tests for core.views — upload_meeting view.

Verifies:
- Uploading a mocked audio file creates a Meeting and redirects
- process_meeting.delay is called with the correct meeting ID
- All external API calls are mocked (no real network requests)
"""

import pytest
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import Meeting


@pytest.mark.django_db
class TestUploadMeetingView:
    """Tests for the upload_meeting view."""

    def setup_method(self):
        """Create a test user and log in."""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    @patch("core.tasks.process_meeting.delay")
    def test_upload_creates_meeting_and_redirects(self, mock_delay):
        """
        POST /upload/ with a valid audio file should:
        1. Create a Meeting with status='pending'
        2. Call process_meeting.delay(meeting.pk)
        3. Redirect (302) to the processing page
        """
        mock_delay.return_value = None

        audio_file = SimpleUploadedFile(
            "meeting_audio.mp3",
            b"\x00\x01\x02\x03" * 100,  # fake audio bytes
            content_type="audio/mpeg",
        )

        response = self.client.post(
            "/upload/",
            {"title": "Sprint Review", "audio_file": audio_file},
        )

        # Should redirect to the processing page
        assert response.status_code == 302

        # Meeting should have been created
        meeting = Meeting.objects.get(title="Sprint Review")
        assert meeting.status == "pending"
        assert meeting.user == self.user

        # Redirect should point to the processing URL
        assert f"/meetings/{meeting.pk}/processing/" in response.url

        # process_meeting.delay should have been called with the meeting PK
        mock_delay.assert_called_once_with(meeting.pk)

    @patch("core.tasks.process_meeting.delay")
    def test_upload_rejects_unsupported_file_type(self, mock_delay):
        """POST /upload/ with an unsupported extension should show an error."""
        bad_file = SimpleUploadedFile(
            "document.txt",
            b"this is not audio",
            content_type="text/plain",
        )

        response = self.client.post(
            "/upload/",
            {"title": "Bad Upload", "audio_file": bad_file},
        )

        # Should render the upload page (not redirect)
        assert response.status_code == 200
        # No meeting should have been created
        assert Meeting.objects.filter(title="Bad Upload").count() == 0
        # process_meeting.delay should NOT have been called
        mock_delay.assert_not_called()

    def test_upload_requires_login(self):
        """Unauthenticated users should be redirected to the login page."""
        anon_client = Client()
        response = anon_client.post("/upload/", {"title": "Anon Upload"})
        assert response.status_code == 302
        assert "login" in response.url
