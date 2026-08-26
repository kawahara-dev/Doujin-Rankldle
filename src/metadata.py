"""Presentation and analytics helpers for raw product metadata."""
from __future__ import annotations

GENRE_ANALYTICS_EXCLUDE_IDS = frozenset({"156023", "156022", "156021"})
GENRE_ANALYTICS_EXCLUDE_NAMES = frozenset({"成人向け", "男性向け", "専売"})


def meaningful_genres(genres):
 """Return useful genre dictionaries without modifying the API-owned raw list."""
 if not isinstance(genres, list):
  return []
 return [genre for genre in genres if isinstance(genre, dict)
         and str(genre.get("name") or "").strip()
         and str(genre.get("id") or "") not in GENRE_ANALYTICS_EXCLUDE_IDS
         and str(genre.get("name") or "").strip() not in GENRE_ANALYTICS_EXCLUDE_NAMES]
