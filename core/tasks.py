"""
Celery background task for processing meetings asynchronously.

Runs the full AI pipeline (transcription → summarization → NER → action items → embedding)
and writes stage-by-stage progress to Redis for SSE consumption.
"""

import json
import logging
import os

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Redis key pattern for progress data
PROGRESS_KEY = "meeting:{id}:progress"

# Progress expiry (10 minutes — plenty of time for SSE to read)
PROGRESS_TTL = 600


def _set_progress(meeting_id, stage, pct, message, done=False, error=False):
    """Write progress JSON to Redis cache."""
    data = {
        "stage": stage,
        "pct": pct,
        "message": message,
        "done": done,
        "error": error,
    }
    key = PROGRESS_KEY.format(id=meeting_id)
    cache.set(key, json.dumps(data), timeout=PROGRESS_TTL)
    logger.info(f"Progress [{meeting_id}]: {stage} — {pct}% — {message}")


def _chunk_transcript(text, chunk_size=250, overlap=50):
    """
    Split transcript into overlapping word chunks of 200-300 words.

    Args:
        text: The full transcript text.
        chunk_size: Target number of words per chunk (default 250, within 200-300 range).
        overlap: Number of overlapping words between consecutive chunks.

    Returns:
        List of chunk strings.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


@shared_task(bind=True, max_retries=0)
def process_meeting(self, meeting_id):
    """
    Full async AI pipeline for a meeting.

    Handles both audio meetings (transcription → summarization → action items → embedding)
    and text-only meetings (summarization → action items → embedding, skip transcription).

    Progress is written to Redis at each stage for the SSE endpoint to stream.
    """
    from core.models import Meeting, Task as MeetingTask, TranscriptChunk
    from core.ai_processor import MeetingAIProcessor
    from core import hf_client

    try:
        meeting = Meeting.objects.get(pk=meeting_id)
    except Meeting.DoesNotExist:
        logger.error(f"Meeting {meeting_id} not found.")
        return

    # Mark as processing
    meeting.status = "processing"
    meeting.save(update_fields=["status"])

    # Determine if this is an audio or text-only meeting
    has_audio = bool(meeting.audio_file)
    has_transcript = bool(meeting.transcript.strip())

    try:
        processor = MeetingAIProcessor()

        # ── Stage 1: Transcription (audio only) ─────────────────────
        if has_audio and not has_transcript:
            _set_progress(meeting_id, "transcription", 5, "Starting audio transcription…")

            audio_path = os.path.join(settings.MEDIA_ROOT, str(meeting.audio_file))
            transcript = processor.convert_audio_to_text(audio_path)

            if not transcript:
                raise RuntimeError("Audio transcription failed — no text returned.")

            meeting.transcript = transcript
            meeting.save(update_fields=["transcript"])
            _set_progress(meeting_id, "transcription", 30, "Transcription complete!")
        else:
            # Text-only meeting — transcript already exists
            transcript = meeting.transcript
            _set_progress(meeting_id, "transcription", 30, "Using provided transcript.")

        # ── Stage 2: Summarization ───────────────────────────────────
        _set_progress(meeting_id, "summarization", 35, "Generating summary…")

        summary = processor.generate_summary(transcript)
        meeting.summary = summary
        meeting.save(update_fields=["summary"])

        _set_progress(meeting_id, "summarization", 55, "Summary generated!")

        # ── Stage 3: NER & Action Items ──────────────────────────────
        _set_progress(meeting_id, "extraction", 60, "Extracting action items…")

        action_items = processor.extract_action_items(transcript)

        _set_progress(meeting_id, "extraction", 70, f"Found {len(action_items)} action items.")

        # ── Stage 4: Embedding Transcript Chunks ─────────────────────
        _set_progress(meeting_id, "embedding", 72, "Splitting transcript into chunks…")

        # Delete any existing chunks for this meeting (in case of reprocessing)
        TranscriptChunk.objects.filter(meeting=meeting).delete()

        chunks = _chunk_transcript(transcript)
        total_chunks = len(chunks)
        logger.info(f"Meeting {meeting_id}: {total_chunks} chunks to embed.")

        _set_progress(
            meeting_id, "embedding", 75,
            f"Embedding {total_chunks} chunks…",
        )

        # Embed in batches (HF API can handle batched inputs)
        BATCH_SIZE = 16
        saved_count = 0
        for batch_start in range(0, total_chunks, BATCH_SIZE):
            batch_texts = chunks[batch_start : batch_start + BATCH_SIZE]
            batch_vectors = hf_client.embed_text(batch_texts)

            chunk_objects = []
            for text, vector in zip(batch_texts, batch_vectors):
                chunk_objects.append(
                    TranscriptChunk(
                        meeting=meeting,
                        text=text,
                        embedding=vector,
                    )
                )

            TranscriptChunk.objects.bulk_create(chunk_objects)
            saved_count += len(chunk_objects)

            # Report batch progress (75% → 90% during embedding)
            embed_pct = 75 + int((saved_count / total_chunks) * 15)
            _set_progress(
                meeting_id, "embedding", embed_pct,
                f"Embedded {saved_count}/{total_chunks} chunks…",
            )

        _set_progress(meeting_id, "embedding", 90, f"All {total_chunks} chunks embedded!")

        # ── Stage 5: Saving Results ──────────────────────────────────
        _set_progress(meeting_id, "saving", 92, "Saving action items…")

        for item in action_items:
            MeetingTask.objects.create(
                meeting=meeting,
                description=item.get("description", ""),
                assignee=item.get("assignee", ""),
                deadline_text=item.get("deadline", ""),
                status=item.get("status", "pending"),
            )

        meeting.status = "done"
        meeting.save(update_fields=["status"])

        _set_progress(meeting_id, "done", 100, "Processing complete!", done=True)
        logger.info(f"Meeting {meeting_id} processed successfully.")

    except Exception as exc:
        logger.error(f"Error processing meeting {meeting_id}: {exc}", exc_info=True)

        meeting.status = "error"
        meeting.error_message = str(exc)
        meeting.save(update_fields=["status", "error_message"])

        _set_progress(
            meeting_id, "error", 0,
            f"Processing failed: {str(exc)[:200]}",
            done=False, error=True,
        )
