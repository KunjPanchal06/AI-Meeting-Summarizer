import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq
from django.conf import settings as django_settings


class MeetingRAGProcessor:
    """
    RAG (Retrieval-Augmented Generation) processor for meeting Q&A.
    Uses TF-IDF for chunk retrieval and Groq API for answer generation.
    """

    def __init__(self):
        api_key = getattr(django_settings, 'GROQ_API_KEY', None) or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not configured. Set it in settings.py or as an environment variable.")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def chunk_text(self, text, chunk_size=200, overlap=50):
        """Split text into overlapping word chunks for better retrieval."""
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

    def find_relevant_chunks(self, question, chunks, top_k=3):
        """Find the most relevant text chunks using TF-IDF + cosine similarity."""
        if not chunks:
            return []

        # Combine question with chunks for TF-IDF vectorization
        all_texts = [question] + chunks
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(all_texts)

        # Compute similarity between question (first) and all chunks
        question_vec = tfidf_matrix[0:1]
        chunk_vecs = tfidf_matrix[1:]
        similarities = cosine_similarity(question_vec, chunk_vecs).flatten()

        # Get top-k most similar chunks
        top_k = min(top_k, len(chunks))
        top_indices = similarities.argsort()[-top_k:][::-1]

        # Filter out chunks with zero similarity
        relevant = []
        for idx in top_indices:
            if similarities[idx] > 0:
                relevant.append({
                    "text": chunks[idx],
                    "score": float(similarities[idx]),
                })

        return relevant

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

    def ask_question(self, transcript, summary, question):
        """
        Full RAG pipeline: chunk → retrieve → generate answer.
        Uses both transcript and summary for better context.
        """
        # Combine transcript and summary for richer context
        full_text = f"Meeting Summary:\n{summary}\n\nFull Transcript:\n{transcript}"

        # Step 1: Chunk the text
        chunks = self.chunk_text(full_text)

        # Step 2: Find relevant chunks
        relevant_chunks = self.find_relevant_chunks(question, chunks, top_k=4)

        if not relevant_chunks:
            return {
                "answer": "I couldn't find relevant information in this meeting to answer your question. Try rephrasing or asking something else.",
                "sources": [],
            }

        # Step 3: Generate answer
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
