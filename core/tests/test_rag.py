"""
Tests for core.rag_processor — MeetingRAGProcessor.

Verifies the RAG pipeline with mocked external calls:
- HF embedding API (core.hf_client.embed_text)
- pgvector similarity query (TranscriptChunk queryset)
- Groq chat completion API

Asserts:
- Correct chunks are retrieved and passed to Groq
- Groq receives the right context in its messages
- The response contains an answer and sources
"""

import pytest
from unittest.mock import patch, MagicMock

from core.models import Meeting, TranscriptChunk


@pytest.mark.django_db
class TestMeetingRAGProcessor:
    """Tests for the RAG Q&A pipeline."""

    @patch("core.rag_processor.Groq")
    @patch("core.hf_client.embed_text")
    def test_ask_question_full_pipeline(self, mock_embed, mock_groq_cls):
        """
        Full RAG pipeline: embed question → vector search → generate answer.
        All external calls are mocked.
        """
        # ── Setup ────────────────────────────────────────────────
        meeting = Meeting.objects.create(
            title="Architecture Review",
            transcript="We discussed microservices migration and API gateway.",
            status="done",
        )

        # Create real TranscriptChunk objects in the DB so the ORM query works
        dummy_vector = [0.1] * 384
        TranscriptChunk.objects.create(
            meeting=meeting,
            text="We discussed migrating to microservices architecture.",
            embedding=dummy_vector,
        )
        TranscriptChunk.objects.create(
            meeting=meeting,
            text="The API gateway will handle authentication and rate limiting.",
            embedding=[0.2] * 384,
        )

        # Mock embed_text to return a known question embedding
        question_embedding = [0.15] * 384
        mock_embed.return_value = [question_embedding]

        # Mock Groq client
        mock_groq_instance = MagicMock()
        mock_groq_cls.return_value = mock_groq_instance

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The team discussed migrating to microservices."
        mock_groq_instance.chat.completions.create.return_value = mock_response

        # ── Execute ──────────────────────────────────────────────
        from core.rag_processor import MeetingRAGProcessor
        processor = MeetingRAGProcessor()

        result = processor.ask_question(meeting.id, "What architecture was discussed?")

        # ── Assert ───────────────────────────────────────────────
        # embed_text should have been called with the question
        mock_embed.assert_called_once_with("What architecture was discussed?")

        # Groq should have been called
        mock_groq_instance.chat.completions.create.assert_called_once()
        call_kwargs = mock_groq_instance.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")

        # The user message should contain the chunk text as context
        user_message = messages[1]["content"]
        assert "microservices" in user_message.lower()

        # Response should have answer and sources
        assert "answer" in result
        assert "sources" in result
        assert len(result["answer"]) > 0
        assert len(result["sources"]) > 0

    @patch("core.rag_processor.Groq")
    @patch("core.hf_client.embed_text")
    def test_ask_question_no_chunks(self, mock_embed, mock_groq_cls):
        """When no chunks exist, return an informative message (no Groq call)."""
        meeting = Meeting.objects.create(
            title="Empty Meeting",
            transcript="Nothing transcribed.",
            status="done",
        )

        # Mock Groq (shouldn't be called)
        mock_groq_instance = MagicMock()
        mock_groq_cls.return_value = mock_groq_instance

        from core.rag_processor import MeetingRAGProcessor
        processor = MeetingRAGProcessor()

        result = processor.ask_question(meeting.id, "What happened?")

        # Should return a helpful message without calling Groq
        assert "answer" in result
        assert "no transcript chunks" in result["answer"].lower()
        mock_groq_instance.chat.completions.create.assert_not_called()

    @patch("core.rag_processor.Groq")
    @patch("core.hf_client.embed_text")
    def test_groq_receives_correct_context(self, mock_embed, mock_groq_cls):
        """Verify the exact context format sent to Groq."""
        meeting = Meeting.objects.create(title="Context Test", status="done")

        chunk_text = "Budget approved for $500k. Marketing gets 40%, Engineering gets 60%."
        TranscriptChunk.objects.create(
            meeting=meeting,
            text=chunk_text,
            embedding=[0.5] * 384,
        )

        mock_embed.return_value = [[0.5] * 384]

        mock_groq_instance = MagicMock()
        mock_groq_cls.return_value = mock_groq_instance
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Budget is $500k."
        mock_groq_instance.chat.completions.create.return_value = mock_response

        from core.rag_processor import MeetingRAGProcessor
        processor = MeetingRAGProcessor()

        processor.ask_question(meeting.id, "What is the budget?")

        # Verify Groq received the chunk text in the context
        call_kwargs = mock_groq_instance.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")

        # System message should instruct about meeting context
        assert "meeting" in messages[0]["content"].lower()

        # User message should contain the actual chunk text
        assert chunk_text in messages[1]["content"]
