import sqlite3
import os
from boss_analyzer.models.snapshot import JobSnapshot
from boss_analyzer.config import TRACKING_DB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS job_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    job_url     TEXT NOT NULL,
    job_title   TEXT NOT NULL,
    salary_min  INTEGER DEFAULT 0,
    salary_max  INTEGER DEFAULT 0,
    experience_req TEXT DEFAULT '',
    education_req  TEXT DEFAULT '',
    skills_json    TEXT DEFAULT '[]',
    description_hash TEXT DEFAULT '',
    hr_active_time TEXT DEFAULT '',
    hr_active_days INTEGER DEFAULT 999,
    captured_at TEXT NOT NULL,
    run_id      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracking_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    job_count    INTEGER DEFAULT 0,
    ran_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshot_company
    ON job_snapshots(company_name, run_id);
"""


class JobStore:
    def __init__(self, db_path: str = TRACKING_DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(DDL)

    def save_snapshots(self, company_name: str, snapshots: list, run_id: str, ran_at: str):
        with self._connect() as conn:
            conn.executemany(
                """INSERT INTO job_snapshots
                   (company_name, job_url, job_title, salary_min, salary_max,
                    experience_req, education_req, skills_json, description_hash,
                    hr_active_time, hr_active_days, captured_at, run_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        s.company_name, s.job_url, s.job_title,
                        s.salary_min, s.salary_max,
                        s.experience_req, s.education_req,
                        s.skills_json, s.description_hash,
                        s.hr_active_time, s.hr_active_days,
                        s.captured_at, s.run_id,
                    )
                    for s in snapshots
                ],
            )
            conn.execute(
                "INSERT INTO tracking_runs (company_name, run_id, job_count, ran_at) VALUES (?,?,?,?)",
                (company_name, run_id, len(snapshots), ran_at),
            )

    def get_last_snapshots(self, company_name: str) -> list:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id FROM tracking_runs WHERE company_name=? ORDER BY id DESC LIMIT 1 OFFSET 1",
                (company_name,),
            ).fetchone()
            if not row:
                return []
            run_id = row["run_id"]
            rows = conn.execute(
                "SELECT * FROM job_snapshots WHERE company_name=? AND run_id=?",
                (company_name, run_id),
            ).fetchall()
            return [_row_to_snapshot(r) for r in rows]

    def get_run_history(self, company_name: str, limit: int = 10) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tracking_runs WHERE company_name=? ORDER BY id DESC LIMIT ?",
                (company_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_snapshot_history(self, company_name: str, job_url: str, limit: int = 8) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT *
                   FROM job_snapshots
                   WHERE company_name=? AND job_url=?
                   ORDER BY id DESC
                   LIMIT ?""",
                (company_name, job_url, limit),
            ).fetchall()
            return [_row_to_snapshot(r) for r in reversed(rows)]


def _row_to_snapshot(row: sqlite3.Row) -> JobSnapshot:
    return JobSnapshot(
        job_url=row["job_url"],
        company_name=row["company_name"],
        job_title=row["job_title"],
        salary_min=row["salary_min"],
        salary_max=row["salary_max"],
        experience_req=row["experience_req"],
        education_req=row["education_req"],
        skills_json=row["skills_json"],
        description_hash=row["description_hash"],
        hr_active_time=row["hr_active_time"],
        hr_active_days=row["hr_active_days"],
        captured_at=row["captured_at"],
        run_id=row["run_id"],
    )
