import json
import sqlite3
from datetime import datetime

DB_PATH = "predictions.db" #glavna database 
#sadrzi sledece (dole)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        #vrednosti obelezja koje je korisnik uneo, labelu, verovatnocu, response time i status
        cursor.execute(""" 
            CREATE TABLE IF NOT EXISTS predictions ( 
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp             TEXT NOT NULL,
                fixed_acidity         REAL,
                volatile_acidity      REAL,
                citric_acid           REAL,
                residual_sugar        REAL,
                chlorides             REAL,
                free_sulfur_dioxide   REAL,
                total_sulfur_dioxide  REAL,
                density               REAL,
                pH                    REAL,
                sulphates             REAL,
                alcohol               REAL,
                label                 TEXT,
                probability           REAL,
                response_time         REAL,
                status                TEXT NOT NULL DEFAULT 'success'
            )
        """)
        try:
            cursor.execute("ALTER TABLE predictions ADD COLUMN status TEXT NOT NULL DEFAULT 'success'")
        except sqlite3.OperationalError:
            pass
        #monitoring tabela id i vreme, statiscke vrednsoti za latenciju i broj zahteva
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT NOT NULL,
                avg_latency    REAL,
                min_latency    REAL,
                max_latency    REAL,
                p95_latency    REAL,
                median_latency REAL,
                num_requests   INTEGER
            )
        """)
        try:
            cursor.execute("ALTER TABLE monitoring_logs ADD COLUMN p95_latency REAL")
        except sqlite3.OperationalError:
            pass #kolona vec postoji ako baza nije prvi put napravljena, CREATE TABLE iznad se ne izvrsava ako tabela vec postoji
        try:
            cursor.execute("ALTER TABLE monitoring_logs ADD COLUMN median_latency REAL")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                error_type TEXT NOT NULL,
                input_data TEXT,
                details    TEXT
            )
        """)
        conn.commit()
#upis u gorepomenutu predictions
def log_prediction(input_data: dict, label: str = None, probability: float = None, response_time: float = None, status: str = "success"):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO predictions (
                timestamp, fixed_acidity, volatile_acidity, citric_acid,
                residual_sugar, chlorides, free_sulfur_dioxide, total_sulfur_dioxide,
                density, pH, sulphates, alcohol, label, probability, response_time, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            input_data.get("fixed_acidity"),
            input_data.get("volatile_acidity"),
            input_data.get("citric_acid"),
            input_data.get("residual_sugar"),
            input_data.get("chlorides"),
            input_data.get("free_sulfur_dioxide"),
            input_data.get("total_sulfur_dioxide"),
            input_data.get("density"),
            input_data.get("pH"),
            input_data.get("sulphates"),
            input_data.get("alcohol"),
            label,
            probability,
            response_time,
            status
        ))
        conn.commit()

    print(f"[DB] log_prediction status={status}", flush=True)
#upis u pomenutu incidents tabelu 
def log_incident(error_type: str, input_data: dict, details: str = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (timestamp, error_type, input_data, details)
            VALUES (?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            error_type,
            json.dumps(input_data),
            details
        ))
        conn.commit()

    print(f"[DB] log_incident error_type={error_type}", flush=True)
