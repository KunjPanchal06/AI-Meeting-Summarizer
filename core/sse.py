"""
Server-Sent Events (SSE) endpoint for streaming meeting processing progress.

Polls Redis cache for progress data and streams it to the browser as SSE events.
The browser connects via EventSource and receives real-time updates.
"""

import json
import time
import logging

from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Redis key pattern (must match tasks.py)
PROGRESS_KEY = "meeting:{id}:progress"

# Polling interval in seconds
POLL_INTERVAL = 0.8

# Maximum stream duration (5 minutes) to prevent zombie connections
MAX_STREAM_SECONDS = 300


def _event_stream(meeting_id):
    """
    Generator that yields SSE-formatted events.

    Polls Redis every POLL_INTERVAL seconds for progress data.
    Sends heartbeat comments to prevent proxy/load-balancer timeouts.
    Closes the stream when processing is done or an error occurs.
    """
    start_time = time.time()
    heartbeat_count = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > MAX_STREAM_SECONDS:
            # Safety timeout — close the stream
            yield _format_sse({
                "stage": "timeout",
                "pct": 0,
                "message": "Stream timed out. Please refresh the page.",
                "done": False,
                "error": True,
            })
            return

        # Read progress from Redis
        key = PROGRESS_KEY.format(id=meeting_id)
        raw = cache.get(key)

        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                data = None

            if data:
                yield _format_sse(data)

                # Close stream if done or error
                if data.get("done") or data.get("error"):
                    return
        else:
            # No progress data yet — send heartbeat to keep connection alive
            heartbeat_count += 1
            yield f": heartbeat {heartbeat_count}\n\n"

        time.sleep(POLL_INTERVAL)


def _format_sse(data):
    """Format a dict as an SSE data event."""
    return f"data: {json.dumps(data)}\n\n"


@login_required(login_url='login')
def meeting_progress_sse(request, meeting_id):
    """
    SSE endpoint that streams processing progress for a meeting.

    URL: /meetings/<meeting_id>/progress/
    Content-Type: text/event-stream

    The browser should connect via:
        const es = new EventSource('/meetings/123/progress/');
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    response = StreamingHttpResponse(
        _event_stream(meeting_id),
        content_type='text/event-stream',
    )
    # Disable buffering for real-time streaming
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # nginx
    return response
