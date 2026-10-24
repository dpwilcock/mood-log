import os
import json
import glob
import psycopg2
import anthropic

SCHEMA = os.environ.get("PGSCHEMA", "DW Health")

client = anthropic.Anthropic()

conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
conn.autocommit = True

PROMPT = f"""
You are given a text containing a mood log with entries separated by dates.
Extract a JSON array of entries. For each entry with actual text/content, extract:
- "date": Date in "dd-MMM-YYYY" format (e.g., "02-Apr-2020"). If the input date has a different format, standardize it to this.
- "sentiment_score_dw": A numeric score if the user explicitly wrote one (e.g. 6.0). Look for a number at the end of the entry like "6.0" or "7.5". If there is no explicit score, return null.
- "sentiment_score_llm": A numeric score from 1 to 10 (1=terrible, 10=amazing) estimated by you based on the text. Always provide this. Use decimals if appropriate.
- "tags": An array of 2-4 descriptive string tags (e.g., ["family", "work", "stress", "bike"]).
- "comment": The full raw text of the entry for that date.

Return ONLY valid JSON. The output must be an array of objects. Skip dates that have no text/comments under them. Do not include markdown formatting blocks like ```json ... ```, just output the raw JSON.
"""

def process_file(filepath):
    print(f"Processing {os.path.basename(filepath)}...")
    with open(filepath, "r") as f:
        content = f.read()
    
    if not content.strip():
        print("Empty file.")
        return

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        temperature=0,
        system="You are a data extraction assistant that outputs raw JSON arrays without markdown wrappers.",
        messages=[
            {"role": "user", "content": f"{PROMPT}\n\nHere is the text:\n\n{content}"}
        ]
    )

    result_text = response.content[0].text.strip()
    if result_text.startswith("```json"):
        result_text = result_text[7:-3]
    elif result_text.startswith("```"):
        result_text = result_text[3:-3]
        
    try:
        entries = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        print(result_text[:500])
        return

    inserted = 0
    with conn.cursor() as cur:
        for entry in entries:
            date_str = entry.get("date")
            if not date_str:
                continue
            dw_score = entry.get("sentiment_score_dw")
            llm_score = entry.get("sentiment_score_llm")
            tags = entry.get("tags", [])
            comment = entry.get("comment", "")

            try:
                cur.execute(
                    '''
                    INSERT INTO "{SCHEMA}".mood_log 
                    (log_time, sentiment_score_dw, sentiment_score_llm, comment, tags)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (log_time) DO UPDATE SET
                        sentiment_score_dw = EXCLUDED.sentiment_score_dw,
                        sentiment_score_llm = EXCLUDED.sentiment_score_llm,
                        comment = EXCLUDED.comment,
                        tags = EXCLUDED.tags
                    ''',
                    (date_str, dw_score, llm_score, comment, tags)
                )
                inserted += 1
            except Exception as e:
                print(f"Error inserting {date_str}: {e}")
    print(f"Inserted/Updated {inserted} entries.")

if __name__ == "__main__":
    import sys
    notes_dir = os.path.expanduser(os.environ.get("MOOD_NOTES_DIR", "~/mood-notes"))
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        files = glob.glob(os.path.join(notes_dir, "*.md"))
        for f in files:
            process_file(f)
    elif len(sys.argv) > 1:
        # Treat first arg as inline text: run the same extraction on it.
        import json as _json
        from datetime import datetime as _dt

        text = sys.argv[1]
        print(f"Processing inline text...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            temperature=0,
            system="You are a data extraction assistant that outputs raw JSON arrays without markdown wrappers.",
            messages=[
                {"role": "user", "content": f"{PROMPT}\n\nHere is the text:\n\n{text}"}
            ]
        )
        result_text = response.content[0].text.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:-3]
        elif result_text.startswith("```"):
            result_text = result_text[3:-3]
        try:
            entries = _json.loads(result_text)
            for e in entries:
                print(_json.dumps(e, indent=2))
        except _json.JSONDecodeError as ex:
            print(f"Failed to parse JSON: {ex}")
            print(result_text[:500])
    else:
        test_file = os.path.join(notes_dir, "mood-log-example.md")
        process_file(test_file)
