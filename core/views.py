# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
import os

from .models import Meeting, Task
from .ai_processor import MeetingAIProcessor  # 🔹 Added

# 🔹 Initialize AI model once globally (only when needed)
ai_processor = MeetingAIProcessor()


def home(request):
    recent_meetings = Meeting.objects.filter(user=request.user).order_by('-created_at')[:5] if request.user.is_authenticated else []
    context = {
        'recent_meetings': recent_meetings,
        'total_meetings': Meeting.objects.filter(user=request.user).count() if request.user.is_authenticated else 0,
        'completed_tasks': 85,
        'time_saved': 12,
    }
    return render(request, 'core/home.html', context)


def upload_meeting(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        audio_file = request.FILES.get('audio_file')

        if title and audio_file:
            try:
                meeting = Meeting.objects.create(
                    title=title,
                    audio_file=audio_file,
                    status='processing',
                    user=request.user if request.user.is_authenticated else None
                )

                # 🔹 Full file path
                audio_path = os.path.join(settings.MEDIA_ROOT, str(meeting.audio_file))

                # 🔹 Run AI processing
                transcript, summary, action_items = ai_processor.process_meeting(audio_path)

                if not transcript:
                    meeting.status = 'failed'
                    meeting.save()
                    messages.error(request, f'Failed to process "{title}". Please try again.')
                    return redirect('meeting_detail', meeting_id=meeting.id)

                # 🔹 Save results
                meeting.transcript = transcript
                meeting.summary = summary
                meeting.status = 'completed'
                meeting.save()

                # 🔹 Save extracted tasks
                for item in action_items:
                    Task.objects.create(
                        meeting=meeting,
                        description=item.get('description', ''),
                        assignee=item.get('assignee', ''),
                        deadline_text=item.get('deadline', ''),
                        status=item.get('status', 'pending')
                    )

                messages.success(request, f'Meeting "{title}" processed successfully!')
                return redirect('meeting_detail', meeting_id=meeting.id)

            except Exception as e:
                messages.error(request, f'Error processing meeting: {str(e)}')

        else:
            messages.error(request, 'Please provide both title and audio file.')

    return render(request, 'core/upload.html')


def process_text_meeting(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        meeting_text = request.POST.get('meeting_text')

        if title and meeting_text:
            try:
                meeting = Meeting.objects.create(
                    title=title,
                    transcript=meeting_text,
                    status='processing',
                    user=request.user if request.user.is_authenticated else None
                )

                # 🔹 Use AI processor for text input
                transcript, summary, action_items = ai_processor.process_text_only(meeting_text)

                meeting.summary = summary
                meeting.status = 'completed'
                meeting.save()

                # 🔹 Add tasks
                for item in action_items:
                    Task.objects.create(
                        meeting=meeting,
                        description=item.get('description', ''),
                        assignee=item.get('assignee', ''),
                        deadline_text=item.get('deadline', ''),
                        status=item.get('status', 'pending')
                    )

                messages.success(request, f'Meeting "{title}" processed successfully!')
                return redirect('meeting_detail', meeting_id=meeting.id)

            except Exception as e:
                messages.error(request, f'Error processing meeting: {str(e)}')

        else:
            messages.error(request, 'Please provide both title and meeting text.')

    return render(request, 'core/process_text.html')


def meeting_list(request):
    """
    List all meetings or only AI-processed meetings if ?ai=true is in URL.
    """
    meetings = Meeting.objects.none()

    if request.user.is_authenticated:
        meetings = Meeting.objects.filter(user=request.user).order_by('-created_at')

        if request.GET.get('ai') == 'true':
            # Only show meetings that have a summary (i.e., AI processed)
            meetings = meetings.exclude(summary__isnull=True).exclude(summary__exact='')

    return render(request, 'core/meeting_list.html', {'meetings': meetings})


def meeting_detail(request, meeting_id):
    meeting = get_object_or_404(Meeting, id=meeting_id)
    tasks = Task.objects.filter(meeting=meeting)
    return render(request, 'core/meeting_detail.html', {'meeting': meeting, 'tasks': tasks})
