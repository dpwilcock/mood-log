import os
import json
import psycopg2
from datetime import datetime
import google.generativeai as genai

SCHEMA = os.environ.get("PGSCHEMA", "DW Health")

# Setup Gemini
genai.configure() # Assumes GOOGLE_API_KEY is in env
model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))

directory = os.path.expanduser(os.environ.get("MOOD_DIR", "~/moods"))
files = [f for f in os.listdir(directory) if f.endswith('.md')]

conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
cur = conn.cursor()

def process_file(filename):
    filepath = os.path.join(directory, filename)
    with open(filepath, 'r') as f:
        content = f.read()

    prompt = f"""
    Analyze the following journal entry and extract:
    1. The Date (from the filename "{filename}" or content). Format exactly as YYYY-MM-DD HH:MM:SS. If no time, use 12:00:00.
    2. A Sentiment Score (1-10, where 5 is normal/neutral).
    3. 2-4 descriptive tags (array of strings).

    Return ONLY a valid JSON object with keys: "date", "sentiment", "tags". No markdown block, no backticks.

    Entry:
    {content}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        
        log_time = data['date']
        sentiment = data['sentiment']
        tags = data['tags']
        
        print(f"Processing {filename}: {log_time}, {sentiment}, {tags}")

        cur.execute(
            f'INSERT INTO "{SCHEMA}".mood_log (log_time, sentiment_score_llm, tags, comment) VALUES (%s, %s, %s, %s) ON CONFLICT (log_time) DO UPDATE SET sentiment_score_llm = EXCLUDED.sentiment_score_llm, tags = EXCLUDED.tags, comment = EXCLUDED.comment',
            (log_time, sentiment, tags, content)
        )
        conn.commit()
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        conn.rollback()

for f in files:
    process_file(f)

print("Test complete.")
