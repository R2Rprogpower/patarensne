from chat_discovery.normalize import extract_telegram_links, normalize_telegram_link


def test_normalizes_public_link_and_message_path() -> None:
    assert normalize_telegram_link("https://t.me/KyivChat/123").url == "https://t.me/kyivchat"
    assert normalize_telegram_link("@KyivChat").username == "kyivchat"


def test_normalizes_private_invite_without_exposing_token_as_username() -> None:
    result = normalize_telegram_link("https://t.me/+AbCdEfGh123")
    assert result is not None
    assert result.private_hint is True
    assert result.username is None


def test_rejects_non_telegram_and_reserved_links() -> None:
    assert normalize_telegram_link("https://example.com/KyivChat") is None
    assert normalize_telegram_link("https://t.me/share/url?url=x") is None


def test_extracts_and_deduplicates_links() -> None:
    links = extract_telegram_links("See t.me/KyivChat and https://telegram.me/kyivchat plus t.me/ObolonChat")
    assert [item.url for item in links] == ["https://t.me/kyivchat", "https://t.me/obolonchat"]
