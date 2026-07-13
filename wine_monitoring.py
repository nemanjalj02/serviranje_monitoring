import sqlite3
import statistics
import pandas as pd
from datetime import datetime
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
import os

DB_PATH = "predictions.db"
REPORTS_DIR = "reports"
LATENCY_EVERY_N  = 100
DRIFT_EVERY_N = 100

os.makedirs(REPORTS_DIR, exist_ok=True)

#pristupanje bazi, dobijanje uspesnih zahteva (korisnik dobio labelu) njima se prati latencija/monitoring
def get_valid_request_count():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE status IN ('success', 'low_confidence')")
        return cursor.fetchone()[0]

def check_latency():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        #dobijanje response time od validnih zahteva sortiranje hronoloski, najnoviji prvi
        cursor.execute("""
            SELECT response_time FROM predictions
            WHERE status IN ('success', 'low_confidence')
            AND response_time IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (LATENCY_EVERY_N,))
        rows = cursor.fetchall()

        #provera da li ih je 100
        if len(rows) < LATENCY_EVERY_N:
            print(f"[Latency] Nedovoljno zahteva ({len(rows)}), preskacam...")
            return
        
        #racunanje statistike
        times = [r[0] for r in rows]
        avg = sum(times) / len(times)
        minimum = min(times)
        maximum = max(times)
        median = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)]

        print(f"[Latency] Zahteva: {len(rows)}, Avg: {avg:.2f}ms, Min: {minimum:.2f}ms, Max: {maximum:.2f}ms, Median: {median:.2f}ms, P95: {p95:.2f}ms")
        
        #upis izracunatih vrednosti 
        cursor.execute("""
            INSERT INTO monitoring_logs (timestamp, avg_latency, min_latency, max_latency, p95_latency, median_latency, num_requests)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), avg, minimum, maximum, p95, median, len(rows)))
        conn.commit()
#razliciti nazivi obelezja u datasetu i predicitons, mapiraju se da budu isti 
CSV_COLUMN_MAP = {
    "fixed acidity":        "fixed_acidity",
    "volatile acidity":     "volatile_acidity",
    "citric acid":          "citric_acid",
    "residual sugar":       "residual_sugar",
    "chlorides":            "chlorides",
    "free sulfur dioxide":  "free_sulfur_dioxide",
    "total sulfur dioxide": "total_sulfur_dioxide",
    "density":              "density",
    "pH":                   "pH",
    "sulphates":            "sulphates",
    "alcohol":              "alcohol",
}

def check_drift():
    #referenca koja se koristi za monitoring su originalne vrednosti iz dataseta, vidjene tokom treninga
    feature_cols = list(CSV_COLUMN_MAP.values())
    reference_df = pd.read_csv("winequality-red.csv").rename(columns=CSV_COLUMN_MAP)[feature_cols]

    #ponovo odabir validnih upita
    with sqlite3.connect(DB_PATH) as conn:
        current_df = pd.read_sql_query(f"""
            SELECT {', '.join(feature_cols)} FROM predictions
            WHERE status IN ('success', 'low_confidence')
            ORDER BY id DESC
            LIMIT {DRIFT_EVERY_N}
        """, conn)
    #provera da li ih je dovoljno za pokretanje monitoriga
    if len(current_df) < DRIFT_EVERY_N:
        print(f"[Drift] Nedovoljno trenutnih podataka ({len(current_df)}), preskacam...")
        return
    #formiranje evidently reporta sa odabirom testa i praga za detekciju. 
    report = Report(metrics=[DataDriftPreset(stattest="ks", stattest_threshold=0.01)])
    #definisanje skupova koji se porede (onaj iz dataseta, sa onim iz upita)
    report.run(reference_data=reference_df, current_data=current_df)

    #cuvanje u html formatu
    report_path = os.path.join(REPORTS_DIR, f"drift_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    report.save_html(report_path)

    print(f"[Drift] Report sacuvan: {report_path}")

#provera broja zahteva i da li ih je 100,200,300,400.. odnosno dovoljno za pokretanje monitoringa i pracenja latencije
#ako ih je dovoljno, pokrecu se
def on_new_request():
    count = get_valid_request_count()
    print(f"[Monitoring] count={count}", flush=True)
    if count % LATENCY_EVERY_N == 0:
        check_latency()
    if count % DRIFT_EVERY_N == 0:
        check_drift()
#ispis da je uspesno zapoceto 
def start_monitoring():
    print(f"[Monitoring] Latencija: svakih {LATENCY_EVERY_N} upita")
    print(f"[Monitoring] Drift: svakih {DRIFT_EVERY_N} upita")
