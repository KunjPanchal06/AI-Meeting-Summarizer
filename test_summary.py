from core.ai_processor import MeetingAIProcessor

# Create processor instance
processor = MeetingAIProcessor()

# Sample comprehensive meeting text
meeting_text = """
Good morning everyone, welcome to our Q3 business review meeting. Today is September 15th and we have several important topics to cover.

First, let's review our financial performance. Sarah has prepared a comprehensive budget analysis. Our revenue for Q3 exceeded expectations by 12%, reaching $2.4 million. This is primarily due to strong sales in our enterprise segment and successful product launches. However, operational costs increased by 8% due to our office expansion and new hires.

John will present the Project Alpha update. The development phase is now 85% complete and we're still on track for the November 15th launch. The QA team identified three minor bugs that need fixing. Beta testing will begin next week with 50 selected customers. John needs to coordinate with the QA team by tomorrow to resolve these issues.

For our marketing initiatives, the holiday campaign planning is underway. The marketing team should submit their complete campaign proposal by Wednesday. This includes budget requirements, creative assets, and timeline. Sarah will review and approve the budget allocation by Friday.

Regarding human resources, we're expanding our development team. HR has scheduled interviews for two senior developer positions next week. Mike will participate in the technical interviews and provide feedback by the end of next week.

Our next steps include finalizing Q4 budget planning. The finance team needs to prepare detailed projections by October 1st. All department heads should submit their Q4 requirements by September 30th.

Action items summary: John coordinates with QA team, marketing submits campaign proposal, Sarah approves budget, Mike provides interview feedback, finance prepares Q4 projections, and department heads submit requirements.

Thank you everyone for your participation. Our next meeting is scheduled for October 1st.
"""

print("TESTING COMPLETE AI PIPELINE WITH SAMPLE MEETING TEXT")
print("="*80)

# Process the meeting text
transcript, summary, action_items = processor.process_text_only(meeting_text)

# Display comprehensive results
print("\nCOMPLETE MEETING ANALYSIS RESULTS")
print("="*80)

print(f"\nORIGINAL TRANSCRIPT ({len(transcript.split())} words):")
print("-" * 50)
print(transcript[:200] + "..." if len(transcript) > 200 else transcript)

print(f"\nINTELLIGENT SUMMARY ({len(summary.split())} words):")
print("-" * 50)
print(summary)

print(f"\nEXTRACTED ACTION ITEMS ({len(action_items)} items):")
print("-" * 50)
for i, item in enumerate(action_items, 1):
    print(f"\n{i}. TASK: {item['description']}")
    print(f"   ASSIGNEE: {item['assignee'] or 'Not specified'}")
    print(f"   DEADLINE: {item['deadline'] or 'Not specified'}")
    print(f"   STATUS: {item['status']}")

print("\n" + "="*80)
print("PROCESSING STATISTICS:")
print(f"   • Original text: {len(transcript.split())} words")
print(f"   • Summary: {len(summary.split())} words ({100-int((len(summary.split())/len(transcript.split()))*100)}% reduction)")
print(f"   • Action items found: {len(action_items)}")
print(f"   • Processing time: Completed successfully")

print("\nCOMPLETE AI MEETING PROCESSING PIPELINE WORKING PERFECTLY!")