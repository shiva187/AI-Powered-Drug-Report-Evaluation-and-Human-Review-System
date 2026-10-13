import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "drug_reports.db"

def get_connection(db_path=DEFAULT_DB):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=DEFAULT_DB):
    with get_connection(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS drug_reports (
            report_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'synthetic_or_uploaded',
            extracted_json TEXT NOT NULL,
            current_json TEXT NOT NULL,
            evaluation_json TEXT NOT NULL,
            processing_status TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'PENDING',
            extraction_mode TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evaluation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            check_name TEXT NOT NULL,
            status TEXT NOT NULL,
            observed_value TEXT,
            criterion TEXT,
            explanation TEXT,
            category TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES drug_reports(report_id)
        );
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            action TEXT NOT NULL,
            original_json TEXT,
            revised_json TEXT,
            reviewer TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES drug_reports(report_id)
        );
        CREATE TABLE IF NOT EXISTS approved_records (
            report_id TEXT PRIMARY KEY,
            approved_json TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES drug_reports(report_id)
        );
        """)

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def upsert_pending(report_id, filename, extracted, current, evaluation, extraction_mode, db_path=DEFAULT_DB):
    now = utc_now()
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO drug_reports
        (report_id, filename, extracted_json, current_json, evaluation_json,
         processing_status, review_status, extraction_mode, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'PROCESSED', 'PENDING', ?, ?, ?)
        ON CONFLICT(report_id) DO UPDATE SET
          filename=excluded.filename, extracted_json=excluded.extracted_json,
          current_json=excluded.current_json, evaluation_json=excluded.evaluation_json,
          processing_status='PROCESSED', review_status='PENDING',
          extraction_mode=excluded.extraction_mode, updated_at=excluded.updated_at
        """, (report_id, filename, json.dumps(extracted), json.dumps(current),
              json.dumps(evaluation), extraction_mode, now, now))
        conn.execute("DELETE FROM evaluation_results WHERE report_id=?", (report_id,))
        for check in evaluation.get("checks", []):
            conn.execute("""
            INSERT INTO evaluation_results
            (report_id, check_name, status, observed_value, criterion, explanation, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (report_id, check["check_name"], check["status"],
                  str(check.get("observed_value")), str(check.get("criterion")),
                  check.get("explanation"), check.get("category"), now))

def save_review(report_id, action, original, revised, reviewer, comment="", db_path=DEFAULT_DB):
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO review_history (report_id, action, original_json, revised_json, reviewer, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (report_id, action, json.dumps(original), json.dumps(revised), reviewer,
              comment, utc_now()))

def approve_record(report_id, current, reviewer, db_path=DEFAULT_DB):
    now = utc_now()
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO approved_records (report_id, approved_json, reviewer, approved_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(report_id) DO UPDATE SET approved_json=excluded.approved_json,
          reviewer=excluded.reviewer, approved_at=excluded.approved_at
        """, (report_id, json.dumps(current), reviewer, now))
        conn.execute("UPDATE drug_reports SET current_json=?, review_status='APPROVED', updated_at=? WHERE report_id=?",
                     (json.dumps(current), now, report_id))

def set_rejected(report_id, db_path=DEFAULT_DB):
    with get_connection(db_path) as conn:
        conn.execute("UPDATE drug_reports SET review_status='REJECTED', updated_at=? WHERE report_id=?",
                     (utc_now(), report_id))

def update_current(report_id, current, evaluation, db_path=DEFAULT_DB):
    now = utc_now()
    with get_connection(db_path) as conn:
        conn.execute("UPDATE drug_reports SET current_json=?, evaluation_json=?, review_status='PENDING', updated_at=? WHERE report_id=?",
                     (json.dumps(current), json.dumps(evaluation), now, report_id))
        conn.execute("DELETE FROM evaluation_results WHERE report_id=?", (report_id,))
        for check in evaluation.get("checks", []):
            conn.execute("""
            INSERT INTO evaluation_results
            (report_id, check_name, status, observed_value, criterion, explanation, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (report_id, check["check_name"], check["status"],
                  str(check.get("observed_value")), str(check.get("criterion")),
                  check.get("explanation"), check.get("category"), now))

def fetch_dashboard(db_path=DEFAULT_DB):
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM drug_reports ORDER BY created_at DESC").fetchall()
        approved = conn.execute("SELECT COUNT(*) AS n FROM approved_records").fetchone()["n"]
        history = conn.execute("SELECT COUNT(*) AS n FROM review_history").fetchone()["n"]
    return [dict(r) for r in rows], approved, history
