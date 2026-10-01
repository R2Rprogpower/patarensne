from __future__ import annotations

from dataclasses import dataclass

from chat_discovery.models import Candidate


@dataclass(slots=True, frozen=True)
class CandidateFilters:
    min_members: int | None = None
    min_messages: int | None = None
    min_unique_authors: int | None = None
    max_days_since_last_message: float | None = None
    entity_types: frozenset[str] = frozenset()
    activity_statuses: frozenset[str] = frozenset()
    captcha_statuses: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        return any(
            (
                self.min_members is not None,
                self.min_messages is not None,
                self.min_unique_authors is not None,
                self.max_days_since_last_message is not None,
                bool(self.entity_types),
                bool(self.activity_statuses),
                bool(self.captcha_statuses),
            )
        )


def filter_candidates(candidates: list[Candidate], filters: CandidateFilters) -> list[Candidate]:
    result: list[Candidate] = []
    for candidate in candidates:
        if filters.min_members is not None and (
            candidate.members_count is None or candidate.members_count < filters.min_members
        ):
            continue
        if filters.min_messages is not None and (
            candidate.messages_count is None or candidate.messages_count < filters.min_messages
        ):
            continue
        if filters.min_unique_authors is not None and (
            candidate.unique_authors is None or candidate.unique_authors < filters.min_unique_authors
        ):
            continue
        if filters.max_days_since_last_message is not None and (
            candidate.days_since_last_message is None
            or candidate.days_since_last_message > filters.max_days_since_last_message
        ):
            continue
        if filters.entity_types and candidate.entity_type not in filters.entity_types:
            continue
        if filters.activity_statuses and candidate.activity_status not in filters.activity_statuses:
            continue
        if filters.captcha_statuses and candidate.captcha_status not in filters.captcha_statuses:
            continue
        result.append(candidate)
    return result
