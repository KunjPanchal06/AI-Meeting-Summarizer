import os
import logging

from groq import Groq
from django.conf import settings as django_settings
from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)


class MeetingRAGProcessor:
    """
    RAG (Retrieval-Augmented Generation) processor for meeting Q&A.
    Uses pgvector cosine-similarity search for chunk retrieval
    and Groq API for answer generation.
    """

    def __init__(self):
        api_key = getattr(django_settings, 'GROQ_API_KEY', None) or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not configured. Set it in settings.py or as an environment variable.")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def _retrieve_chunks(self, meeting_id, question_embedding, top_k=4):
        """
        Retrieve the top-k most semantically similar transcript chunks
        from the database using pgvector cosine distance.

        Args:
            meeting_id: The ID of the meeting to search within.
            question_embedding: The 384-dim embedding vector for the user's question.
            top_k: Number of closest chunks to return (default 4).

        Returns:
            List of dicts with 'text' and 'score' keys.
        """
        from core.models import TranscriptChunk

        results = (
            TranscriptChunk.objects
            .filter(meeting_id=meeting_id)
            .annotate(distance=CosineDistance('embedding', question_embedding))
            .order_by('distance')[:top_k]
        )

        chunks = []
        for chunk in results:
            # Cosine distance → cosine similarity = 1 - distance
            chunks.append({
                "text": chunk.text,
                "score": round(1.0 - chunk.distance, 4),
            })

        return chunks

    def generate_answer(self, question, context_chunks):
        """Generate an answer using Groq API with retrieved context."""
        context = "\n\n---\n\n".join([c["text"] for c in context_chunks])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that answers questions about meetings. "
                    "You MUST answer based ONLY on the provided meeting context. "
                    "If the context doesn't contain enough information to answer, say so clearly. "
                    "Keep your answers concise and to the point. "
                    "Do not make up information that is not in the context."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Meeting Context:\n{context}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer based on the meeting context above:"
                ),
            },
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=512,
        )

        return response.choices[0].message.content.strip()

    def ask_question(self, meeting_id, question):
        """
        Full RAG pipeline: embed question → vector search → generate answer.

        Args:
            meeting_id: The database ID of the meeting to query.
            question: The user's natural-language question.

        Returns:
            Dict with 'answer' and 'sources' keys.
        """
        from core import hf_client
        from core.models import TranscriptChunk

        # Verify that embeddings exist for this meeting
        chunk_count = TranscriptChunk.objects.filter(meeting_id=meeting_id).count()
        if chunk_count == 0:
            return {
                "answer": (
                    "No transcript chunks have been embedded for this meeting yet. "
                    "Please wait for processing to complete, or reprocess the meeting."
                ),
                "sources": [],
            }

        # Step 1: Embed the user's question
        question_vectors = hf_client.embed_text(question)
        question_embedding = question_vectors[0]

        # Step 2: Retrieve top 4 most similar chunks via pgvector
        relevant_chunks = self._retrieve_chunks(meeting_id, question_embedding, top_k=4)

        if not relevant_chunks:
            return {
                "answer": "I couldn't find relevant information in this meeting to answer your question. Try rephrasing or asking something else.",
                "sources": [],
            }

        # Step 3: Generate answer using Groq
        answer = self.generate_answer(question, relevant_chunks)

        # Format sources (truncate for display)
        sources = []
        for chunk in relevant_chunks:
            text = chunk["text"]
            if len(text) > 200:
                text = text[:200] + "..."
            sources.append({
                "text": text,
                "relevance": round(chunk["score"] * 100, 1),
            })

        return {
            "answer": answer,
            "sources": sources,
        }
