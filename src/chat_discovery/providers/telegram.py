from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from telethon import TelegramClient, errors, functions, types

from chat_discovery.captcha import detect_captcha
from chat_discovery.models import ActivityMetrics, DiscoveredCandidate, utc_now
from chat_discovery.normalize import normalize_telegram_link


class TelegramProvider:
    name = "telegram"

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: Path,
        limit_per_query: int = 50,
        delay_seconds: float = 1.0,
    ) -> None:
        self.client = TelegramClient(str(session_path), api_id, api_hash)
        self.limit_per_query = min(limit_per_query, 100)
        self.delay_seconds = delay_seconds

    async def __aenter__(self) -> TelegramProvider:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError("Telegram session is not authorized. Run the local auth command first.")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.disconnect()

    async def discover(self, queries: list[str]) -> list[DiscoveredCandidate]:
        found: list[DiscoveredCandidate] = []
        for query in queries:
            try:
                result = await self.client(functions.contacts.SearchRequest(q=query, limit=self.limit_per_query))
            except errors.FloodWaitError as error:
                await asyncio.sleep(error.seconds)
                result = await self.client(functions.contacts.SearchRequest(q=query, limit=self.limit_per_query))

            for entity in result.chats:
                candidate = self._from_entity(entity, query)
                if candidate is not None:
                    found.append(candidate)
            await asyncio.sleep(self.delay_seconds)
        return found

    async def validate(self, url: str, username: str | None) -> DiscoveredCandidate:
        if username is None:
            return DiscoveredCandidate(
                url=url,
                username=None,
                provider=self.name,
                entity_type="group",
                access_status="private",
                checked_at=utc_now(),
            )
        try:
            entity = await self.client.get_entity(username)
            candidate = self._from_entity(entity, None)
            if candidate is None:
                return DiscoveredCandidate(
                    url=url,
                    username=username,
                    provider=self.name,
                    entity_type="user",
                    access_status="not_group",
                    checked_at=utc_now(),
                )

            if isinstance(entity, types.Channel):
                try:
                    full = await self.client(functions.channels.GetFullChannelRequest(entity))
                    candidate.description = full.full_chat.about or None
                    candidate.members_count = full.full_chat.participants_count
                except (errors.ChatAdminRequiredError, errors.ChannelPrivateError):
                    pass
            candidate.captcha_status, candidate.captcha_evidence = detect_captcha(
                candidate.title, candidate.description
            )
            candidate.checked_at = utc_now()
            return candidate
        except errors.FloodWaitError:
            raise
        except errors.ChannelPrivateError:
            return DiscoveredCandidate(
                url=url,
                username=username,
                provider=self.name,
                entity_type="group",
                access_status="private",
                checked_at=utc_now(),
            )
        except (errors.UsernameInvalidError, errors.UsernameNotOccupiedError, ValueError):
            return DiscoveredCandidate(
                url=url,
                username=username,
                provider=self.name,
                access_status="unavailable",
                checked_at=utc_now(),
            )

    async def scan_activity(
        self,
        url: str,
        username: str | None,
        period_days: int,
        active_min_messages: int,
        max_messages: int,
    ) -> ActivityMetrics:
        scanned_at = utc_now()
        if username is None:
            return ActivityMetrics(
                status="unavailable",
                period_days=period_days,
                scanned_at=scanned_at,
                unavailable_reason="private link has no public username",
            )

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=period_days)
        count = 0
        authors: set[int] = set()
        last_message_at: str | None = None
        last_message_date: datetime | None = None
        hit_limit = False
        try:
            entity = await self.client.get_entity(username)
            async for message in self.client.iter_messages(entity, limit=max_messages):
                message_date = message.date
                if message_date.tzinfo is None:
                    message_date = message_date.replace(tzinfo=UTC)
                else:
                    message_date = message_date.astimezone(UTC)
                if last_message_date is None:
                    last_message_date = message_date
                    last_message_at = message_date.isoformat(timespec="seconds")
                if message_date < cutoff:
                    break
                count += 1
                if message.sender_id is not None:
                    authors.add(int(message.sender_id))
                if count >= max_messages:
                    hit_limit = True
                    break
        except errors.FloodWaitError:
            raise
        except (errors.ChannelPrivateError, errors.ChatAdminRequiredError, ValueError) as error:
            return ActivityMetrics(
                status="unavailable",
                period_days=period_days,
                scanned_at=scanned_at,
                unavailable_reason=type(error).__name__,
            )

        if count >= active_min_messages:
            status = "active"
        elif count > 0:
            status = "low_activity"
        else:
            status = "inactive"
        days_since = None
        if last_message_date is not None:
            days_since = round(max(0.0, (now - last_message_date).total_seconds() / 86400), 2)
        return ActivityMetrics(
            status=status,
            period_days=period_days,
            messages_count=count,
            unique_authors=len(authors),
            messages_per_day=round(count / period_days, 2),
            last_message_at=last_message_at,
            days_since_last_message=days_since,
            scanned_at=scanned_at,
            unavailable_reason="message limit reached; counts are lower bounds" if hit_limit else None,
        )

    def _from_entity(self, entity: object, query: str | None) -> DiscoveredCandidate | None:
        if not isinstance(entity, (types.Channel, types.Chat)):
            return None

        username = getattr(entity, "username", None)
        if not username:
            return None
        normalized = normalize_telegram_link(f"https://t.me/{username}")
        if normalized is None:
            return None

        if isinstance(entity, types.Channel):
            entity_type = "channel" if entity.broadcast and not entity.megagroup else "group"
            if entity_type == "channel":
                access = "channel"
            else:
                access = "approval_required" if getattr(entity, "join_request", False) else "open"
        else:
            entity_type = "group"
            access = "open"

        return DiscoveredCandidate(
            url=normalized.url,
            username=normalized.username,
            provider=self.name,
            telegram_id=getattr(entity, "id", None),
            source_query=query,
            title=getattr(entity, "title", None),
            entity_type=entity_type,
            access_status=access,
            members_count=getattr(entity, "participants_count", None),
            checked_at=utc_now(),
        )
