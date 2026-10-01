from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from chat_discovery.models import Candidate


CSV_FIELDS = [
    "url",
    "username",
    "telegram_id",
    "title",
    "description",
    "entity_type",
    "access_status",
    "members_count",
    "captcha_status",
    "captcha_evidence",
    "activity_status",
    "activity_period_days",
    "messages_count",
    "unique_authors",
    "messages_per_day",
    "last_message_at",
    "days_since_last_message",
    "activity_scanned_at",
    "activity_unavailable_reason",
    "relevance_score",
    "relevance_reasons",
    "sources",
    "source_queries",
    "discovered_at",
    "checked_at",
]


def serialize_candidate(candidate: Candidate) -> dict[str, object]:
    data = asdict(candidate)
    data["relevance_score"] = data.pop("kyiv_score")
    data["relevance_reasons"] = data.pop("kyiv_reasons")
    return data


def export_candidates(
    candidates: list[Candidate],
    output_dir: Path,
    min_score: int,
    output_name: str = "telegram-results",
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    relevant = [candidate for candidate in candidates if candidate.kyiv_score >= min_score]
    csv_path = output_dir / f"{output_name}.csv"
    json_path = output_dir / f"{output_name}.json"
    txt_path = output_dir / f"{output_name}.txt"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        for candidate in relevant:
            writer.writerow(
                {
                    "url": candidate.url,
                    "username": candidate.username or "",
                    "telegram_id": candidate.telegram_id if candidate.telegram_id is not None else "",
                    "title": candidate.title or "",
                    "description": candidate.description or "",
                    "entity_type": candidate.entity_type,
                    "access_status": candidate.access_status,
                    "members_count": candidate.members_count if candidate.members_count is not None else "",
                    "captcha_status": candidate.captcha_status,
                    "captcha_evidence": candidate.captcha_evidence or "",
                    "activity_status": candidate.activity_status,
                    "activity_period_days": candidate.activity_period_days or "",
                    "messages_count": candidate.messages_count if candidate.messages_count is not None else "",
                    "unique_authors": candidate.unique_authors if candidate.unique_authors is not None else "",
                    "messages_per_day": candidate.messages_per_day if candidate.messages_per_day is not None else "",
                    "last_message_at": candidate.last_message_at or "",
                    "days_since_last_message": candidate.days_since_last_message if candidate.days_since_last_message is not None else "",
                    "activity_scanned_at": candidate.activity_scanned_at or "",
                    "activity_unavailable_reason": candidate.activity_unavailable_reason or "",
                    "relevance_score": candidate.kyiv_score,
                    "relevance_reasons": " | ".join(candidate.kyiv_reasons),
                    "sources": " | ".join(candidate.sources),
                    "source_queries": " | ".join(candidate.source_queries),
                    "discovered_at": candidate.discovered_at,
                    "checked_at": candidate.checked_at or "",
                }
            )

    json_path.write_text(
        json.dumps([serialize_candidate(candidate) for candidate in relevant], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scan_urls = [
        candidate.url
        for candidate in relevant
        if candidate.entity_type in {"group", "unknown"}
        and candidate.access_status in {"open", "approval_required", "unverified"}
    ]
    txt_path.write_text("".join(f"{url}\n" for url in scan_urls), encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "scanner_input": txt_path}
