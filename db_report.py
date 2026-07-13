import sqlite3
import statistics

DB_PATH = "predictions.db"

def report_status_counts(conn):
    print("\n Broj zahteva po statusu (potvrda da je simulacija upisala podatke)")
    rows = conn.execute("""
        SELECT status,
               COUNT(*)
        FROM predictions
        GROUP BY status
        ORDER BY COUNT(*) DESC
    """).fetchall()
    for status, count in rows:
        print(f"{status:20s} {count}")
    total = conn.execute("""
        SELECT COUNT(*)
        FROM predictions
    """).fetchone()[0]
    print(f"{'UKUPNO':20s} {total}")

def report_latency(conn):
    print("\n Latencija (response_time, iz svih uspesnih/low_confidence zahteva)")
    rows = conn.execute("""
        SELECT response_time
        FROM predictions
        WHERE status IN ('success', 'low_confidence')
          AND response_time IS NOT NULL
    """).fetchall()
    times = sorted(r[0] for r in rows)
    if not times:
        print("Nema podataka.")
        return
    avg = sum(times) / len(times)
    median = statistics.median(times)
    p95 = times[int(len(times) * 0.95)]
    print(f"Broj uzoraka: {len(times)}")
    print(f"Avg: {avg:.2f} ms")
    print(f"Min: {times[0]:.2f} ms")
    print(f"Max: {times[-1]:.2f} ms")
    print(f"Median: {median:.2f} ms")
    print(f"P95: {p95:.2f} ms")

def report_round_trip(conn):
    print("\n Round-trip latencija (client_latency_log, iz simulate_requests.py)")
    rows = conn.execute("""
        SELECT round_trip_ms,
               server_response_time_ms
        FROM client_latency_log
        WHERE round_trip_ms IS NOT NULL
    """).fetchall()
    if not rows:
        print("Nema podataka.")
        return
    round_trips = sorted(r[0] for r in rows)
    server_times = sorted(r[1] for r in rows if r[1] is not None)
    avg_rt = sum(round_trips) / len(round_trips)
    median_rt = statistics.median(round_trips)
    p95_rt = round_trips[int(len(round_trips) * 0.95)]
    print(f"Broj uzoraka: {len(round_trips)}")
    print(f"Avg: {avg_rt:.2f} ms")
    print(f"Min: {round_trips[0]:.2f} ms")
    print(f"Max: {round_trips[-1]:.2f} ms")
    print(f"Median: {median_rt:.2f} ms")
    print(f"P95: {p95_rt:.2f} ms")
    if server_times:
        avg_srv = sum(server_times) / len(server_times)
        print(f"Server-side Avg: {avg_srv:.2f} ms  (za poredjenje. deo round-trip-a koji otpada na obradu, ne mrezu)")

def report_monitoring_logs(conn):
    print("\n Zabelezeni monitoring_logs snapshoti (na svaki 100-ti validan zahtev)")
    rows = conn.execute("""
        SELECT timestamp,
               avg_latency,
               p95_latency,
               num_requests
        FROM monitoring_logs
        ORDER BY timestamp
    """).fetchall()
    if not rows:
        print("Nema podataka.")
        return
    for ts, avg, p95, n in rows:
        print(f"{ts}  avg={avg:.2f}ms  p95={p95:.2f}ms  n={n}")

def report_drift_labels(conn, n=100):
    print(f"\n Raspodela labela u periodu drifta (poslednjih {n} validnih zahteva)")
    rows = conn.execute(f"""
        SELECT label,
               COUNT(*)
        FROM (
            SELECT label
            FROM predictions
            WHERE status IN ('success', 'low_confidence')
            ORDER BY id DESC
            LIMIT {n}
        )
        GROUP BY label
    """).fetchall()
    for label, count in rows:
        print(f"{label:15s} {count}")

def report_baseline_labels(conn, n=100):
    print(f"\n Raspodela labela van perioda drifta (prethodnih {n} validnih zahteva pre drifta)")
    rows = conn.execute(f"""
        SELECT label,
               COUNT(*)
        FROM (
            SELECT label
            FROM predictions
            WHERE status IN ('success', 'low_confidence')
            ORDER BY id DESC
            LIMIT {n} OFFSET {n}
        )
        GROUP BY label
    """).fetchall()
    for label, count in rows:
        print(f"{label:15s} {count}")

if __name__ == "__main__":
    with sqlite3.connect(DB_PATH) as conn:
        report_status_counts(conn)
        report_latency(conn)
        report_round_trip(conn)
        report_monitoring_logs(conn)
        report_drift_labels(conn)
        report_baseline_labels(conn)


