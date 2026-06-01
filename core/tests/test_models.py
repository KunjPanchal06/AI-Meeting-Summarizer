"""
Tests for core.models — Meeting, Task, TranscriptChunk.

Verifies:
- Meeting creation with all fields and default status
- Task creation linked to a meeting
- TranscriptChunk stores text and a 384-dim embedding vector
"""

import pytest
from django.contrib.auth.models import User

from core.models import Meeting, Task, TranscriptChunk


@pytest.mark.django_db
class TestMeetingModel:
    """Tests for the Meeting model."""

    def test_create_meeting_with_all_fields(self):
        """A Meeting can be created with all fields populated."""
        user = User.objects.create_user(username="testuser", password="pass1234")
        meeting = Meeting.objects.create(
            title="Sprint Planning",
            transcript="We discussed the roadmap for Q3.",
            summary="Roadmap discussion.",
            status="done",
            user=user,
        )
        meeting.refresh_from_db()

        assert meeting.title == "Sprint Planning"
        assert meeting.transcript == "We discussed the roadmap for Q3."
        assert meeting.summary == "Roadmap discussion."
        assert meeting.status == "done"
        assert meeting.user == user
        assert meeting.created_at is not None
        assert meeting.updated_at is not None

    def test_status_defaults_to_pending(self):
        """Meeting.status should default to 'pending' when not specified."""
        meeting = Meeting.objects.create(title="Quick Sync")
        meeting.refresh_from_db()

        assert meeting.status == "pending"

    def test_str_representation(self):
        """Meeting.__str__ returns the title."""
        meeting = Meeting.objects.create(title="Retrospective")
        assert str(meeting) == "Retrospective"


@pytest.mark.django_db
class TestTaskModel:
    """Tests for the Task model."""

    def test_create_task(self):
        """A Task can be created and linked to a Meeting."""
        meeting = Meeting.objects.create(title="Standup")
        task = Task.objects.create(
            meeting=meeting,
            description="Update the Jira board with new tickets",
            assignee="Alice",
            deadline_text="by Friday",
            status="pending",
        )
        task.refresh_from_db()

        assert task.meeting == meeting
        assert task.description == "Update the Jira board with new tickets"
        assert task.assignee == "Alice"
        assert task.deadline_text == "by Friday"
        assert task.status == "pending"


@pytest.mark.django_db
class TestTranscriptChunkModel:
    """Tests for the TranscriptChunk model (pgvector)."""

    def test_create_chunk_with_vector(self):
        """TranscriptChunk stores text and a 384-dimensional embedding."""
        meeting = Meeting.objects.create(title="Design Review")
        vector = [0.1] * 384  # 384-dim dummy embedding

        chunk = TranscriptChunk.objects.create(
            meeting=meeting,
            text="We reviewed the new landing page mockup and discussed colors.",
            embedding=vector,
        )
        chunk.refresh_from_db()

        assert chunk.meeting == meeting
        assert chunk.text.startswith("We reviewed")
        # pgvector stores the vector; length should be 384
        assert len(chunk.embedding) == 384

    def test_chunk_str_representation(self):
        """TranscriptChunk.__str__ shows a truncated preview."""
        meeting = Meeting.objects.create(title="All Hands")
        chunk = TranscriptChunk.objects.create(
            meeting=meeting,
            text="The CEO presented quarterly results and future plans for expansion.",
            embedding=[0.0] * 384,
        )
        result = str(chunk)
        assert result.startswith("Chunk(")
        assert "..." in result
