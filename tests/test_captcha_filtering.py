from pathlib import Path

from chat_discovery.captcha import detect_captcha
from chat_discovery.filtering import CandidateFilters, filter_candidates
from chat_discovery.models import ActivityMetrics, DiscoveredCandidate
from chat_discovery.storage import Repository


def test_captcha_detection_requires_positive_evidence() -> None:
    assert detect_captcha("Welcome", "Complete CAPTCHA via @shieldy_bot")[0] == "yes"
    assert detect_captcha("Ordinary public chat", "Be kind") == (
        "unknown",
        "not determinable from public metadata",
    )


def test_activity_and_captcha_fields_are_persisted_and_filterable(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "db.sqlite3")
    try:
        candidate_id = repository.upsert(
            DiscoveredCandidate(
                url="https://t.me/examplechat",
                username="examplechat",
                telegram_id=1234,
                provider="telegram",
                title="Example",
                entity_type="group",
                access_status="open",
                members_count=250,
                captcha_status="yes",
                captcha_evidence="known verification bot: @shieldy_bot",
            )
        )
        repository.update_activity(
            candidate_id,
            ActivityMetrics(
                status="active",
                period_days=7,
                messages_count=70,
                unique_authors=12,
                messages_per_day=10.0,
                last_message_at="2026-09-30T12:00:00+00:00",
                days_since_last_message=0.5,
                scanned_at="2026-10-01T00:00:00+00:00",
            ),
        )
        candidates = repository.list_candidates()

        assert candidates[0].telegram_id == 1234
        assert candidates[0].captcha_status == "yes"
        assert candidates[0].messages_count == 70
        assert filter_candidates(
            candidates,
            CandidateFilters(
                min_members=200,
                min_messages=50,
                min_unique_authors=10,
                max_days_since_last_message=1,
                entity_types=frozenset({"group"}),
                activity_statuses=frozenset({"active"}),
                captcha_statuses=frozenset({"yes"}),
            ),
        ) == candidates
        assert filter_candidates(candidates, CandidateFilters(min_messages=100)) == []
    finally:
        repository.close()
