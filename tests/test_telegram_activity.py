from datetime import UTC, datetime, timedelta

from chat_discovery.providers.telegram import TelegramProvider


class FakeMessage:
    def __init__(self, date: datetime, sender_id: int | None) -> None:
        self.date = date
        self.sender_id = sender_id


class FakeClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages

    async def get_entity(self, username: str) -> str:
        return username

    async def iter_messages(self, entity: str, limit: int):
        for message in self.messages[:limit]:
            yield message


async def test_activity_scanner_counts_recent_messages_and_authors() -> None:
    now = datetime.now(UTC)
    provider = TelegramProvider.__new__(TelegramProvider)
    provider.client = FakeClient(
        [
            FakeMessage(now - timedelta(hours=1), 1),
            FakeMessage(now - timedelta(hours=2), 2),
            FakeMessage(now - timedelta(days=8), 3),
        ]
    )

    metrics = await provider.scan_activity(
        "https://t.me/example", "example", period_days=7, active_min_messages=2, max_messages=100
    )

    assert metrics.status == "active"
    assert metrics.messages_count == 2
    assert metrics.unique_authors == 2
    assert metrics.messages_per_day == 0.29
