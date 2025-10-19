# from core.ai_processor import MeetingAIProcessor

# processor = MeetingAIProcessor()
# audio_file_path = "harvard.wav"

# print("converting audio to text")
# transcript = processor.convert_audio_to_speech(audio_file_path)

# if transcript:
#     print(transcript)
# else:
#     print("failed to convert")

# print("Whisper model loaded successfully !")

from core.ai_processor import MeetingAIProcessor
import os

processor = MeetingAIProcessor()

# Use FULL absolute path with forward slashes
# audio_file_path = r"C:/Kunj/VS STUDIO/Projects/MeetingSummarizer/harvard.wav"
audio_file_path = "media/meetings/harvard.wav"

print(f"Looking for file: {audio_file_path}")
print(f"File exists: {os.path.exists(audio_file_path)}")

if os.path.exists(audio_file_path):
    transcript = processor.convert_audio_to_text(audio_file_path)
    if transcript:
        print("SUCCESS! Transcribed text:")
        print(transcript)
    else:
        print("Failed to convert")
else:
    print("Audio file not found!")
