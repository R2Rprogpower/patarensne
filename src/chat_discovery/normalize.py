from __future__ import annotations

import html
import re
from urllib.parse import unquote, urlsplit

from chat_discovery.models import NormalizedLink

TG_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?(?:\+[A-Za-z0-9_-]+|[A-Za-z][A-Za-z0-9_]{3,31})",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
PRIVATE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")
RESERVED = {
    "addemoji",
    "addlist",
    "addstickers",
    "boost",
    "c",
    "confirmphone",
    "contact",
    "invoice",
    "iv",
    "joinchat",
    "login",
    "proxy",
    "setlanguage",
    "share",
    "socks",
}


def normalize_telegram_link(value: str) -> NormalizedLink | None:
    raw = html.unescape(unquote(value.strip())).strip("<>()[]{}.,;:!\"'")
    if not raw:
        return None

    if raw.startswith("@"):
        raw = f"https://t.me/{raw[1:]}"
    elif not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in {"t.me", "telegram.me"}:
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return None
    if segments[0].lower() == "s" and len(segments) > 1:
        segments = segments[1:]

    first = segments[0]
    if first.startswith("+"):
        token = first[1:]
        if PRIVATE_TOKEN_RE.fullmatch(token):
            return NormalizedLink(url=f"https://t.me/+{token}", username=None, private_hint=True)
        return None

    if first.lower() == "joinchat" and len(segments) > 1 and PRIVATE_TOKEN_RE.fullmatch(segments[1]):
        return NormalizedLink(url=f"https://t.me/+{segments[1]}", username=None, private_hint=True)

    if first.lower() in RESERVED or not USERNAME_RE.fullmatch(first):
        return None

    username = first.lower()
    return NormalizedLink(url=f"https://t.me/{username}", username=username)


def extract_telegram_links(text: str) -> list[NormalizedLink]:
    found: list[NormalizedLink] = []
    seen: set[str] = set()
    for match in TG_LINK_RE.finditer(html.unescape(text)):
        normalized = normalize_telegram_link(match.group(0))
        if normalized and normalized.url not in seen:
            seen.add(normalized.url)
            found.append(normalized)
    return found
