# core/models.py
from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField, HnswIndex

class Meeting(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]
    
    title = models.CharField(max_length=200)
    audio_file = models.FileField(upload_to='meetings/', null=True, blank=True)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')  
    error_message = models.TextField(blank=True, default='')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class Task(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    description = models.TextField()
    assignee = models.CharField(max_length=100, blank=True)
    deadline_text = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description[:50]}..."


class TranscriptChunk(models.Model):
    """
    Stores a chunk of meeting transcript along with its semantic embedding
    for pgvector-powered similarity search (RAG retrieval).
    """
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='chunks',
    )
    text = models.TextField(help_text="The chunk text (200-300 words).")
    embedding = VectorField(
        dimensions=384,
        help_text="384-dim embedding from all-MiniLM-L6-v2.",
    )

    class Meta:
        indexes = [
            HnswIndex(
                name='chunk_embedding_idx',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ]

    def __str__(self):
        return f"Chunk({self.meeting_id}): {self.text[:60]}..."
