import os
import psycopg2

SCHEMA = os.environ.get("PGSCHEMA", "DW Health")

conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
cur = conn.cursor()
cur.execute("""
    SELECT EXTRACT(MONTH FROM log_time) AS month, 
           AVG(COALESCE(sentiment_score_dw, sentiment_score_llm)) as avg_score,
           COUNT(*) as count
    FROM "{SCHEMA}".mood_log
    WHERE COALESCE(sentiment_score_dw, sentiment_score_llm) IS NOT NULL
    GROUP BY month
    ORDER BY month;
""")
rows = cur.fetchall()

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
data = {}
for r in rows:
    data[int(r[0])] = float(r[1])

print("--- AVERAGE MOOD BY MONTH (All-Time) ---")
for i in range(1, 13):
    score = data.get(i, 0)
    month_name = months[i-1]
    
    # Scale: each full point above 4.0 is 10 blocks (so we zoom in on the 4.0 - 6.5 range)
    # E.g., 5.0 = 10 blocks. 6.0 = 20 blocks.
    if score >= 4.0:
        bar_len = int((score - 4.0) * 10)
    else:
        bar_len = 0
        
    bar = "█" * bar_len
    
    print(f"{month_name} | {score:.2f} | {bar}")
