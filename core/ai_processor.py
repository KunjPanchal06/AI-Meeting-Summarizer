import whisper
import torch
import spacy
from transformers import pipeline
import librosa
import soundfile as sf
import os
import tempfile
import re


class MeetingAIProcessor:
    def __init__(self):
        print("Initializing AI Processor (Lazy Mode)...")

        # Lazy load — don't load heavy models at startup
        self.whisper_model = None
        self.summarizer = None
        self.nlp = None

        print("Models will load on first use (to save memory).")

    # --------------------------------------------------
    # AUDIO TO TEXT
    # --------------------------------------------------
    def convert_audio_to_text(self, audio_path):
        try:
            if self.whisper_model is None:
                print("Loading Whisper model...")
                self.whisper_model = whisper.load_model("base")

            print("Converting audio file into text file !")
            result = self.whisper_model.transcribe(audio_path)
            transcript = result["text"]
            print("Audio converted Successfully !")
            return transcript.strip()
        except Exception as e:
            print(f"Error in audio conversion : {str(e)}")
            return None

    # --------------------------------------------------
    # SUMMARIZATION
    # --------------------------------------------------
    def generate_summary(self, text):
        try:
            if self.summarizer is None:
                print("Loading summarization model (BART)...")
                self.summarizer = pipeline(
                    "summarization",
                    model="facebook/bart-large-cnn",
                    device=0 if torch.cuda.is_available() else -1
                )

            print("Generating Summary")
            if len(text.split()) < 50:
                return "Text too short to summarize."

            max_chunk = 1024
            words = text.split()

            if len(words) <= max_chunk:
                summary = self.summarizer(text, max_length=150, min_length=50, do_sample=False)[0]['summary_text']
            else:
                chunks = []
                for i in range(0, len(words), max_chunk):
                    chunk = ' '.join(words[i:i + max_chunk])
                    chunks.append(chunk)

                summaries = []
                for chunk in chunks:
                    chunk_summary = self.summarizer(chunk, max_length=100, min_length=30, do_sample=False)[0]['summary_text']
                    summaries.append(chunk_summary)

                combined_summary = ' '.join(summaries)

                if len(combined_summary.split()) > 100:
                    summary = self.summarizer(combined_summary, max_length=200, min_length=75, do_sample=False)[0]['summary_text']
                else:
                    summary = combined_summary

            print("Summary generated successfully!")
            return summary.strip()

        except Exception as e:
            print(f"Error in summarization: {str(e)}")
            return "Error generating summary."

    # --------------------------------------------------
    # ACTION ITEM EXTRACTION
    # --------------------------------------------------
    def extract_action_items(self, text):
        try:
            print("Extracting action items...")

            if self.nlp is None:
                print("Loading spaCy model...")
                self.nlp = spacy.load("en_core_web_sm")

            doc = self.nlp(text)
            action_items = []

            for sent in doc.sents:
                sentence = sent.text.strip()
                if len(sentence.split()) < 5:
                    continue

                action_found = self._extract_from_sentence(sentence)
                if action_found:
                    action_items.append(action_found)

            unique_items = []
            seen_tasks = set()

            for item in action_items:
                task_key = item['description'].lower().strip()
                if task_key not in seen_tasks:
                    unique_items.append(item)
                    seen_tasks.add(task_key)

            print(f"Extracted {len(unique_items)} action items!")
            return unique_items

        except Exception as e:
            print(f"Error extracting action items: {str(e)}")
            return []

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------
    def _extract_from_sentence(self, sentence):
        doc = self.nlp(sentence)

        # Strategy 1: Person + will/should/must + action
        person_action_pattern = r'([A-Z][a-z]+)\s+(will|should|must|needs?\s+to|has\s+to)\s+([^.!?]+)'
        match = re.search(person_action_pattern, sentence)
        if match:
            person = match.group(1)
            action_desc = match.group(3).strip()
            deadline = self._extract_deadline_from_text(sentence)
            return {
                'description': action_desc.capitalize(),
                'assignee': person,
                'deadline': deadline,
                'status': 'pending'
            }

        # Strategy 2: Action item: or Task:
        action_item_pattern = r'(?:action\s+item|task)[:]\s*([^.!?]+)'
        match = re.search(action_item_pattern, sentence, re.IGNORECASE)
        if match:
            action_desc = match.group(1).strip()
            person = self._extract_person_from_sentence(sentence)
            deadline = self._extract_deadline_from_text(sentence)
            return {
                'description': action_desc.capitalize(),
                'assignee': person,
                'deadline': deadline,
                'status': 'pending'
            }

        # Strategy 3: Team/Department + needs to/should
        team_pattern = r'(the\s+)?([A-Za-z]+\s+team|marketing|development|sales)\s+(needs?\s+to|should|must)\s+([^.!?]+)'
        match = re.search(team_pattern, sentence, re.IGNORECASE)
        if match:
            team = match.group(2)
            action_desc = match.group(4).strip()
            deadline = self._extract_deadline_from_text(sentence)
            return {
                'description': action_desc.capitalize(),
                'assignee': team.capitalize(),
                'deadline': deadline,
                'status': 'pending'
            }

        return None

    def _extract_person_from_sentence(self, sentence):
        doc = self.nlp(sentence)
        for ent in doc.ents:
            if ent.label_ == "PERSON" and len(ent.text.split()) <= 2:
                return ent.text

        words = sentence.split()
        for word in words:
            if word[0].isupper() and len(word) > 2 and word.isalpha():
                if word not in ['The', 'This', 'That', 'Team', 'Friday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday', 'Sunday']:
                    return word
        return ""

    def _extract_deadline_from_text(self, sentence):
        doc = self.nlp(sentence)
        for ent in doc.ents:
            if ent.label_ == "DATE":
                return ent.text

        deadline_patterns = [
            r'by\s+(friday|monday|tuesday|wednesday|thursday|saturday|sunday)',
            r'by\s+(next\s+\w+)',
            r'by\s+(end\s+of\s+\w+)',
            r'by\s+(tomorrow|today)',
            r'before\s+([^.!?]+)',
            r'due\s+([^.!?]+)'
        ]
        for pattern in deadline_patterns:
            match = re.search(pattern, sentence, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    # --------------------------------------------------
    # PIPELINES
    # --------------------------------------------------
    def process_meeting(self, audio_file_path):
        try:
            print("=" * 60)
            print("STARTING COMPLETE MEETING PROCESSING PIPELINE")
            print("=" * 60)

            print("\nSTEP 1: Converting audio to text...")
            transcript = self.convert_audio_to_text(audio_file_path)
            if not transcript:
                print("Audio conversion failed. Stopping pipeline.")
                return None, None, None

            print(f"Transcript generated! ({len(transcript.split())} words)")

            print("\nSTEP 2: Generating summary...")
            summary = self.generate_summary(transcript)
            print(f"Summary generated! ({len(summary.split())} words)")

            print("\nSTEP 3: Extracting action items...")
            action_items = self.extract_action_items(transcript)
            print(f"Found {len(action_items)} action items!")

            print("\n" + "=" * 60)
            print("MEETING PROCESSING COMPLETED SUCCESSFULLY!")
            print("=" * 60)

            return transcript, summary, action_items

        except Exception as e:
            print(f"Error in complete meeting processing: {str(e)}")
            return None, None, None

    def process_text_only(self, text):
        try:
            print("=" * 60)
            print("STARTING TEXT-ONLY PROCESSING PIPELINE")
            print("=" * 60)

            print("\nSTEP 1: Generating summary...")
            summary = self.generate_summary(text)
            print(f"Summary generated! ({len(summary.split())} words)")

            print("\nSTEP 2: Extracting action items...")
            action_items = self.extract_action_items(text)
            print(f"Found {len(action_items)} action items!")

            print("\n" + "=" * 60)
            print("TEXT PROCESSING COMPLETED SUCCESSFULLY!")
            print("=" * 60)

            return text, summary, action_items

        except Exception as e:
            print(f"Error in text processing: {str(e)}")
            return None, None, None
