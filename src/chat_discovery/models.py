from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True, frozen=True)
class NormalizedLink:
    url: str
    username: str | None
    private_hint: bool = False


@dataclass(slots=True)
class DiscoveredCandidate:
    url: str
    username: str | None
    provider: str
    telegram_id: int | None = None
    source_query: str | None = None
    source_url: str | None = None
    title: str | None = None
    description: str | None = None
    entity_type: str = "unknown"
    access_status: str = "unverified"
    members_count: int | None = None
    checked_at: str | None = None
    captcha_status: str = "unknown"
    captcha_evidence: str | None = None


@dataclass(slots=True, frozen=True)
class ActivityMetrics:
    status: str = "unknown"
    period_days: int | None = None
    messages_count: int | None = None
    unique_authors: int | None = None
    messages_per_day: float | None = None
    last_message_at: str | None = None
    days_since_last_message: float | None = None
    scanned_at: str | None = None
    unavailable_reason: str | None = None


@dataclass(slots=True)
class Candidate:
    id: int
    url: str
    username: str | None
    title: str | None
    description: str | None
    entity_type: str
    access_status: str
    members_count: int | None
    kyiv_score: int
    kyiv_reasons: list[str] = field(default_factory=list)
    discovered_at: str = ""
    checked_at: str | None = None
    telegram_id: int | None = None
    captcha_status: str = "unknown"
    captcha_evidence: str | None = None
    activity_status: str = "unknown"
    activity_period_days: int | None = None
    messages_count: int | None = None
    unique_authors: int | None = None
    messages_per_day: float | None = None
    last_message_at: str | None = None
    days_since_last_message: float | None = None
    activity_scanned_at: str | None = None
    activity_unavailable_reason: str | None = None
    sources: list[str] = field(default_factory=list)
    source_queries: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class KyivAssessment:
    score: int
    reasons: tuple[str, ...]
