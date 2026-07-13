import pandas as pd
import requests
import sqlite3
import time
import random
import statistics
from datetime import datetime

API_URL = "http://127.0.0.1:8000/predict"
CSV_PATH = "winequality-red.csv"
DELAY_SECONDS = 0.2
DB_PATH = "predictions.db"

def init_client_log_table():
#server ne zna round trip vreme (ukljucuje mrezu), pa ga
#upisuje ovaj skript, ne wine_database.py. to vreme se ne salje
#u API odgovoru (klijenta se to ne tice). skripta ga umesto toga cita direktno
#iz predictions tabele i upisuje oba merenja u isti red client_latency_log tabele
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_latency_log (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp              TEXT NOT NULL,
                request_index          INTEGER,
                label                  TEXT,
                status_code            INTEGER,
                round_trip_ms          REAL,
                server_response_time_ms REAL
            )
        """)
        try:
            conn.execute("ALTER TABLE client_latency_log ADD COLUMN server_response_time_ms REAL")
        except sqlite3.OperationalError:
            pass
        conn.commit()
#upisuje jedan red u gornju tabelu, redni broj tip http staus i oba vremena 
def log_round_trip(request_index, label, status_code, round_trip_ms, server_response_time_ms=None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO client_latency_log (timestamp, request_index, label, status_code, round_trip_ms, server_response_time_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), request_index, label, status_code, round_trip_ms, server_response_time_ms))
        conn.commit()
#cita response time iz poslednjeg reda iz predicitons
def get_latest_server_response_time():
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT response_time FROM predictions ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else None
#uzima red iz tabele i pretvara ga u format koje predict ocekuje
#ovo pravi validan upit, vec vidjen tokom treninga (bez drifta)
def row_to_payload(row):
    return {
        "fixed_acidity":        float(row["fixed acidity"]),
        "volatile_acidity":     float(row["volatile acidity"]),
        "citric_acid":          float(row["citric acid"]),
        "residual_sugar":       float(row["residual sugar"]),
        "chlorides":            float(row["chlorides"]),
        "free_sulfur_dioxide":  float(row["free sulfur dioxide"]),
        "total_sulfur_dioxide": float(row["total sulfur dioxide"]),
        "density":              float(row["density"]),
        "pH":                   float(row["pH"]),
        "sulphates":            float(row["sulphates"]),
        "alcohol":              float(row["alcohol"]),
    }

def make_invalid_payload():
    invalid_cases = [
        {"fixed_acidity": "tekst", "volatile_acidity": 0.5, "citric_acid": 0.1,
         "residual_sugar": 2.0, "chlorides": 0.05, "free_sulfur_dioxide": 10.0,
         "total_sulfur_dioxide": 30.0, "density": 0.998, "pH": 3.2,
         "sulphates": 0.6, "alcohol": 10.0},
        {"fixed_acidity": 7.4, "volatile_acidity": 0.7, "citric_acid": 0.0,
         "residual_sugar": -5.0, "chlorides": 0.076, "free_sulfur_dioxide": 11.0,
         "total_sulfur_dioxide": 34.0, "density": 0.9978, "pH": 3.51,
         "sulphates": 0.56, "alcohol": 9.4},
        {"fixed_acidity": 7.4, "volatile_acidity": 0.7, "citric_acid": 0.0,
         "residual_sugar": 1.9, "chlorides": 0.076, "free_sulfur_dioxide": 11.0,
         "total_sulfur_dioxide": 34.0, "density": 0.9978, "pH": 3.51,
         "sulphates": 0.56, "alcohol": 999.0},
    ]
    return random.choice(invalid_cases)

#simulacija data drifta 
#novo vino, sa vecim alk i pratecom niskom gustinom vecim sulfatima i visim ph
#bitno: opsezi van dataseta, ali i dalje fizicki moguci
#tj ovi zahtevi su validni, samo brojke nisu vidjene tokom treninga
def make_multi_drift_payload(row):
    payload = row_to_payload(row)
    payload["alcohol"] = round(random.uniform(15.0, 20.0), 4)
    payload["density"] = round(random.uniform(0.980, 0.985), 5)
    payload["sulphates"] = round(random.uniform(2.5, 4.0), 4)
    payload["pH"] = round(random.uniform(4.1, 5.0), 4)
    return payload, "alcohol+density+sulphates+pH"

#inicijalizacija vremena, dobijanje odg i merenje round trip vremena
def send(payload):
    t0 = time.time()
    response = requests.post(API_URL, json=payload)
    round_trip_ms = (time.time() - t0) * 1000
    return response, round_trip_ms

def simulate():
    init_client_log_table()
    df = pd.read_csv(CSV_PATH, sep=",")

    # 80% validno, 10% nevalidno, 10% multi-feature drift.
    # Svaki drift blok mora imati tacno 100 validnih zahteva kada Evidently napravi izvestaj.
    n_drift_multi = 100
    n_valid = 800
    n_invalid = 100
    #ispis radi provere
    print(f"[Simulate] Ucitano {len(df)} redova iz dataseta")
    print(f"[Simulate] Saljem {n_valid + n_invalid + n_drift_multi} zahteva u 3 faze:")
    print(f"[Simulate]   Faza 1: {n_valid} validnih + {n_invalid} nevalidnih (mesano)")
    print(f"[Simulate]   Faza 3: {n_drift_multi} multi-feature drift zahteva (koncentrovano - za detekciju)")

    #Faza 1: validni (ne drift) i nevalidni mesano
    faza1 = ["valid"] * n_valid + ["invalid"] * n_invalid
    random.shuffle(faza1)
    #Faza 2 i 3: svi drift na kraju da uzorak za Evidently bude cist drift
    types = faza1 + ["drift_multi"] * n_drift_multi

    total = n_valid + n_invalid + n_drift_multi
    success = failed = 0
    round_trips = []

    for i, tip in enumerate(types):
        row = df.sample(1).iloc[0]

        if tip == "valid":
            payload = row_to_payload(row)
            label = "valid"
        elif tip == "invalid":
            payload = make_invalid_payload()
            label = "invalid"
        else:
            payload, drifted_feature = make_multi_drift_payload(row)
            label = f"drift-multi ({drifted_feature})"

        try:
            response, round_trip_ms = send(payload)
            round_trips.append((i + 1, round_trip_ms))
            server_response_time_ms = get_latest_server_response_time()

            if response.status_code == 200: #uspesan zahtev
                data = response.json()
                success += 1
                print(f"[{i+1}/{total}] [{label}] {data['label']} ({data['probability']*100:.1f}%), round-trip: {round_trip_ms:.1f}ms, server: {server_response_time_ms:.1f}ms")
            elif response.status_code == 422: #neuspesan, validaciona
                failed += 1
                print(f"[{i+1}/{total}] [{label}] Validaciona greska, round-trip: {round_trip_ms:.1f}ms")
            else: #ostali neuspesni koji nisu validaciona
                failed += 1
                print(f"[{i+1}/{total}] [{label}] Greska: {response.status_code}, round-trip: {round_trip_ms:.1f}ms")

            log_round_trip(i + 1, label, response.status_code, round_trip_ms, server_response_time_ms)
        except Exception as e: #sirok spektar gresaka, greska u slanju, logovanju mrezi serveru bazi i sl
            failed += 1
            print(f"[{i+1}/{total}] [{label}] Konekcija failed: {e}")

        time.sleep(DELAY_SECONDS)

        #krajnji ispis radi provere
    print(f"\n[Simulate] Zavrseno! Uspesno: {success}, Neuspesno: {failed}, Drift-multi: {n_drift_multi}, Ukupno: {total}")
#sortira i racuna kao u db report
    if round_trips:
        times = sorted(t for _, t in round_trips)
        avg = sum(times) / len(times)
        median = statistics.median(times)
        p95_idx = int(round(0.95 * (len(times) - 1)))
        p95 = times[p95_idx]
        print(f"\n[Round-trip] Avg: {avg:.1f}ms, Min: {times[0]:.1f}ms, Max: {times[-1]:.1f}ms, Median: {median:.1f}ms, P95: {p95:.1f}ms")
        top5 = sorted(round_trips, key=lambda x: x[1], reverse=True)[:5]
        print("[Round-trip] Top 5 najsporijih zahteva (redni_broj, ms):")
        for idx, ms in top5:
            print(f"    #{idx}: {ms:.1f}ms")

if __name__ == "__main__":
    simulate()
