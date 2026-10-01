from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from chat_discovery.models import ActivityMetrics, Candidate, DiscoveredCandidate, KyivAssessment, utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS discovery_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    query_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    username TEXT,
    telegram_id INTEGER,
    title TEXT,
    description TEXT,
    entity_type TEXT NOT NULL DEFAULT 'unknown',
    access_status TEXT NOT NULL DEFAULT 'unverified',
    members_count INTEGER,
    kyiv_score INTEGER NOT NULL DEFAULT 0,
    kyiv_reasons_json TEXT NOT NULL DEFAULT '[]',
    discovered_at TEXT NOT NULL,
    checked_at TEXT
    ,captcha_status TEXT NOT NULL DEFAULT 'unknown'
    ,captcha_evidence TEXT
    ,activity_status TEXT NOT NULL DEFAULT 'unknown'
    ,activity_period_days INTEGER
    ,messages_count INTEGER
    ,unique_authors INTEGER
    ,messages_per_day REAL
    ,last_message_at TEXT
    ,days_since_last_message REAL
    ,activity_scanned_at TEXT
    ,activity_unavailable_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS candidates_username_unique
ON candidates(username) WHERE username IS NOT NULL;

CREATE TABLE IF NOT EXISTS candidate_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    source_query TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    discovered_at TEXT NOT NULL,
    UNIQUE(candidate_id, provider, source_query, source_url)
);
"""


class Repository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(candidates)").fetchall()
        }
        migrations = {
            "telegram_id": "INTEGER",
            "captcha_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "captcha_evidence": "TEXT",
            "activity_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "activity_period_days": "INTEGER",
            "messages_count": "INTEGER",
            "unique_authors": "INTEGER",
            "messages_per_day": "REAL",
            "last_message_at": "TEXT",
            "days_since_last_message": "REAL",
            "activity_scanned_at": "TEXT",
            "activity_unavailable_reason": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE candidates ADD COLUMN {name} {definition}")
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS candidates_telegram_id_unique "
            "ON candidates(telegram_id) WHERE telegram_id IS NOT NULL"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def start_run(self, query_count: int) -> int:
        cursor = self.connection.execute(
            "INSERT INTO discovery_runs(started_at, status, query_count) VALUES (?, 'running', ?)",
            (utc_now(), query_count),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, candidate_count: int, error: str | None = None) -> None:
        self.connection.execute(
            "UPDATE discovery_runs SET finished_at=?, status=?, candidate_count=?, error=? WHERE id=?",
            (utc_now(), status, candidate_count, error, run_id),
        )
        self.connection.commit()

    def upsert(self, item: DiscoveredCandidate) -> int:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO candidates(
                url, username, telegram_id, title, description, entity_type, access_status,
                members_count, discovered_at, checked_at, captcha_status, captcha_evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                username=COALESCE(excluded.username, candidates.username),
                telegram_id=COALESCE(excluded.telegram_id, candidates.telegram_id),
                title=CASE
                    WHEN excluded.checked_at IS NOT NULL OR candidates.title IS NULL THEN COALESCE(excluded.title, candidates.title)
                    ELSE candidates.title
                END,
                description=CASE
                    WHEN excluded.checked_at IS NOT NULL OR candidates.description IS NULL THEN COALESCE(excluded.description, candidates.description)
                    ELSE candidates.description
                END,
                entity_type=CASE WHEN excluded.entity_type='unknown' THEN candidates.entity_type ELSE excluded.entity_type END,
                access_status=CASE WHEN excluded.access_status='unverified' THEN candidates.access_status ELSE excluded.access_status END,
                members_count=COALESCE(excluded.members_count, candidates.members_count),
                checked_at=COALESCE(excluded.checked_at, candidates.checked_at),
                captcha_status=CASE WHEN excluded.captcha_status='unknown' THEN candidates.captcha_status ELSE excluded.captcha_status END,
                captcha_evidence=COALESCE(excluded.captcha_evidence, candidates.captcha_evidence)
            """,
            (
                item.url,
                item.username,
                item.telegram_id,
                item.title,
                item.description,
                item.entity_type,
                item.access_status,
                item.members_count,
                now,
                item.checked_at,
                item.captcha_status,
                item.captcha_evidence,
            ),
        )
        row = self.connection.execute("SELECT id FROM candidates WHERE url=?", (item.url,)).fetchone()
        assert row is not None
        candidate_id = int(row["id"])
        self.connection.execute(
            """
            INSERT OR IGNORE INTO candidate_sources(
                candidate_id, provider, source_query, source_url, discovered_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (candidate_id, item.provider, item.source_query or "", item.source_url or "", now),
        )
        self.connection.commit()
        return candidate_id

    def update_validation(self, candidate_id: int, item: DiscoveredCandidate) -> None:
        self.connection.execute(
            """
            UPDATE candidates SET
                username=COALESCE(?, username), telegram_id=COALESCE(?, telegram_id), title=COALESCE(?, title),
                description=COALESCE(?, description), entity_type=?, access_status=?,
                members_count=?, checked_at=?,
                captcha_status=CASE WHEN ?='unknown' THEN captcha_status ELSE ? END,
                captcha_evidence=COALESCE(?, captcha_evidence)
            WHERE id=?
            """,
            (
                item.username,
                item.telegram_id,
                item.title,
                item.description,
                item.entity_type,
                item.access_status,
                item.members_count,
                item.checked_at or utc_now(),
                item.captcha_status,
                item.captcha_status,
                item.captcha_evidence,
                candidate_id,
            ),
        )
        self.connection.commit()

    def update_activity(self, candidate_id: int, metrics: ActivityMetrics) -> None:
        self.connection.execute(
            """
            UPDATE candidates SET
                activity_status=?, activity_period_days=?, messages_count=?,
                unique_authors=?, messages_per_day=?, last_message_at=?,
                days_since_last_message=?, activity_scanned_at=?,
                activity_unavailable_reason=?
            WHERE id=?
            """,
            (
                metrics.status,
                metrics.period_days,
                metrics.messages_count,
                metrics.unique_authors,
                metrics.messages_per_day,
                metrics.last_message_at,
                metrics.days_since_last_message,
                metrics.scanned_at or utc_now(),
                metrics.unavailable_reason,
                candidate_id,
            ),
        )
        self.connection.commit()

    def update_assessment(self, candidate_id: int, assessment: KyivAssessment) -> None:
        self.connection.execute(
            "UPDATE candidates SET kyiv_score=?, kyiv_reasons_json=? WHERE id=?",
            (assessment.score, json.dumps(assessment.reasons, ensure_ascii=False), candidate_id),
        )
        self.connection.commit()

    def list_candidates(self) -> list[Candidate]:
        rows = self.connection.execute(
            """
            SELECT c.*,
                   GROUP_CONCAT(DISTINCT s.provider) AS sources,
                   GROUP_CONCAT(DISTINCT NULLIF(s.source_query, '')) AS source_queries
            FROM candidates c
            LEFT JOIN candidate_sources s ON s.candidate_id=c.id
            GROUP BY c.id
            ORDER BY c.kyiv_score DESC, c.members_count DESC, c.url ASC
            """
        ).fetchall()
        return [self._candidate(row) for row in rows]

    def get_candidate(self, candidate_id: int) -> Candidate:
        row = self.connection.execute(
            """
            SELECT c.*,
                   GROUP_CONCAT(DISTINCT s.provider) AS sources,
                   GROUP_CONCAT(DISTINCT NULLIF(s.source_query, '')) AS source_queries
            FROM candidates c
            LEFT JOIN candidate_sources s ON s.candidate_id=c.id
            WHERE c.id=? GROUP BY c.id
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return self._candidate(row)

    @staticmethod
    def _candidate(row: sqlite3.Row) -> Candidate:
        return Candidate(
            id=int(row["id"]),
            url=str(row["url"]),
            username=row["username"],
            telegram_id=row["telegram_id"],
            title=row["title"],
            description=row["description"],
            entity_type=str(row["entity_type"]),
            access_status=str(row["access_status"]),
            members_count=row["members_count"],
            kyiv_score=int(row["kyiv_score"]),
            kyiv_reasons=list(json.loads(row["kyiv_reasons_json"])),
            discovered_at=str(row["discovered_at"]),
            checked_at=row["checked_at"],
            captcha_status=str(row["captcha_status"]),
            captcha_evidence=row["captcha_evidence"],
            activity_status=str(row["activity_status"]),
            activity_period_days=row["activity_period_days"],
            messages_count=row["messages_count"],
            unique_authors=row["unique_authors"],
            messages_per_day=row["messages_per_day"],
            last_message_at=row["last_message_at"],
            days_since_last_message=row["days_since_last_message"],
            activity_scanned_at=row["activity_scanned_at"],
            activity_unavailable_reason=row["activity_unavailable_reason"],
            sources=[value for value in (row["sources"] or "").split(",") if value],
            source_queries=[value for value in (row["source_queries"] or "").split(",") if value],
        )
