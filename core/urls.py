# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_meeting, name='upload_meeting'),
    path('process/', views.process_text_meeting, name='process_text_meeting'),
    path('meetings/', views.meeting_list, name='meeting_list'),
    path('meeting/<int:meeting_id>/', views.meeting_detail, name='meeting_detail'),
]

