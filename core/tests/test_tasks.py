"""
Tests for core.tasks — process_meeting Celery task (end-to-end).

Verifies the full AI pipeline with all three external HF API calls mocked:
- Whisper transcription (skipped for text-only meetings)
- BART summarization
- BERT NER entity extraction
- MiniLM embedding

Asserts after task completion:
- meeting.status == "done"
- transcript is saved
- summary is saved
- at least one Task (action item) is created
- Redis progress key exists with pct == 100
"""

import json

import pytest
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache

from core.models import Meeting, Task as MeetingTask
from core.tasks import process_meeting, PROGRESS_KEY


# Sample transcript long enough to trigger summarization & NER
SAMPLE_TRANSCRIPT = (
    "John will prepare the quarterly report by Friday. "
    "Sarah should update the marketing dashboard with new metrics. "
    "The development team needs to fix the login bug before the release. "
    "Action item: Mike to review the security audit findings. "
    "Alice will schedule a follow-up meeting for next Monday. "
    "We discussed the budget allocation for Q3 and agreed on the final numbers. "
    "The sales team should contact the new leads by end of week. "
    "Bob must finalize the vendor contract before the deadline. "
    "Task: Update the project timeline with the new milestones. "
    "Everyone should review the updated company policies by next Wednesday."
)


@pytest.mark.django_db
class TestProcessMeetingTask:
    """End-to-end tests for the process_meeting Celery task."""

    @patch("core.hf_client.embed_text")
    @patch("core.hf_client.extract_entities")
    @patch("core.hf_client.summarize_text")
    def test_process_text_meeting_end_to_end(
        self,
        mock_summarize,
        mock_ner,
        mock_embed,
    ):
        """
        Process a text-only meeting (transcript already provided).
        All HF API calls are mocked.
        """
        # ── Mock returns ─────────────────────────────────────────
        mock_summary = "Team discussed Q3 plans, action items were assigned."
        mock_summarize.return_value = mock_summary

        # extract_entities returns NER results
        mock_ner.return_value = [
            {"entity_group": "PER", "score": 0.99, "word": "John", "start": 0, "end": 4},
            {"entity_group": "PER", "score": 0.98, "word": "Sarah", "start": 50, "end": 55},
        ]

        # embed_text returns 384-dim vectors (one per input text)
        dummy_vector = [0.1] * 384
        mock_embed.return_value = [dummy_vector]

        # ── Create meeting with pre-filled transcript ────────────
        user = User.objects.create_user(username="taskuser", password="pass1234")
        meeting = Meeting.objects.create(
            title="Q3 Planning",
            transcript=SAMPLE_TRANSCRIPT,
            status="pending",
            user=user,
        )

        # ── Run the task synchronously ───────────────────────────
        process_meeting(meeting.pk)

        # ── Assertions ───────────────────────────────────────────
        meeting.refresh_from_db()

        # Status should be "done"
        assert meeting.status == "done"

        # Transcript should still be there
        assert len(meeting.transcript) > 0
        assert "John" in meeting.transcript

        # Summary should be saved
        assert len(meeting.summary) > 0

        # At least one action item (Task) should have been created
        tasks = MeetingTask.objects.filter(meeting=meeting)
        assert tasks.count() >= 1

        # Redis progress key should exist with pct == 100
        key = PROGRESS_KEY.format(id=meeting.pk)
        raw = cache.get(key)
        assert raw is not None
        progress = json.loads(raw)
        assert progress["pct"] == 100
        assert progress["done"] is True

    @patch("core.hf_client.embed_text")
    @patch("core.hf_client.extract_entities")
    @patch("core.hf_client.summarize_text")
    def test_process_meeting_error_handling(
        self,
        mock_summarize,
        mock_ner,
        mock_embed,
    ):
        """When embedding fails, the meeting status should be 'error'."""
        # Summarization and NER succeed
        mock_summarize.return_value = "A summary."
        mock_ner.return_value = [
            {"entity_group": "PER", "score": 0.99, "word": "John", "start": 0, "end": 4},
        ]
        # embed_text is called directly in task code (not wrapped by AI processor)
        # so raising here will be caught by the task's top-level exception handler
        mock_embed.side_effect = RuntimeError("Embedding API unavailable")

        meeting = Meeting.objects.create(
            title="Failing Meeting",
            transcript=SAMPLE_TRANSCRIPT,
            status="pending",
        )

        process_meeting(meeting.pk)

        meeting.refresh_from_db()
        assert meeting.status == "error"
        assert "Embedding API unavailable" in meeting.error_message

