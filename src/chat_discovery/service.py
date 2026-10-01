from __future__ import annotations

import asyncio
from pathlib import Path

from telethon import errors

from chat_discovery.classify import KyivClassifier
from chat_discovery.export import export_candidates
from chat_discovery.filtering import CandidateFilters, filter_candidates
from chat_discovery.models import DiscoveredCandidate
from chat_discovery.providers.files import FileProvider
from chat_discovery.providers.base import DiscoveryProvider
from chat_discovery.providers.searxng import SearxngProvider
from chat_discovery.providers.telegram import TelegramProvider
from chat_discovery.storage import Repository


class DiscoveryService:
    def __init__(self, repository: Repository, classifier: KyivClassifier) -> None:
        self.repository = repository
        self.classifier = classifier

    async def run(
        self,
        queries: list[str],
        input_paths: list[Path],
        telegram: TelegramProvider | None,
        searxng: SearxngProvider | None,
        validate: bool,
        output_dir: Path,
        min_score: int,
        output_name: str = "telegram-results",
        activity_days: int = 0,
        active_min_messages: int = 10,
        activity_max_messages: int = 5000,
        filters: CandidateFilters = CandidateFilters(),
    ) -> dict[str, object]:
        run_id = self.repository.start_run(len(queries))
        seen_ids: set[int] = set()
        try:
            providers: list[DiscoveryProvider] = []
            if input_paths:
                providers.append(FileProvider(input_paths))
            if searxng is not None:
                providers.append(searxng)
            if telegram is not None:
                providers.append(telegram)

            for provider in providers:
                batch = await provider.discover(queries)
                for item in batch:
                    seen_ids.add(self.repository.upsert(item))

            if validate and telegram is not None:
                for candidate_id in sorted(seen_ids):
                    candidate = self.repository.get_candidate(candidate_id)
                    try:
                        validated = await telegram.validate(candidate.url, candidate.username)
                    except errors.FloodWaitError as error:
                        await asyncio.sleep(error.seconds)
                        validated = await telegram.validate(candidate.url, candidate.username)
                    self.repository.update_validation(candidate_id, validated)
                    await asyncio.sleep(0.4)

            if activity_days > 0 and telegram is not None:
                for candidate_id in sorted(seen_ids):
                    candidate = self.repository.get_candidate(candidate_id)
                    if candidate.entity_type not in {"group", "channel"}:
                        continue
                    try:
                        metrics = await telegram.scan_activity(
                            candidate.url,
                            candidate.username,
                            activity_days,
                            active_min_messages,
                            activity_max_messages,
                        )
                    except errors.FloodWaitError as error:
                        await asyncio.sleep(error.seconds)
                        metrics = await telegram.scan_activity(
                            candidate.url,
                            candidate.username,
                            activity_days,
                            active_min_messages,
                            activity_max_messages,
                        )
                    self.repository.update_activity(candidate_id, metrics)
                    await asyncio.sleep(0.4)

            all_candidates = self.repository.list_candidates()
            for candidate in all_candidates:
                self.repository.update_assessment(candidate.id, self.classifier.assess(candidate))

            all_candidates = self.repository.list_candidates()
            paths = export_candidates(all_candidates, output_dir, min_score, output_name)
            if filters.active:
                filtered = filter_candidates(all_candidates, filters)
                filtered_paths = export_candidates(
                    filtered, output_dir, min_score, f"{output_name}-filtered"
                )
                paths.update({f"filtered_{label}": path for label, path in filtered_paths.items()})
            self.repository.finish_run(run_id, "completed", len(seen_ids))
            return {"run_id": run_id, "discovered": len(seen_ids), "total": len(all_candidates), "paths": paths}
        except Exception as error:
            self.repository.finish_run(run_id, "failed", len(seen_ids), type(error).__name__)
            raise
