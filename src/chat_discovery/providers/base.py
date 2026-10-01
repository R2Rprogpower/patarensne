from __future__ import annotations

from typing import Protocol

from chat_discovery.models import DiscoveredCandidate


class DiscoveryProvider(Protocol):
    name: str

    async def discover(self, queries: list[str]) -> list[DiscoveredCandidate]: ...
