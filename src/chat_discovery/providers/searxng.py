from __future__ import annotations

import asyncio

import httpx

from chat_discovery.models import DiscoveredCandidate
from chat_discovery.normalize import extract_telegram_links, normalize_telegram_link


class SearxngProvider:
    name = "searxng"

    def __init__(self, base_url: str, limit_per_query: int = 30, delay_seconds: float = 1.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.limit_per_query = limit_per_query
        self.delay_seconds = delay_seconds

    async def discover(self, queries: list[str]) -> list[DiscoveredCandidate]:
        found: list[DiscoveredCandidate] = []
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for query in queries:
                response = await client.get(
                    f"{self.base_url}/search",
                    params={"q": f"site:t.me {query}", "format": "json", "language": "all", "safesearch": 0},
                )
                response.raise_for_status()
                results = response.json().get("results", [])[: self.limit_per_query]
                for result in results:
                    source_url = str(result.get("url") or "")
                    direct = normalize_telegram_link(source_url)
                    links = [direct] if direct else extract_telegram_links(
                        " ".join(str(result.get(key) or "") for key in ("url", "title", "content"))
                    )
                    for link in links:
                        if link is None:
                            continue
                        found.append(
                            DiscoveredCandidate(
                                url=link.url,
                                username=link.username,
                                provider=self.name,
                                source_query=query,
                                source_url=source_url,
                                access_status="private" if link.private_hint else "unverified",
                            )
                        )
                await asyncio.sleep(self.delay_seconds)
        return found
