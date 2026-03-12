"""TMDb API lookup for movies, TV shows, and comedy specials.

Uses the free TMDb API (https://www.themoviedb.org/) to fetch canonical
metadata from filename-parsed title + year. Degrades gracefully when
no API key is configured.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"


def parse_media_filename(filename: str) -> dict[str, str]:
    """Extract title, year, season, episode from common media filename patterns.

    Handles: "The.Office.S03E05.720p.mkv", "There Will Be Blood (2007).mp4",
    "John.Mulaney.Kid.Gorgeous.2018.WEBRip.mp4", etc.
    """
    stem = Path(filename).stem
    result: dict[str, str] = {}

    # Try S01E02 pattern first (TV)
    se_match = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", stem)
    if se_match:
        result["season"] = str(int(se_match.group(1)))
        result["episode"] = str(int(se_match.group(2)))
        # Title is everything before the SxxExx
        title_part = stem[: se_match.start()].strip(" .-_")
        title_part = re.sub(r"[\.\-_]+", " ", title_part).strip()
        if title_part:
            result["title"] = title_part
        return result

    # Try year in parens or standalone: "Title (2007)" or "Title.2018.WEBRip"
    year_match = re.search(r"[\(\[]?((?:19|20)\d{2})[\)\]]?", stem)
    if year_match:
        result["year"] = year_match.group(1)
        title_part = stem[: year_match.start()].strip(" .-_")
        title_part = re.sub(r"[\.\-_]+", " ", title_part).strip()
        if title_part:
            result["title"] = title_part
        return result

    # No pattern matched — use cleaned stem as title
    title = re.sub(r"[\.\-_]+", " ", stem).strip()
    # Remove common quality/codec tags
    title = re.sub(
        r"\b(720p|1080p|2160p|4k|bluray|brrip|webrip|web[\s\-]?dl|hdtv|dvdrip|x264|x265|hevc|aac|ac3)\b",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    if title:
        result["title"] = title

    return result


async def search_movie(
    client: httpx.AsyncClient, api_key: str, title: str, year: str = "",
) -> list[dict]:
    """Search TMDb for a movie by title and optional year."""
    params: dict[str, str] = {"api_key": api_key, "query": title}
    if year:
        params["year"] = year
    try:
        resp = await client.get(f"{TMDB_BASE}/search/movie", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        logger.debug("TMDb movie search failed for %r", title, exc_info=True)
        return []


async def get_movie_details(
    client: httpx.AsyncClient, api_key: str, movie_id: int,
) -> dict | None:
    """Get movie details including collection (series/franchise) info."""
    try:
        resp = await client.get(
            f"{TMDB_BASE}/movie/{movie_id}",
            params={"api_key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.debug("TMDb movie details failed for %d", movie_id, exc_info=True)
        return None


async def search_tv(
    client: httpx.AsyncClient, api_key: str, title: str,
) -> list[dict]:
    """Search TMDb for a TV show by title."""
    try:
        resp = await client.get(
            f"{TMDB_BASE}/search/tv",
            params={"api_key": api_key, "query": title},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        logger.debug("TMDb TV search failed for %r", title, exc_info=True)
        return []


async def get_tv_episode(
    client: httpx.AsyncClient, api_key: str,
    show_id: int, season: int, episode: int,
) -> dict | None:
    """Get TV episode details (name, overview)."""
    try:
        resp = await client.get(
            f"{TMDB_BASE}/tv/{show_id}/season/{season}/episode/{episode}",
            params={"api_key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.debug("TMDb episode lookup failed for show=%d S%dE%d", show_id, season, episode)
        return None


async def analyze_movie(
    client: httpx.AsyncClient, api_key: str, filename: str,
) -> list[dict]:
    """Analyze a movie file and return tag suggestions.

    Returns list of {kind, value, confidence} dicts.
    """
    parsed = parse_media_filename(filename)
    title = parsed.get("title")
    if not title:
        return []

    results = await search_movie(client, api_key, title, parsed.get("year", ""))
    if not results:
        return []

    best = results[0]
    suggestions: list[dict] = []
    confidence = 0.85 if len(results) == 1 else 0.7

    # Canonical title
    tmdb_title = best.get("title", "")
    if tmdb_title:
        suggestions.append({"kind": "name", "value": tmdb_title, "confidence": confidence})

    # Year from release date
    release_date = best.get("release_date", "")
    if release_date:
        suggestions.append({"kind": "year", "value": release_date[:4], "confidence": confidence})

    # Check for collection (franchise/series)
    details = await get_movie_details(client, api_key, best["id"])
    if details and details.get("belongs_to_collection"):
        collection_name = details["belongs_to_collection"]["name"]
        # Strip " Collection" suffix for cleaner series names
        series_name = re.sub(r"\s+Collection$", "", collection_name, flags=re.IGNORECASE)
        suggestions.append({"kind": "series", "value": series_name, "confidence": confidence})

    return suggestions


async def analyze_tv(
    client: httpx.AsyncClient, api_key: str, filename: str,
) -> list[dict]:
    """Analyze a TV file and return tag suggestions."""
    parsed = parse_media_filename(filename)
    title = parsed.get("title")
    if not title:
        return []

    results = await search_tv(client, api_key, title)
    if not results:
        return []

    best = results[0]
    suggestions: list[dict] = []
    confidence = 0.85 if len(results) == 1 else 0.7

    show_name = best.get("name", "")
    if show_name:
        suggestions.append({"kind": "show", "value": show_name, "confidence": confidence})

    # If we have season/episode, fetch episode details
    season_str = parsed.get("season")
    episode_str = parsed.get("episode")
    if season_str:
        suggestions.append({"kind": "season", "value": season_str, "confidence": 0.9})
    if episode_str:
        suggestions.append({"kind": "episode", "value": episode_str, "confidence": 0.9})

    if season_str and episode_str:
        ep_data = await get_tv_episode(
            client, api_key, best["id"], int(season_str), int(episode_str),
        )
        if ep_data and ep_data.get("name"):
            suggestions.append({
                "kind": "name",
                "value": ep_data["name"],
                "confidence": confidence,
            })

    return suggestions


async def analyze_comedy(
    client: httpx.AsyncClient, api_key: str, filename: str,
) -> list[dict]:
    """Analyze a comedy special file. Uses movie search (specials are listed as movies on TMDb)."""
    parsed = parse_media_filename(filename)
    title = parsed.get("title")
    if not title:
        return []

    # Comedy specials are typically listed as movies on TMDb
    results = await search_movie(client, api_key, title, parsed.get("year", ""))
    if not results:
        return []

    best = results[0]
    suggestions: list[dict] = []
    confidence = 0.65  # Lower confidence — comedy specials are harder to match

    tmdb_title = best.get("title", "")
    if tmdb_title:
        suggestions.append({"kind": "name", "value": tmdb_title, "confidence": confidence})

    release_date = best.get("release_date", "")
    if release_date:
        suggestions.append({"kind": "year", "value": release_date[:4], "confidence": confidence})

    return suggestions
