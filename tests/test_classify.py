import json
from pathlib import Path

from chat_discovery.classify import KyivClassifier
from chat_discovery.models import Candidate


def candidate(**overrides: object) -> Candidate:
    values = {
        "id": 1,
        "url": "https://t.me/examplechat",
        "username": "examplechat",
        "title": None,
        "description": None,
        "entity_type": "group",
        "access_status": "open",
        "members_count": None,
        "kyiv_score": 0,
    }
    values.update(overrides)
    return Candidate(**values)


def test_scores_city_and_district_terms(tmp_path: Path) -> None:
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"city_terms": ["Київ"], "district_terms": ["Оболонь"]}), encoding="utf-8")
    classifier = KyivClassifier(terms)

    result = classifier.assess(candidate(title="Київ — Оболонь чат"))

    assert result.score == 10
    assert "city:київ@title" in result.reasons
    assert "district:оболонь@title" in result.reasons


def test_query_is_only_a_weak_signal(tmp_path: Path) -> None:
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"city_terms": ["Київ"], "district_terms": []}), encoding="utf-8")
    classifier = KyivClassifier(terms)

    result = classifier.assess(candidate(source_queries=["Київ чат"]))

    assert result.score == 1
