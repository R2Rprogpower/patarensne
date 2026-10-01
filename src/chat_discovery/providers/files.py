from __future__ import annotations

import csv
from pathlib import Path

from chat_discovery.models import DiscoveredCandidate
from chat_discovery.normalize import extract_telegram_links, normalize_telegram_link


class FileProvider:
    name = "file"

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths

    async def discover(self, queries: list[str] | None = None) -> list[DiscoveredCandidate]:
        found: list[DiscoveredCandidate] = []
        for path in self.paths:
            if path.suffix.casefold() == ".csv":
                found.extend(self._csv(path))
            else:
                found.extend(self._text(path))
        return found

    def _text(self, path: Path) -> list[DiscoveredCandidate]:
        candidates: list[DiscoveredCandidate] = []
        for link in extract_telegram_links(path.read_text(encoding="utf-8-sig")):
            candidates.append(
                DiscoveredCandidate(
                    url=link.url,
                    username=link.username,
                    provider=self.name,
                    source_url=str(path),
                    access_status="private" if link.private_hint else "unverified",
                )
            )
        return candidates

    def _csv(self, path: Path) -> list[DiscoveredCandidate]:
        candidates: list[DiscoveredCandidate] = []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            for row in reader:
                value = next((row.get(key) for key in ("url", "link", "telegram", "username") if row.get(key)), None)
                normalized = normalize_telegram_link(value or "")
                if normalized is None:
                    continue
                candidates.append(
                    DiscoveredCandidate(
                        url=normalized.url,
                        username=normalized.username,
                        provider=self.name,
                        source_url=str(path),
                        title=row.get("title") or row.get("name"),
                        description=row.get("description") or row.get("about"),
                        access_status="private" if normalized.private_hint else "unverified",
                        captcha_status=(row.get("captcha_status") or "unknown").casefold(),
                        captcha_evidence=row.get("captcha_evidence") or None,
                    )
                )
        return candidates
