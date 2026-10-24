
import pandas as pd
import numpy as np
import psycopg2
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import joblib
import os

SCHEMA = os.environ.get("PGSCHEMA", "DW Health")

def fetch_data():
    conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
    
    # Mood Log (Target)
    mood = pd.read_sql(f"""
        SELECT date_trunc('day', log_time)::date as date, 
               AVG(COALESCE(sentiment_score_dw, sentiment_score_llm)) as mood
        FROM "{SCHEMA}".mood_log
        WHERE COALESCE(sentiment_score_dw, sentiment_score_llm) IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, conn)
    
    # Daily Summary (Health)
    health = pd.read_sql(f"""
        SELECT summary_date as date, sleep_total_min, hrv, resting_heart_rate, steps
        FROM "{SCHEMA}".daily_summary
    """, conn)
    
    # Airthings sensor data (set AIRTHINGS_DEVICE_ID to your device)
    air = pd.read_sql("""
        SELECT date_trunc('day', recorded_at)::date as date, 
               AVG(co2) as co2, AVG(voc) as voc, AVG(pm25) as pm25, AVG(humidity) as humidity
        FROM climate.airthings_samples
        WHERE device_id = %s
        GROUP BY 1
    """, conn, params=[os.environ.get("AIRTHINGS_DEVICE_ID", "")])
    
    # Weather
    weather = pd.read_sql("""
        SELECT date as date, total_precip, max_temp
        FROM climate.yvr_daily_weather
    """, conn)
    
    # Workload Metrics (from CSV)
    try:
        workload = pd.read_csv('workload_team_metrics.csv')
        workload['date'] = pd.to_datetime(workload['date']).dt.date
    except FileNotFoundError:
        workload = pd.DataFrame(columns=['date', 'meeting_hours', 'team_absence_count', 'personal_event_count', 'leadership_meeting_count'])

    conn.close()
    return mood, health, air, weather, workload

def process_and_model():
    mood, health, air, weather, workload = fetch_data()
    
    # Standardize dates
    mood['date'] = pd.to_datetime(mood['date']).dt.date
    health['date'] = pd.to_datetime(health['date']).dt.date
    air['date'] = pd.to_datetime(air['date']).dt.date
    weather['date'] = pd.to_datetime(weather['date']).dt.date
    
    # Merge predictors
    df = health.merge(air, on='date', how='outer')
    df = df.merge(weather, on='date', how='outer')
    df = df.merge(workload[['date', 'meeting_hours', 'team_absence_count', 'personal_event_count', 'leadership_meeting_count']], on='date', how='outer')
    df = df.sort_values('date')
    
    features = ['sleep_total_min', 'hrv', 'resting_heart_rate', 'steps', 'co2', 'voc', 'pm25', 'humidity', 'total_precip', 'max_temp', 'meeting_hours', 'team_absence_count', 'personal_event_count', 'leadership_meeting_count']
    
    # Fill missing features
    for col in features:
        if col in df.columns:
            # For calendar metrics, NaN usually means 0 (no meetings, no absences)
            if col in ['meeting_hours', 'team_absence_count', 'personal_event_count', 'leadership_meeting_count']:
                df[col] = df[col].fillna(0)
            else:
                df[col] = df[col].fillna(df[col].mean())
    
    # Lag features by 1 day
    df_lagged = df.copy()
    lag_cols = []
    for col in features:
        lag_col = f'lag_{col}'
        df_lagged[lag_col] = df_lagged[col].shift(1)
        lag_cols.append(lag_col)
    
    # Training Data
    train_data = df_lagged.merge(mood, on='date', how='inner').dropna(subset=['mood'] + lag_cols)
    
    X_train = train_data[lag_cols]
    y_train = train_data['mood']
    
    print(f"Training on {len(train_data)} samples with {len(lag_cols)} features...")
    
    # Scaling
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    # Ridge Model
    model = Ridge(alpha=1.0)
    model.fit(X_train_scaled, y_train)
    
    # Save Model
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/mood_ridge_model.pkl')
    joblib.dump(scaler, 'models/mood_scaler.pkl')
    
    # Coefficients
    coeffs = pd.DataFrame({'feature': features, 'weight': model.coef_}).sort_values('weight', ascending=False)
    
    # Predictions since 2025-12-01
    predict_start = pd.to_datetime('2025-12-01').date()
    df_predict = df_lagged[df_lagged['date'] >= predict_start].copy()
    
    X_predict = df_predict[lag_cols]
    X_predict_scaled = scaler.transform(X_predict)
    df_predict['predicted_mood'] = model.predict(X_predict_scaled)
    
    # Join with Actual Mood
    results = df_predict[['date', 'predicted_mood', 'meeting_hours', 'team_absence_count', 'personal_event_count', 'leadership_meeting_count']].merge(mood, on='date', how='left')
    
    return coeffs, results

def save_to_db(results):
    conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
    cur = conn.cursor()
    
    # Update table to include new columns if they don't exist (just in case)
    cur.execute(f"""
        ALTER TABLE "{SCHEMA}".mood_predict ADD COLUMN IF NOT EXISTS meeting_hours NUMERIC;
        ALTER TABLE "{SCHEMA}".mood_predict ADD COLUMN IF NOT EXISTS team_absence_count INTEGER;
        ALTER TABLE "{SCHEMA}".mood_predict ADD COLUMN IF NOT EXISTS personal_event_count INTEGER;
        ALTER TABLE "{SCHEMA}".mood_predict ADD COLUMN IF NOT EXISTS leadership_meeting_count INTEGER;
    """)
    
    # Insert/Upsert
    for _, row in results.iterrows():
        cur.execute(f"""
            INSERT INTO "{SCHEMA}".mood_predict (date, predicted_mood, actual_mood, meeting_hours, team_absence_count, personal_event_count, leadership_meeting_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (date) DO UPDATE SET
                predicted_mood = EXCLUDED.predicted_mood,
                actual_mood = EXCLUDED.actual_mood,
                meeting_hours = EXCLUDED.meeting_hours,
                team_absence_count = EXCLUDED.team_absence_count,
                personal_event_count = EXCLUDED.personal_event_count,
                leadership_meeting_count = EXCLUDED.leadership_meeting_count,
                updated_at = NOW();
        """, (row['date'], row['predicted_mood'], row['mood'] if not pd.isna(row['mood']) else None, 
              row['meeting_hours'], row['team_absence_count'], row['personal_event_count'], row['leadership_meeting_count']))
    
    conn.commit()
    cur.close()
    conn.close()

def print_physiological_warning():
    conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "postgres"))
    df = pd.read_sql(f"""
        SELECT summary_date, hrv, resting_heart_rate 
        FROM "{SCHEMA}".daily_summary 
        ORDER BY summary_date DESC LIMIT 3
    """, conn)
    conn.close()
    
    print("\n--- PHYSIOLOGICAL STRESS CHECK ---")
    if not df.empty:
        latest = df.iloc[0]
        date = latest['summary_date']
        hrv = latest['hrv']
        rhr = latest['resting_heart_rate']
        
        print(f"Latest Data ({date}): HRV={hrv}, RHR={rhr}")
        
        # Adjust thresholds to your own baselines (or set via env vars)
        hrv_low = float(os.environ.get('HRV_LOW_THRESHOLD', '24'))
        rhr_high = float(os.environ.get('RHR_HIGH_THRESHOLD', '75'))
        is_stressed = False
        reasons = []
        
        if hrv is not None and hrv < hrv_low:
            is_stressed = True
            reasons.append(f"Low HRV ({hrv})")
        if rhr is not None and rhr > rhr_high:
            is_stressed = True
            reasons.append(f"High RHR ({rhr})")
            
        if is_stressed:
            print(f"⚠️ WORKLOAD WARNING: Physiological stress detected! ({', '.join(reasons)})")
            print("Action: Apply load-shedding / rest protocol.")
        else:
            print("✅ Physiological status stable.")
    else:
        print("No recent health data found for assessment.")

if __name__ == "__main__":
    coeffs, results = process_and_model()
    print("--- UPDATED MODEL COEFFICIENTS (Including Workload) ---")
    print(coeffs.to_string(index=False))
    
    save_to_db(results)
    print(f"\nSaved {len(results)} predictions and workload metrics to 'DW Health'.mood_predict table.")
    
    print("\n--- RECENT PREDICTIONS ---")
    print(results.tail(5).to_string(index=False))
    
    # Add the warning check
    print_physiological_warning()
