import whisper
import torch
import spacy
from transformers import pipeline
import librosa
import soundfile as sf
import os
import tempfile
import re
import logging

logger = logging.getLogger(__name__)

class MeetingAIProcessor:
    def __init__(self):
        logger.info("Initializing AI Models...")

        self.whisper_model = whisper.load_model("base")

        self.summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=0 if torch.cuda.is_available() else -1
        )
        
        self.nlp = spacy.load("en_core_web_sm")

        logger.info("AI Models loaded successfully.")
    
    def convert_audio_to_text(self, audio_path):
        try:
            logger.info("Converting audio file into text...")
            result = self.whisper_model.transcribe(audio_path)
            transcript = result["text"]
            logger.info("Audio converted successfully.")
            return transcript.strip()
        except Exception as e:
            logger.error(f"Error in audio conversion: {str(e)}")
            return None
        
    def generate_summary(self, text):
        try:
            logger.info("Generating summary...")
            if len(text.split()) < 50:
                return "Text too short to summarize."

            max_chunk = 512  # words (~700 tokens), safe for BART's 1024-token limit
            words = text.split()

            if len(words) <= max_chunk:
                summary = self.summarizer(text, max_length=150, min_length=30, do_sample=False, truncation=True)[0]['summary_text']
            else:
                chunks = []
                for i in range(0, len(words), max_chunk):
                    chunk = ' '.join(words[i:i + max_chunk])
                    chunks.append(chunk)
            
                summaries = []
                for chunk in chunks:
                    chunk_summary = self.summarizer(chunk, max_length=100, min_length=20, do_sample=False, truncation=True)[0]['summary_text']
                    summaries.append(chunk_summary)
            
                combined_summary = ' '.join(summaries)
    
                if len(combined_summary.split()) > 100:
                    summary = self.summarizer(combined_summary, max_length=200, min_length=50, do_sample=False, truncation=True)[0]['summary_text']
                else:
                    summary = combined_summary
        
            logger.info("Summary generated successfully.")
            return summary.strip()
        
        except Exception as e:
            logger.error(f"Error in summarization: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return "Error generating summary."
        
    def extract_action_items(self, text):
        """
        Extract action items using improved semantic and pattern matching
        """
        try:
            logger.info("Extracting action items...")
            
            doc = self.nlp(text)
            action_items = []
            
            # Process each sentence individually for better accuracy
            for sent in doc.sents:
                sentence = sent.text.strip()
                
                # Skip very short sentences
                if len(sentence.split()) < 5:
                    continue
                    
                # Look for clear action patterns with person + action + optional deadline
                action_found = self._extract_from_sentence(sentence)
                
                if action_found:
                    action_items.append(action_found)
            
            # Remove exact duplicates only
            unique_items = []
            seen_tasks = set()
            
            for item in action_items:
                task_key = item['description'].lower().strip()
                if task_key not in seen_tasks:
                    unique_items.append(item)
                    seen_tasks.add(task_key)
            
            logger.info(f"Extracted {len(unique_items)} action items.")
            return unique_items
            
        except Exception as e:
            logger.error(f"Error extracting action items: {str(e)}")
            return []

    def _extract_from_sentence(self, sentence):
        """
        Extract single action item from one sentence using multiple strategies
        """
        doc = self.nlp(sentence)
        
        # Strategy 1: Look for "Person + will/should/must + action"
        person_action_pattern = r'([A-Z][a-z]+)\s+(will|should|must|needs?\s+to|has\s+to)\s+([^.!?]+)'
        match = re.search(person_action_pattern, sentence)
        
        if match:
            person = match.group(1)
            action_verb = match.group(2)
            action_desc = match.group(3).strip()
            
            # Extract deadline from the action description
            deadline = self._extract_deadline_from_text(sentence)
            
            return {
                'description': action_desc.capitalize(),
                'assignee': person,
                'deadline': deadline,
                'status': 'pending'
            }
        
        # Strategy 2: Look for "Action item:" or "Task:" patterns
        action_item_pattern = r'(?:action\s+item|task)[:]\s*([^.!?]+)'
        match = re.search(action_item_pattern, sentence, re.IGNORECASE)
        
        if match:
            action_desc = match.group(1).strip()
            
            # Look for person names in the same sentence
            person = self._extract_person_from_sentence(sentence)
            deadline = self._extract_deadline_from_text(sentence)
            
            return {
                'description': action_desc.capitalize(),
                'assignee': person,
                'deadline': deadline,
                'status': 'pending'
            }
        
        # Strategy 3: Look for "Team/Department + needs to/should" patterns  
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
        """
        Extract person name using spaCy NER with better accuracy
        """
        doc = self.nlp(sentence)
        
        # Look for PERSON entities
        for ent in doc.ents:
            if ent.label_ == "PERSON" and len(ent.text.split()) <= 2:  # Avoid long phrases
                return ent.text
        
        # Fallback: Look for capitalized words that might be names
        words = sentence.split()
        for word in words:
            if word[0].isupper() and len(word) > 2 and word.isalpha():
                # Check if it's likely a name (not a common word)
                if word not in ['The', 'This', 'That', 'Team', 'Friday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday', 'Sunday']:
                    return word
        
        return ""

    def _extract_deadline_from_text(self, sentence):
        """
        Extract deadline with better accuracy
        """
        doc = self.nlp(sentence)
        
        # Look for DATE entities first
        for ent in doc.ents:
            if ent.label_ == "DATE":
                return ent.text
        
        # Look for common deadline patterns
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

    def process_meeting(self, audio_file_path):
        """
        Complete pipeline: audio → text → summary → action items
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING COMPLETE MEETING PROCESSING PIPELINE")
            logger.info("=" * 60)
            
            # Step 1: Convert audio to text
            logger.info("STEP 1: Converting audio to text...")
            transcript = self.convert_audio_to_text(audio_file_path)
            
            if not transcript:
                logger.warning("Audio conversion failed. Stopping pipeline.")
                return None, None, None
            
            logger.info(f"Transcript generated! ({len(transcript.split())} words)")
            
            # Step 2: Generate summary
            logger.info("STEP 2: Generating summary...")
            summary = self.generate_summary(transcript)
            logger.info(f"Summary generated! ({len(summary.split())} words)")
            
            # Step 3: Extract action items
            logger.info("STEP 3: Extracting action items...")
            action_items = self.extract_action_items(transcript)
            logger.info(f"Found {len(action_items)} action items!")
            
            logger.info("=" * 60)
            logger.info("MEETING PROCESSING COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            
            return transcript, summary, action_items
            
        except Exception as e:
            logger.error(f"Error in complete meeting processing: {str(e)}")
            return None, None, None

    def process_text_only(self, text):
        """
        Pipeline for text input: text → summary → action items
        (Skip audio conversion for testing)
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING TEXT-ONLY PROCESSING PIPELINE")
            logger.info("=" * 60)
            
            # Step 1: Generate summary
            logger.info("STEP 1: Generating summary...")
            summary = self.generate_summary(text)
            logger.info(f"Summary generated! ({len(summary.split())} words)")
            
            # Step 2: Extract action items
            logger.info("STEP 2: Extracting action items...")
            action_items = self.extract_action_items(text)
            logger.info(f"Found {len(action_items)} action items!")
            
            logger.info("=" * 60)
            logger.info("TEXT PROCESSING COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            
            return text, summary, action_items
            
        except Exception as e:
            logger.error(f"Error in text processing: {str(e)}")
            return None, None, None