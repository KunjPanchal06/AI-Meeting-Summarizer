# AI Meeting Summarizer

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2.7-green)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## Overview
AI Meeting Summarizer is a Django web application that automatically generates concise meeting summaries from audio recordings or textual notes. It extracts key points, action items, and decisions, helping teams save time and stay organized.

## Features
- Upload or record meeting audio
- Automatic speech-to-text conversion
- Extract key points and action items
- Export summaries as text or PDF
- Simple and user-friendly web interface

## Tech Stack
- Backend: Django
- Frontend: HTML, CSS (React integration possible)
- Database: SQLite (default) / PostgreSQL (optional)
- AI/NLP: Whisper, Transformers, spaCy
- Environment: Python 3.11, virtual environment recommended

## Project Structure
```text
AI-Meeting-Summarizer/
    core/             # Django app
    templates/        # HTML templates
    static/           # CSS, JS, images
    venv/             # Virtual environment (ignored in Git)
    manage.py         # Django management script
    requirements.txt  # Python dependencies
    README.md         # Project documentation
