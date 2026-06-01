from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import json
import os

from .models import Meeting, Task

# Lazy-load AI processors (only initialized when first used)
_ai_processor = None
_rag_processor = None

def get_ai_processor():
    global _ai_processor
    if _ai_processor is None:
        from .ai_processor import MeetingAIProcessor
        _ai_processor = MeetingAIProcessor()
    return _ai_processor

def get_rag_processor():
    global _rag_processor
    if _rag_processor is None:
        from .rag_processor import MeetingRAGProcessor
        _rag_processor = MeetingRAGProcessor()
    return _rag_processor

@login_required(login_url='login')
def home(request):
    recent_meetings = Meeting.objects.filter(user=request.user).order_by('-created_at')[:5]
    total_tasks = Task.objects.filter(meeting__user=request.user).count()
    completed_tasks = Task.objects.filter(meeting__user=request.user, status='completed').count()
    context = {
        'recent_meetings': recent_meetings,
        'total_meetings': Meeting.objects.filter(user=request.user).count(),
        'completed_tasks': completed_tasks,
        'total_tasks': total_tasks,
    }
    return render(request, 'core/home.html', context)

@login_required(login_url='login')
def upload_meeting(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        audio_file = request.FILES.get('audio_file')

        if title and audio_file:
            # Validate file extension
            allowed_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm']
            file_ext = os.path.splitext(audio_file.name)[1].lower()
            if file_ext not in allowed_extensions:
                messages.error(request, f'Unsupported file type "{file_ext}". Allowed: {", ".join(allowed_extensions)}')
                return render(request, 'core/upload.html')

            # Validate file size (max 100 MB)
            max_size = 100 * 1024 * 1024
            if audio_file.size > max_size:
                messages.error(request, 'File is too large. Maximum size is 100 MB.')
                return render(request, 'core/upload.html')

            try:
                # Save meeting with pending status
                meeting = Meeting.objects.create(
                    title=title,
                    audio_file=audio_file,
                    status='pending',
                    user=request.user
                )

                # Dispatch async Celery task instead of processing synchronously
                from .tasks import process_meeting
                process_meeting.delay(meeting.pk)

                # Redirect to processing page (not detail page)
                return redirect('meeting_processing', pk=meeting.pk)

            except Exception as e:
                messages.error(request, f'Error uploading meeting: {str(e)}')

        else:
            messages.error(request, 'Please provide both title and audio file.')

    return render(request, 'core/upload.html')

@login_required(login_url='login')
def process_text_meeting(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        meeting_text = request.POST.get('meeting_text')

        if title and meeting_text:
            try:
                # Save meeting with the transcript already filled in
                meeting = Meeting.objects.create(
                    title=title,
                    transcript=meeting_text,
                    status='pending',
                    user=request.user
                )

                # Dispatch async Celery task (will skip transcription since transcript exists)
                from .tasks import process_meeting
                process_meeting.delay(meeting.pk)

                # Redirect to processing page
                return redirect('meeting_processing', pk=meeting.pk)

            except Exception as e:
                messages.error(request, f'Error processing meeting: {str(e)}')

        else:
            messages.error(request, 'Please provide both title and meeting text.')

    return render(request, 'core/process_text.html')

@login_required(login_url='login')
def meeting_processing(request, pk):
    """Render the processing waiting page, or redirect if already done."""
    meeting = get_object_or_404(Meeting, pk=pk, user=request.user)

    # If already done, redirect straight to detail
    if meeting.status == 'done':
        return redirect('meeting_detail', meeting_id=meeting.pk)

    return render(request, 'core/meeting_processing.html', {'meeting': meeting})

@login_required(login_url='login')
def meeting_list(request):
    meetings = Meeting.objects.filter(user=request.user).order_by('-created_at')

    status_filter = request.GET.get('status')
    if status_filter in ['done', 'processing', 'error', 'pending']:
        meetings = meetings.filter(status=status_filter)

    if request.GET.get('ai') == 'true':
        # Only show meetings that have a summary (i.e., AI processed)
        meetings = meetings.exclude(summary__isnull=True).exclude(summary__exact='')

    return render(request, 'core/meeting_list.html', {'meetings': meetings})

@login_required(login_url='login')
def meeting_detail(request, meeting_id):
    meeting = get_object_or_404(Meeting, id=meeting_id, user=request.user)
    tasks = Task.objects.filter(meeting=meeting)
    return render(request, 'core/meeting_detail.html', {'meeting': meeting, 'tasks': tasks})


@login_required(login_url='login')
@require_POST
def delete_meeting(request, meeting_id):
    """Delete a meeting owned by the current user."""
    meeting = get_object_or_404(Meeting, id=meeting_id, user=request.user)
    title = meeting.title
    # Delete associated audio file from disk
    if meeting.audio_file:
        file_path = meeting.audio_file.path
        if os.path.exists(file_path):
            os.remove(file_path)
    meeting.delete()
    messages.success(request, f'Meeting "{title}" deleted successfully.')
    return redirect('meeting_list')


@login_required(login_url='login')
@require_POST
def toggle_task_status(request, task_id):
    """Toggle a task between pending and completed via AJAX."""
    task = get_object_or_404(Task, id=task_id, meeting__user=request.user)
    task.status = 'completed' if task.status == 'pending' else 'pending'
    task.save()
    return JsonResponse({'status': task.status})


@login_required(login_url='login')
@require_POST
def ask_question(request, meeting_id):
    """RAG-powered Q&A endpoint for a specific meeting."""
    meeting = get_object_or_404(Meeting, id=meeting_id, user=request.user)

    if meeting.status != 'done':
        return JsonResponse({'error': 'Meeting has not been processed yet.'}, status=400)

    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not question:
        return JsonResponse({'error': 'Please enter a question.'}, status=400)

    try:
        rag = get_rag_processor()
        result = rag.ask_question(meeting.id, question)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': f'Error generating answer: {str(e)}'}, status=500)


@login_required(login_url='login')
def settings_page(request):
    """User settings page."""
    total_meetings = Meeting.objects.filter(user=request.user).count()
    total_tasks = Task.objects.filter(meeting__user=request.user).count()
    return render(request, 'core/settings.html', {
        'total_meetings': total_meetings,
        'total_tasks': total_tasks,
    })