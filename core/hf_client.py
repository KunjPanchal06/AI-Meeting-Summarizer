# MIGRATED: HuggingFace Inference API client
# Replaces local whisper, transformers, and spacy models

import os
import time
import json
import requests
import logging

logger = logging.getLogger(__name__)

HF_TOKEN = os.environ.get("HF_TOKEN", "")

API_BASE = "https://router.huggingface.co/hf-inference/models"

MODELS = {
    "whisper": f"{API_BASE}/openai/whisper-large-v3",
    "summarizer": f"{API_BASE}/facebook/bart-large-cnn",
    "ner": f"{API_BASE}/dslim/bert-base-NER",
}


def _get_headers():
    """Return authorization headers for HF API."""
    if not HF_TOKEN:
        raise ValueError(
            "HF_TOKEN is not set. Add it to your .env file. "
            "Get a token at https://huggingface.co/settings/tokens"
        )
    return {"Authorization": f"Bearer {HF_TOKEN}"}


def call_hf_api(url, payload=None, data=None, content_type=None, max_retries=5):
    """
    Make a request to the HuggingFace Inference API with retry logic.

    - Retries up to `max_retries` times on 503 (model cold start).
    - Waits for `estimated_time` returned in the 503 response.
    - Raises a clear exception on other errors.

    Args:
        url: The HF API endpoint URL.
        payload: JSON payload (for text-based models).
        data: Binary data (for audio models).
        content_type: MIME type for binary data (e.g. "audio/wav").
        max_retries: Maximum number of retries on 503.

    Returns:
        Parsed JSON response from the API.
    """
    headers = _get_headers()

    for attempt in range(1, max_retries + 1):
        try:
            if data is not None:
                if content_type:
                    headers["Content-Type"] = content_type
                response = requests.post(url, headers=headers, data=data)
            else:
                headers["Content-Type"] = "application/json"
                response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                return response.json()

            if response.status_code == 503:
                # Model is loading (cold start)
                try:
                    body = response.json()
                    wait_time = body.get("estimated_time", 20)
                except Exception:
                    wait_time = 20

                logger.warning(
                    f"Model loading (attempt {attempt}/{max_retries}). "
                    f"Waiting {wait_time:.0f}s..."
                )
                time.sleep(wait_time)
                continue

            # Other errors — raise immediately
            error_msg = f"HF API error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries:
                logger.warning(f"Connection error (attempt {attempt}): {e}")
                time.sleep(5)
                continue
            raise

    raise RuntimeError(
        f"HF API failed after {max_retries} retries. "
        "The model may be unavailable. Try again later."
    )


# ─── Task-Specific Functions ────────────────────────────────────────────


# Map file extensions to MIME types for audio uploads
_AUDIO_MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".m4a": "audio/m4a",
    ".amr": "audio/amr",
}


def transcribe_audio(file_path):
    """
    Transcribe an audio file using openai/whisper-large-v3.

    Args:
        file_path: Path to the audio file.

    Returns:
        Transcribed text string, or None on failure.
    """
    logger.info(f"Sending audio to HF Whisper API: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    content_type = _AUDIO_MIME_TYPES.get(ext, "audio/wav")
    logger.info(f"Detected content type: {content_type}")

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    result = call_hf_api(MODELS["whisper"], data=audio_bytes, content_type=content_type)

    if isinstance(result, dict) and "text" in result:
        return result["text"].strip()

    logger.error(f"Unexpected Whisper API response: {result}")
    return None


def summarize_text(text, max_length=150, min_length=30):
    """
    Summarize text using facebook/bart-large-cnn.

    Args:
        text: The text to summarize.
        max_length: Maximum summary length in tokens.
        min_length: Minimum summary length in tokens.

    Returns:
        Summary text string.
    """
    logger.info("Sending text to HF Summarization API...")

    payload = {
        "inputs": text,
        "parameters": {
            "max_length": max_length,
            "min_length": min_length,
            "do_sample": False,
            "truncation": "only_first",
        },
    }

    result = call_hf_api(MODELS["summarizer"], payload=payload)

    if isinstance(result, list) and len(result) > 0:
        return result[0].get("summary_text", "").strip()

    logger.error(f"Unexpected Summarization API response: {result}")
    return ""


def extract_entities(text):
    """
    Extract named entities using dslim/bert-base-NER.

    Supported entity types: PER (person), ORG, LOC, MISC.

    Args:
        text: The text to analyze.

    Returns:
        List of entity dicts with keys: entity_group, score, word, start, end.
        Returns empty list on failure.
    """
    logger.info("Sending text to HF NER API...")

    payload = {"inputs": text}

    try:
        result = call_hf_api(MODELS["ner"], payload=payload)

        if isinstance(result, list):
            return result

        logger.error(f"Unexpected NER API response: {result}")
        return []

    except Exception as e:
        logger.error(f"NER API error: {e}")
        return []
