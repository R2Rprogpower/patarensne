from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from chat_discovery.models import Candidate, KyivAssessment


def _fold(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return re.sub(r"[^\wа-яіїєґ']+", " ", normalized, flags=re.UNICODE).strip()


class KyivClassifier:
    def __init__(self, terms_path: Path) -> None:
        payload = json.loads(terms_path.read_text(encoding="utf-8"))
        self.city_terms = tuple(_fold(item) for item in payload["city_terms"])
        self.district_terms = tuple(_fold(item) for item in payload["district_terms"])

    def assess(self, candidate: Candidate) -> KyivAssessment:
        fields = {
            "title": _fold(candidate.title),
            "description": _fold(candidate.description),
            "username": _fold(candidate.username),
        }
        score = 0
        reasons: list[str] = []

        for field, weight in (("title", 6), ("description", 4), ("username", 3)):
            matches = [term for term in self.city_terms if term and term in fields[field]]
            if matches:
                term = max(matches, key=len)
                score += weight
                reasons.append(f"city:{term}@{field}")

        for field, weight in (("title", 4), ("description", 2), ("username", 2)):
            matches = [term for term in self.district_terms if term and term in fields[field]]
            if matches:
                term = max(matches, key=len)
                score += weight
                reasons.append(f"district:{term}@{field}")

        query_text = _fold(" ".join(candidate.source_queries))
        if any(term in query_text for term in self.city_terms):
            score += 1
            reasons.append("city:source_query")

        return KyivAssessment(score=min(score, 100), reasons=tuple(dict.fromkeys(reasons)))
