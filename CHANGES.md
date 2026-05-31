# CHANGES.md — Celery + Redis Async Processing with SSE Progress

## Overview

This changeset migrates the AI meeting processing pipeline from **synchronous** (blocking the HTTP request) to **asynchronous** (Celery background tasks) with **real-time browser progress updates** via Server-Sent Events (SSE).

---

## Old vs New Flow

### Old Flow (Synchronous)

```
Browser → POST /upload/ → Django runs AI pipeline (1–5 min) → Redirect to detail page
```

- The entire pipeline (transcription → summarization → NER → action items) ran inside the Django request cycle
- The browser showed a **fake** progress overlay with hardcoded timers (3s for upload, 45s for transcription)
- Long-running requests could time out
- The user had no real visibility into processing progress

### New Flow (Asynchronous)

```
Browser → POST /upload/ → Django saves Meeting & dispatches Celery task → Redirect to /processing/
Browser → EventSource(/progress/) → SSE stream ← Redis ← Celery worker
Browser → auto-redirect to detail page on completion
```

- Upload returns immediately (~100ms) after saving the file and dispatching the task
- A dedicated processing page shows **real** progress from the actual AI pipeline
- Each stage writes its progress to Redis, which is streamed to the browser via SSE
- Auto-redirects to the detail page when processing is complete

---

## Files Created

### `meeting_summarizer/celery.py`
Initializes the Celery application. Sets `DJANGO_SETTINGS_MODULE`, creates the `Celery('meeting_summarizer')` instance, loads config from Django settings (prefixed with `CELERY_`), and auto-discovers `tasks.py` in all installed apps.

### `core/tasks.py`
Contains the `process_meeting(meeting_id)` Celery shared task. This task:
1. Fetches the Meeting from the database
2. Runs each AI pipeline stage (transcription, summarization, NER, action items)
3. After each stage, writes progress JSON to Redis via `django.core.cache`
4. Handles both audio and text-only meetings (skips transcription if transcript exists)
5. On error, sets `status='error'` and saves the error message

### `core/sse.py`
Contains the `meeting_progress_sse(request, meeting_id)` view that returns a `StreamingHttpResponse` with `content_type='text/event-stream'`. A generator function:
- Polls Redis every 0.8 seconds for progress data
- Sends heartbeat comments (`: heartbeat N`) to prevent proxy timeouts
- Formats progress as SSE data events
- Closes the stream when processing completes or errors
- Has a 5-minute safety timeout

### `core/templates/core/meeting_processing.html`
A dedicated processing page with:
- Animated hero icon with spinning ring
- Large percentage counter (0–100%)
- Gradient progress bar with glow animation
- 4-step pipeline tracker (Transcription → Summarization → Action Items → Saving)
- Elapsed timer and rotating tips
- Error card with retry button
- Vanilla JS `EventSource` that connects to the SSE endpoint and updates all UI elements in real-time

### `core/migrations/0004_meeting_error_message_alter_meeting_status.py`
Auto-generated migration that:
- Adds `error_message` TextField to Meeting model
- Updates `status` field choices to `(pending, processing, done, error)` with default `'pending'`

---

## Files Modified

### `requirements.txt`
Added: `celery==5.3.6`, `redis==5.0.1`, `django-redis==5.4.0`

### `meeting_summarizer/__init__.py`
Imports and exposes the Celery app so it loads on Django startup:
```python
from .celery import app as celery_app
__all__ = ('celery_app',)
```

### `meeting_summarizer/settings.py`
Added at the end:
- `REDIS_URL` from environment variable (fallback `redis://localhost:6379/0`)
- Celery broker/backend configuration pointing to Redis
- `django-redis` `CACHES` configuration for SSE progress data

### `core/models.py`
- Changed `STATUS_CHOICES` from `(processing, completed, failed)` to `(pending, processing, done, error)`
- Changed default status from `'processing'` to `'pending'`
- Added `error_message = TextField(blank=True, default='')`

### `core/views.py`
- `upload_meeting`: Now saves the meeting and calls `process_meeting.delay(meeting.pk)` instead of running the pipeline synchronously. Redirects to the processing page instead of the detail page.
- `process_text_meeting`: Same async pattern — saves meeting with transcript, dispatches Celery task, redirects to processing page.
- Added `meeting_processing` view: renders the waiting page, or redirects to detail if already done.
- `meeting_list`: Updated status filter values to match new choices.
- `ask_question`: Updated status check from `'completed'` to `'done'`.

### `core/urls.py`
Added two new routes:
- `meetings/<int:pk>/processing/` → `meeting_processing` view
- `meetings/<int:meeting_id>/progress/` → `meeting_progress_sse` SSE endpoint

### `core/templates/core/upload.html`
- Removed the entire `#processingOverlay` div and its ~130 lines of fake timer JavaScript
- Form submit now just disables the button and shows a spinner; the redirect happens server-side

### `core/templates/core/meeting_detail.html`
- Updated all status checks from `'completed'` to `'done'`
- Processing state now shows a "View Live Progress" button linking to the processing page
- Error state now displays `meeting.error_message` when available
- Auto-refresh replaced with redirect to processing page

### `core/templates/core/meeting_list.html`
- Updated filter chips from `completed/processing` to `done/processing/pending/error`

### `core/static/core/css/style.css`
Added ~200 lines of CSS for the processing page:
- `.processing-hero-icon` and `.processing-hero-ring` (spinning ring animation)
- `.sse-progress-track` and `.sse-progress-fill` (gradient progress bar with glow)
- `.pipeline-step`, `.pipeline-connector` (4-stage pipeline tracker)
- `.pipeline-spinner` (spinning loader for active steps)
- `.badge-done` and `.badge-error` (new status badge variants)

---

## Component Roles

| Component | Role |
|-----------|------|
| **Celery** | Distributed task queue that runs the AI pipeline in a separate worker process, freeing the Django web server to respond immediately |
| **Redis** | Serves as both the Celery message broker (task queue) and the progress data store (via django-redis cache) |
| **SSE** | Server-Sent Events — a one-directional HTTP streaming protocol that pushes real-time progress updates from Django to the browser without WebSockets |
| **Processing Page** | A dedicated UI that connects to the SSE endpoint and visualizes the pipeline progress with animations, percentage counter, and stage tracker |

---

## How to Run Locally

You need **three separate processes** running simultaneously:

### 1. Install Redis

**Option A — Docker (recommended):**
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

**Option B — WSL (Windows):**
```bash
wsl
sudo apt update && sudo apt install redis-server
sudo service redis-server start
```

**Option C — Memurai (native Windows Redis alternative):**
Download from https://www.memurai.com/ and install.

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Django
```bash
python manage.py runserver
```

### 4. Run Celery Worker (separate terminal)
```bash
celery -A meeting_summarizer worker --loglevel=info --pool=solo
```
> **Note:** `--pool=solo` is required on Windows. On Linux/Mac, omit it for better performance.

### 5. (Optional) Add REDIS_URL to .env
If Redis is not running on the default `localhost:6379`, set:
```
REDIS_URL=redis://your-redis-host:6379/0
```

### Verify everything is connected
1. Start Redis, Django, and Celery
2. Upload an audio file or paste meeting text
3. You should be redirected to the processing page with a live progress bar
4. When complete, you'll be auto-redirected to the meeting detail page
