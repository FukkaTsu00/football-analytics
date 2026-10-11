"""Text helpers used by the silver layer."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

# Boilerplate sentences the sites insert into article text
NOISE_PHRASES = (
    "This video can not be played",
    "Add GOAL.com as a preferred source",
    "Send us your questions",
)


def clean_text(text: str | None) -> str:
    """Remove boilerplate and normalise whitespace."""
    if not text:
        return ""
    for phrase in NOISE_PHRASES:
        text = text.replace(phrase, "")
    text = text.replace("\xa0", " ")  # non-breaking spaces -> normal spaces
    text = re.sub(r"\s+", " ", text)  # many spaces / newlines -> one space
    text = re.sub(r"\s+([,.;:!?)])", r"\1", text)  # "word ." -> "word." (left by the spiders' " ".join)
    return text.strip()


def parse_published_at(raw: str | None) -> str | None:
    """Turn any ISO-8601 timestamp into UTC 'YYYY-MM-DDTHH:MM:SSZ', or None if it can't be parsed."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:  # no timezone given: assume UTC rather than guess
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def article_id(url: str) -> str:
    """Stable 16-character id for an article, derived from its URL without ?query or #fragment."""
    canonical = url.split("?")[0].split("#")[0].rstrip("/")
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]