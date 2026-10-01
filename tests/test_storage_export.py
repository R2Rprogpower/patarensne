import csv
import json
import sqlite3
from pathlib import Path

from chat_discovery.export import export_candidates
from chat_discovery.models import DiscoveredCandidate, KyivAssessment
from chat_discovery.storage import Repository


def test_repository_migrates_existing_candidate_table(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            username TEXT,
            title TEXT,
            description TEXT,
            entity_type TEXT NOT NULL DEFAULT 'unknown',
            access_status TEXT NOT NULL DEFAULT 'unverified',
            members_count INTEGER,
            kyiv_score INTEGER NOT NULL DEFAULT 0,
            kyiv_reasons_json TEXT NOT NULL DEFAULT '[]',
            discovered_at TEXT NOT NULL,
            checked_at TEXT
        );
        """
    )
    connection.close()

    repository = Repository(database)
    try:
        columns = {
            row["name"] for row in repository.connection.execute("PRAGMA table_info(candidates)")
        }
        assert {"telegram_id", "captcha_status", "activity_status", "messages_count"} <= columns
    finally:
        repository.close()


def test_repository_deduplicates_and_preserves_sources(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "db.sqlite3")
    try:
        first_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivchat",
                username="kyivchat",
                provider="file",
                source_url="seed.txt",
            )
        )
        second_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivchat",
                username="kyivchat",
                provider="telegram",
                source_query="Київ чат",
                title="Київський чат",
                entity_type="group",
                access_status="open",
            )
        )
        repository.update_assessment(first_id, KyivAssessment(7, ("city:київ@title",)))
        item = repository.get_candidate(first_id)

        assert first_id == second_id
        assert item.title == "Київський чат"
        assert set(item.sources) == {"file", "telegram"}
        assert item.kyiv_score == 7
    finally:
        repository.close()


def test_export_creates_scanner_input_for_groups_only(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "db.sqlite3")
    try:
        group_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivchat",
                username="kyivchat",
                provider="telegram",
                title="Київ чат",
                entity_type="group",
                access_status="open",
            )
        )
        channel_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivnews",
                username="kyivnews",
                provider="telegram",
                title="Київ новини",
                entity_type="channel",
                access_status="channel",
            )
        )
        repository.update_assessment(group_id, KyivAssessment(8, ("city",)))
        repository.update_assessment(channel_id, KyivAssessment(8, ("city",)))
        paths = export_candidates(repository.list_candidates(), tmp_path / "exports", min_score=4)

        assert paths["csv"].name == "telegram-results.csv"
        assert paths["json"].name == "telegram-results.json"
        assert paths["scanner_input"].name == "telegram-results.txt"
        assert paths["scanner_input"].read_text(encoding="utf-8") == "https://t.me/kyivchat\n"
        with paths["csv"].open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        assert len(rows) == 2
        assert "relevance_score" in rows[0]
        assert "relevance_reasons" in rows[0]
        assert "captcha_status" in rows[0]
        assert "activity_status" in rows[0]
        assert "messages_count" in rows[0]
        json_rows = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert "relevance_score" in json_rows[0]
        assert "relevance_reasons" in json_rows[0]
        assert "captcha_status" in json_rows[0]
        assert "activity_status" in json_rows[0]
        assert "kyiv_score" not in json_rows[0]
    finally:
        repository.close()


def test_file_duplicate_does_not_replace_better_existing_metadata(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "db.sqlite3")
    try:
        first_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivchat",
                username="kyivchat",
                provider="file",
                title="Київський чат",
            )
        )
        repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/kyivchat",
                username="kyivchat",
                provider="file",
                title="duplicate",
            )
        )

        assert repository.get_candidate(first_id).title == "Київський чат"
    finally:
        repository.close()
