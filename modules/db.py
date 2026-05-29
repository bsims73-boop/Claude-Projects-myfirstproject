import sqlite3
from datetime import datetime
import config


def get_connection():
    conn = sqlite3.connect(str(config.DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    config.DATABASE_PATH.parent.mkdir(exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS receipts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                filename      TEXT NOT NULL UNIQUE,
                file_path     TEXT NOT NULL,
                scan_status   TEXT NOT NULL DEFAULT 'pending',
                scan_error    TEXT,
                scanned_at    DATETIME,
                receipt_date  TEXT,
                company_name  TEXT,
                total_amount  REAL,
                raw_json      TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS line_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id  INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
                item_name   TEXT,
                quantity    REAL,
                unit_price  REAL,
                line_total  REAL
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                files_found      INTEGER,
                files_new        INTEGER,
                files_processed  INTEGER,
                files_errored    INTEGER
            );
        """)


def insert_receipt(filename, file_path):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO receipts (filename, file_path, scan_status) VALUES (?, ?, 'pending')",
            (filename, str(file_path))
        )
        return cur.lastrowid


def get_receipt_by_filename(filename):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM receipts WHERE filename = ?", (filename,)
        ).fetchone()


def update_receipt_scan_result(receipt_id, date, company, total, raw_json):
    with get_connection() as conn:
        conn.execute(
            """UPDATE receipts
               SET scan_status='done', scanned_at=?, receipt_date=?,
                   company_name=?, total_amount=?, raw_json=?, scan_error=NULL
               WHERE id=?""",
            (datetime.now().isoformat(), date, company, total, raw_json, receipt_id)
        )


def update_receipt_scan_error(receipt_id, error_message):
    with get_connection() as conn:
        conn.execute(
            "UPDATE receipts SET scan_status='error', scan_error=? WHERE id=?",
            (error_message, receipt_id)
        )


def reset_receipt_to_pending(receipt_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE receipts SET scan_status='pending', scan_error=NULL WHERE id=?",
            (receipt_id,)
        )


def get_all_receipts():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM receipts ORDER BY receipt_date DESC, created_at DESC"
        ).fetchall()


def get_line_items(receipt_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM line_items WHERE receipt_id=? ORDER BY id",
            (receipt_id,)
        ).fetchall()


def insert_line_items(receipt_id, items):
    if not items:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO line_items (receipt_id, item_name, quantity, unit_price, line_total) VALUES (?,?,?,?,?)",
            [(receipt_id, i.get("name"), i.get("quantity"), i.get("unit_price"), i.get("line_total")) for i in items]
        )


def delete_line_items(receipt_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM line_items WHERE receipt_id=?", (receipt_id,))


def get_monthly_summary():
    with get_connection() as conn:
        return conn.execute("""
            SELECT
                strftime('%Y', receipt_date) AS year,
                strftime('%m', receipt_date) AS month,
                COUNT(*) AS receipt_count,
                SUM(total_amount) AS total_spend
            FROM receipts
            WHERE scan_status='done' AND receipt_date IS NOT NULL
            GROUP BY year, month
            ORDER BY year DESC, month DESC
        """).fetchall()


def get_receipts_for_export():
    with get_connection() as conn:
        receipts = conn.execute(
            "SELECT * FROM receipts WHERE scan_status='done' ORDER BY receipt_date ASC"
        ).fetchall()
        result = []
        for r in receipts:
            items = conn.execute(
                "SELECT * FROM line_items WHERE receipt_id=? ORDER BY id", (r["id"],)
            ).fetchall()
            result.append((dict(r), [dict(i) for i in items]))
        return result


def log_scan(files_found, files_new, files_processed, files_errored):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO scan_log (files_found, files_new, files_processed, files_errored) VALUES (?,?,?,?)",
            (files_found, files_new, files_processed, files_errored)
        )


def get_last_scan():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM scan_log ORDER BY run_at DESC LIMIT 1"
        ).fetchone()
