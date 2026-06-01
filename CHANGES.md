# CHANGES: TF-IDF → pgvector Semantic Search Migration

> **Date:** 2026-06-01  
> **Scope:** Replace keyword-based TF-IDF RAG retrieval with semantic vector search using pgvector and `all-MiniLM-L6-v2` embeddings.

---

## Files Created or Modified

### Modified Files

| File | What Changed | Why |
|------|-------------|-----|
| `requirements.txt` | Added `pgvector`, `psycopg2-binary`. Removed `scikit-learn`, `scipy`, `joblib`, `threadpoolctl`. | pgvector Python bindings and PostgreSQL adapter are needed; sklearn dependencies were only used for TF-IDF and are no longer needed. |
| `.env` | Added `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` variables. | PostgreSQL connection credentials (pgvector requires PostgreSQL; SQLite doesn't support extensions). |
| `meeting_summarizer/settings.py` | Switched `DATABASES` engine from `django.db.backends.sqlite3` to `django.db.backends.postgresql`. | pgvector is a PostgreSQL extension and cannot run on SQLite. |
| `core/models.py` | Added `TranscriptChunk` model with `meeting` (FK), `text` (TextField), and `embedding` (VectorField, 384 dimensions). Added HNSW index on the embedding column. | Stores pre-computed transcript chunks and their vector embeddings for fast cosine-similarity retrieval at query time. |
| `core/hf_client.py` | Added `sentence-transformers/all-MiniLM-L6-v2` to the `MODELS` dict. Added `embed_text()` function. | Provides a unified API call for generating 384-dimensional sentence embeddings, reusing the existing HF Inference API client with retry logic. |
| `core/tasks.py` | Added Stage 4 (Embedding) between action-item extraction and result saving. Includes `_chunk_transcript()` helper. | After a meeting is processed, the transcript is split into overlapping chunks, embedded via HF API, and stored as `TranscriptChunk` rows so the RAG system can query them later. |
| `core/rag_processor.py` | **Complete rewrite.** Removed all TF-IDF/sklearn code. New logic: embed question → pgvector cosine search → Groq LLM answer. | The core change: replaced keyword matching with semantic understanding for dramatically better retrieval quality. |
| `core/views.py` | Changed `ask_question()` view to pass `meeting.id` to `rag.ask_question()` instead of `meeting.transcript, meeting.summary`. | The new RAG processor retrieves chunks from the database by meeting ID instead of receiving raw text each time. |

### Created Files

| File | Purpose |
|------|---------|
| `core/migrations/0005_transcriptchunk.py` | Django migration that creates the `vector` PostgreSQL extension and the `core_transcriptchunk` table with an HNSW index on the embedding column. |
| `CHANGES.md` | This file — documents all changes made during the migration. |

---

## Old TF-IDF Retrieval vs. New pgvector Semantic Search

### How TF-IDF Worked (Old)

```
User asks question
        │
        ▼
┌─────────────────────────┐
│ Combine transcript +    │
│ summary into one string │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Split into 200-word     │
│ chunks (on every call)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ TF-IDF vectorize all    │
│ chunks + question       │
│ (sklearn TfidfVectorizer│
│  re-fitted every call)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Cosine similarity       │
│ (sklearn) → top 3 chunks│
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Send chunks + question  │
│ to Groq/Llama → answer  │
└─────────────────────────┘
```

**Limitations:**
- **Keyword-based:** TF-IDF matches words, not meaning. "What was the budget?" won't find "We allocated $50K for marketing" because they share no keywords.
- **Re-computed every call:** Chunks and TF-IDF vectors were rebuilt from scratch on every question — no caching.
- **No persistence:** Nothing was stored in the database; the full transcript had to be loaded and processed each time.

### How pgvector Semantic Search Works (New)

```
┌─── At Processing Time (Celery Task) ───┐
│                                         │
│  Transcript                             │
│       │                                 │
│       ▼                                 │
│  Split into 250-word overlapping chunks │
│       │                                 │
│       ▼                                 │
│  Embed each chunk via HF API           │
│  (all-MiniLM-L6-v2 → 384-dim vectors) │
│       │                                 │
│       ▼                                 │
│  Save to TranscriptChunk table         │
│  (text + embedding stored in Postgres) │
└─────────────────────────────────────────┘

┌─── At Query Time ──────────────────────┐
│                                         │
│  User's question                        │
│       │                                 │
│       ▼                                 │
│  Embed question via HF API             │
│  (same all-MiniLM-L6-v2 model)        │
│       │                                 │
│       ▼                                 │
│  pgvector cosine distance query        │
│  (filtered by meeting_id, top 4)       │
│       │                                 │
│       ▼                                 │
│  Concatenate chunk texts as context    │
│       │                                 │
│       ▼                                 │
│  Send to Groq/Llama → answer           │
│  (identical prompt, no changes)        │
└─────────────────────────────────────────┘
```

**Advantages:**
- **Semantic understanding:** Finds conceptually similar content even when exact words don't match.
- **Pre-computed:** Embeddings are generated once during meeting processing; queries are instant database lookups.
- **Indexed:** The HNSW index on the vector column enables sub-millisecond approximate nearest-neighbor search even with thousands of chunks.

---

## Role of Each New Component

### pgvector (PostgreSQL Extension)

pgvector adds native vector data types and similarity-search operators to PostgreSQL. It stores 384-dimensional float vectors alongside regular relational data, and provides:
- `vector` column type for storing embeddings
- `<=>` operator for cosine distance
- HNSW and IVFFlat index types for fast approximate nearest-neighbor search

### all-MiniLM-L6-v2 (Sentence Transformer Model)

A compact sentence embedding model from the `sentence-transformers` family. It maps any text (up to 256 tokens) to a 384-dimensional dense vector that captures semantic meaning. Two texts with similar meaning will have vectors with high cosine similarity, regardless of whether they share exact words.

We call this model via the **HuggingFace Inference API** (not locally) — consistent with how the project already uses Whisper, BART, and BERT-NER.

### TranscriptChunk Model

A Django model that stores:
- `meeting` — Foreign key linking the chunk to its source meeting
- `text` — The raw chunk text (200-300 words)
- `embedding` — A 384-dimensional vector (pgvector `VectorField`)

This model acts as the bridge between the meeting processing pipeline (which generates the data) and the RAG query system (which retrieves it).

---

## How Embeddings Are Generated and Stored

During the Celery background task (`core/tasks.py`), after summarization and action-item extraction:

1. **Chunking:** The `_chunk_transcript()` function splits the full transcript into overlapping chunks of ~250 words with 50-word overlap. Overlap ensures that no important context is lost at chunk boundaries.

2. **Batched Embedding:** Chunks are sent to the HuggingFace Inference API in batches of 16 via `hf_client.embed_text()`. The API returns a list of 384-dimensional float vectors, one per input text.

3. **Bulk Storage:** Each chunk and its vector are saved as a `TranscriptChunk` row using Django's `bulk_create()` for efficiency. The HNSW index is automatically maintained by PostgreSQL.

4. **Progress Reporting:** The embedding stage reports progress to Redis (75% → 90%) so the SSE-powered progress UI keeps the user informed.

---

## How Retrieval Works at Query Time

When a user submits a question on the meeting detail page:

1. **Question Embedding:** The user's question is sent to the same `all-MiniLM-L6-v2` model via `hf_client.embed_text(question)`, producing a single 384-dim vector.

2. **Vector Search:** The `MeetingRAGProcessor._retrieve_chunks()` method runs a Django ORM query:
   ```python
   TranscriptChunk.objects
       .filter(meeting_id=meeting_id)
       .annotate(distance=CosineDistance('embedding', question_embedding))
       .order_by('distance')[:4]
   ```
   This translates to a SQL query using pgvector's `<=>` cosine distance operator, filtered to only chunks belonging to the current meeting, returning the 4 closest matches.

3. **Context Assembly:** The text of the top 4 chunks is concatenated with `---` separators.

4. **Answer Generation:** The assembled context + question are sent to the Groq API (Llama 3.3 70B) using the exact same prompt template as before. Nothing about the LLM call changed — only how we select which chunks to include.

5. **Response:** The answer and source snippets (with relevance scores) are returned as JSON to the frontend.
