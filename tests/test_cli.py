from pathlib import Path

import argparse

import pytest

from chat_discovery.cli import build_parser, output_name, resolve_queries


def test_resolve_queries_combines_file_and_direct_values(tmp_path: Path) -> None:
    query_file = tmp_path / "queries.txt"
    query_file.write_text("first query\n# comment\nsecond query\n", encoding="utf-8")

    assert resolve_queries(query_file, [" second query ", "third query"]) == [
        "first query",
        "second query",
        "third query",
    ]


def test_resolve_queries_accepts_direct_values_without_file() -> None:
    assert resolve_queries(None, [" public groups ", "", "public groups"]) == ["public groups"]


def test_output_name_rejects_paths() -> None:
    assert output_name("telegram-results_2026.09") == "telegram-results_2026.09"
    with pytest.raises(argparse.ArgumentTypeError):
        output_name("../secrets")


def test_discover_activity_and_filter_options() -> None:
    args = build_parser().parse_args(
        [
            "discover",
            "--activity-days",
            "7",
            "--min-messages",
            "20",
            "--activity-status",
            "active",
            "--captcha-status",
            "unknown",
        ]
    )
    assert args.activity_days == 7
    assert args.min_messages == 20
    assert args.activity_status == ["active"]
    assert args.captcha_status == ["unknown"]
