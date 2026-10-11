"""Gold layer: business-ready enrichment of each article, plus daily statistics.

The enrichment is a simple keyword baseline (lists of words and names). The NLP phase
will replace it with real entity recognition, and this baseline is what we measure it against.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone

from .silver import silver_key
from .storage import Storage, get_json, put_json

log = logging.getLogger(__name__)

TOPIC_KEYWORDS = {
    "transfer": ["transfer", "signing", "signed", "deal", "loan", "fee", "bid", "move", "join", "sell", "buy"],
    "injury": ["injury", "injured", "ruled out", "fitness", "hamstring", "knee", "muscle", "surgery"],
    "title_race": ["title", "champion", "points", "lead", "table", "season", "trophy"],
}

CLUBS = [
    "Arsenal", "Manchester City", "Liverpool", "Chelsea", "Manchester United", "Tottenham", "Newcastle",
    "Aston Villa", "PSG", "Bayern", "Barcelona", "Real Madrid", "Atletico", "Juventus", "Inter", "Napoli",
]

PLAYERS = [
    "Salah", "Saka", "Haaland", "Mbappe", "Mbappé", "Ronaldo", "Messi", "Arteta", "Guardiola", "Slot",
    "Odegaard", "Fernandes", "Yamal", "De Bruyne", "Palmer", "Rice", "Kane", "Bellingham",
]

# Different spellings of the same person
SAME_ENTITY = {"Mbappé": "Mbappe"}


def _pattern(words: list[str], case_sensitive: bool) -> re.Pattern:
    """One regex matching any of the words, but only as whole words."""
    longest_first = sorted(words, key=len, reverse=True)  # "Manchester United" before "Manchester"
    alternatives = "|".join(re.escape(w) for w in longest_first)
    flags = 0 if case_sensitive else re.IGNORECASE
    # (?<!\w) and (?!\w): no letter or digit right before or after the match
    return re.compile(rf"(?<!\w)({alternatives})(?!\w)", flags)


# Topic words are ordinary words: ignore case ("Transfer", "transfer")
TOPIC_PATTERNS = {topic: _pattern(words, case_sensitive=False) for topic, words in TOPIC_KEYWORDS.items()}
# Names are proper nouns: match case, so "Rice" the player is not "rice" the food
CLUB_PATTERN = _pattern(CLUBS, case_sensitive=True)
PLAYER_PATTERN = _pattern(PLAYERS, case_sensitive=True)


def _text(article: dict) -> str:
    return f"{article.get('title', '')} {article.get('content', '')}"


def find_topics(article: dict) -> list[str]:
    text = _text(article)
    topics = [topic for topic, pattern in TOPIC_PATTERNS.items() if pattern.search(text)]
    return topics or ["general"]


def find_entities(pattern: re.Pattern, article: dict) -> list[str]:
    found = {SAME_ENTITY.get(name, name) for name in pattern.findall(_text(article))}
    return sorted(found)


def enrich(article: dict) -> dict:
    """Add topics, clubs and players to one silver article."""
    return {
        **article,
        "topics": find_topics(article),
        "clubs": find_entities(CLUB_PATTERN, article),
        "players": find_entities(PLAYER_PATTERN, article),
        "enrichment_method": "keyword_baseline_v1",
    }


def build_summary(enriched: list[dict], ingest_date: str) -> dict:
    """Daily statistics over the enriched articles."""
    topics, clubs, players, hours = Counter(), Counter(), Counter(), Counter()
    for a in enriched:
        topics.update(a["topics"])
        clubs.update(a["clubs"])
        players.update(a["players"])
        if a.get("published_at"):
            hours[a["published_at"][11:13]] += 1  # "2026-10-11T14:05:00Z" -> "14"
    return {
        "ingest_date": ingest_date,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_articles": len(enriched),
        "articles_per_source": dict(Counter(a["source"] for a in enriched)),
        "topics": dict(topics.most_common()),
        "top_clubs": dict(clubs.most_common(10)),
        "top_players": dict(players.most_common(10)),
        "articles_per_hour_utc": dict(sorted(hours.items())),
    }


def gold_articles_key(ingest_date: str) -> str:
    return f"gold/date={ingest_date}/articles_enriched.json"


def gold_summary_key(ingest_date: str) -> str:
    return f"gold/date={ingest_date}/summary.json"


def run_gold(storage: Storage, ingest_date: str) -> dict:
    """Read silver, enrich every article, write enriched articles + daily summary."""
    articles = get_json(storage, silver_key(ingest_date))
    enriched = [enrich(a) for a in articles]
    summary = build_summary(enriched, ingest_date)
    put_json(storage, gold_articles_key(ingest_date), enriched)
    put_json(storage, gold_summary_key(ingest_date), summary)
    log.info("Gold %s: %d articles enriched", ingest_date, len(enriched))
    return summary
