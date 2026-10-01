from __future__ import annotations

import re


CAPTCHA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("captcha keyword", re.compile(r"\b(?:captcha|капч[аиу]?|капча)\b", re.IGNORECASE)),
    (
        "verification instruction",
        re.compile(
            r"\b(?:verify|verification|верификац|провер(?:к|ь)|перевір(?:к|ити)|антиспам)\w*\b",
            re.IGNORECASE,
        ),
    ),
    (
        "known verification bot",
        re.compile(r"@(?:shieldy_bot|grouphelpbot|combot|captcha_bot)\b", re.IGNORECASE),
    ),
)


def detect_captcha(*texts: str | None) -> tuple[str, str | None]:
    """Return only evidence-based detections; absence of a keyword is not proof of no captcha."""
    value = "\n".join(text for text in texts if text)
    for label, pattern in CAPTCHA_PATTERNS:
        match = pattern.search(value)
        if match:
            return "yes", f"{label}: {match.group(0)}"
    return "unknown", "not determinable from public metadata"
