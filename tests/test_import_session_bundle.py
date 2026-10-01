from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

from scripts.import_session_bundle import load_session_files, render_env


def test_load_session_bundle_reads_only_required_values(tmp_path) -> None:
    bundle_path = tmp_path / "bundle.zip"
    with ZipFile(bundle_path, "w") as bundle:
        bundle.writestr("account/session.session", b"SQLite format 3\x00test-data")
        bundle.writestr(
            "account/config.json",
            json.dumps({"app_id": 12345, "app_hash": "example-hash", "profile": "ignored"}),
        )
        bundle.writestr("account/unrelated.txt", "must not be imported")

    session, app_id, app_hash = load_session_files(bundle_path)

    assert session == b"SQLite format 3\x00test-data"
    assert app_id == 12345
    assert app_hash == "example-hash"


def test_load_session_bundle_rejects_ambiguous_sessions(tmp_path) -> None:
    bundle_path = tmp_path / "bundle.zip"
    with ZipFile(bundle_path, "w") as bundle:
        bundle.writestr("one.session", b"SQLite format 3\x00one")
        bundle.writestr("two.session", b"SQLite format 3\x00two")
        bundle.writestr("config.json", json.dumps({"app_id": 1, "app_hash": "hash"}))

    with pytest.raises(RuntimeError, match="exactly one .session"):
        load_session_files(bundle_path)


def test_render_env_replaces_placeholders_without_printing_values() -> None:
    rendered = render_env(
        "DATA_DIR=/app/data\nTELEGRAM_API_ID=\nTELEGRAM_API_HASH=\n",
        12345,
        "example-hash",
    )

    assert "TELEGRAM_API_ID=12345" in rendered
    assert "TELEGRAM_API_HASH=example-hash" in rendered
