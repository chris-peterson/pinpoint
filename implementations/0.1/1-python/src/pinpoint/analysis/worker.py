"""Background analysis worker — processes pending files through AI pipelines.

Runs as an asyncio task after discovery. Processes files that haven't been
analyzed yet, storing results as suggestions in the database.

Pipeline routing by root + file_class:
  - movies/tv/comedy → filename parsing + TMDb lookup
  - memories (image) → Ollama vision LLM
  - music/books/podcasts → embedded metadata (already handled by defaults.py at discovery time)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiosqlite
import httpx

from pinpoint.analysis.suggestions import store_suggestions
from pinpoint.analysis.tmdb import analyze_comedy, analyze_movie, analyze_tv, parse_media_filename
from pinpoint.analysis.vision import analyze_image, check_ollama
from pinpoint.config import AnalysisConfig
from pinpoint.defaults import extract_audio_metadata, slugify

logger = logging.getLogger(__name__)


async def run_analysis(
    db: aiosqlite.Connection,
    config: AnalysisConfig,
) -> None:
    """Main analysis loop. Processes un-analyzed pending files continuously.

    Runs until cancelled. Picks up new files as they're discovered.
    """
    logger.info("Analysis worker starting")

    async with httpx.AsyncClient() as client:
        # Check which services are available
        has_tmdb = bool(config.tmdb_api_key)
        has_ollama = await check_ollama(client, config.ollama_url)

        if has_tmdb:
            logger.info("TMDb API available — movie/TV/comedy lookups enabled")
        else:
            logger.info("No TMDb API key — movie/TV/comedy lookups disabled")

        if has_ollama:
            logger.info("Ollama available at %s — vision analysis enabled", config.ollama_url)
        else:
            logger.info("Ollama not available — vision analysis disabled")

        if not has_tmdb and not has_ollama:
            logger.info("No analysis services available, running metadata-only analysis")

        while True:
            count = await _process_batch(db, client, config, has_tmdb, has_ollama)
            if count == 0:
                # No work to do — sleep before checking again
                await asyncio.sleep(3)
            else:
                logger.info("Analyzed %d files", count)
                # Brief yield to let other tasks run
                await asyncio.sleep(0.1)


async def _process_batch(
    db: aiosqlite.Connection,
    client: httpx.AsyncClient,
    config: AnalysisConfig,
    has_tmdb: bool,
    has_ollama: bool,
    batch_size: int = 10,
) -> int:
    """Process a batch of un-analyzed files. Returns count processed."""
    cursor = await db.execute(
        """SELECT id, source_path, root, file_class
           FROM files
           WHERE status = 'pending' AND analysis_status IS NULL
           ORDER BY discovery_date DESC
           LIMIT ?""",
        (batch_size,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return 0

    count = 0
    for row in rows:
        file_id, source_path, root, file_class = row
        try:
            await _analyze_file(
                db, client, config, file_id, source_path, root, file_class,
                has_tmdb, has_ollama,
            )
            count += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Analysis failed for file %d (%s)", file_id, source_path)
            await db.execute(
                "UPDATE files SET analysis_status = 'failed' WHERE id = ?",
                (file_id,),
            )
            await db.commit()

    return count


async def _analyze_file(
    db: aiosqlite.Connection,
    client: httpx.AsyncClient,
    config: AnalysisConfig,
    file_id: int,
    source_path: str,
    root: str,
    file_class: str,
    has_tmdb: bool,
    has_ollama: bool,
) -> None:
    """Run the appropriate analysis pipeline for a single file."""
    # Mark as analyzing
    await db.execute(
        "UPDATE files SET analysis_status = 'analyzing' WHERE id = ?",
        (file_id,),
    )
    await db.commit()

    suggestions: list[dict] = []
    path = Path(source_path)

    if not path.exists():
        await db.execute(
            "UPDATE files SET analysis_status = 'done' WHERE id = ?",
            (file_id,),
        )
        await db.commit()
        return

    # --- Pipeline 1: TMDb lookup for movies/TV/comedy ---
    if root in ("movies", "tv", "comedy") and has_tmdb:
        filename = path.name
        if root == "movies":
            tmdb_results = await analyze_movie(client, config.tmdb_api_key, filename)
        elif root == "tv":
            tmdb_results = await analyze_tv(client, config.tmdb_api_key, filename)
        else:  # comedy
            tmdb_results = await analyze_comedy(client, config.tmdb_api_key, filename)
        suggestions.extend(tmdb_results)

    # --- Pipeline 2: Metadata extraction for audio (supplements defaults.py) ---
    if file_class == "audio" and root in ("music", "books", "podcasts", "comedy"):
        audio_suggestions = _audio_metadata_suggestions(source_path, root)
        suggestions.extend(audio_suggestions)

    # --- Pipeline 3: Vision LLM for images in memories ---
    if root == "memories" and file_class == "image" and has_ollama:
        vision_results = await analyze_image(
            client, config.ollama_url, config.ollama_model, path,
        )
        suggestions.extend(vision_results)

    # --- Pipeline 4: Filename parsing for movies/TV (even without TMDb) ---
    if root in ("movies", "tv", "comedy") and not has_tmdb:
        filename_suggestions = _filename_suggestions(path.name, root)
        suggestions.extend(filename_suggestions)

    # Store suggestions
    if suggestions:
        stored = await store_suggestions(db, file_id, suggestions)
        logger.debug("Stored %d suggestions for file %d", stored, file_id)

    # Mark as done
    await db.execute(
        "UPDATE files SET analysis_status = 'done' WHERE id = ?",
        (file_id,),
    )
    await db.commit()


def _audio_metadata_suggestions(source_path: str, root: str) -> list[dict]:
    """Generate suggestions from embedded audio metadata.

    These supplement the defaults.py extraction by storing results as formal
    suggestions with confidence scores.
    """
    raw = extract_audio_metadata(source_path)
    if not raw:
        return []

    suggestions: list[dict] = []
    confidence = 0.9  # Embedded metadata is high confidence

    # Map audio fields to root-specific tag kinds
    if root == "music":
        field_map = {"artist": "artist", "album": "album", "name": "name",
                     "year": "year", "track": "track"}
    elif root == "books":
        field_map = {"artist": "author", "album": "name", "name": "name"}
    elif root == "podcasts":
        field_map = {"artist": "show", "name": "name"}
    elif root == "comedy":
        field_map = {"artist": "artist", "name": "name"}
    else:
        return []

    for src_field, dst_kind in field_map.items():
        value = raw.get(src_field)
        if value:
            suggestions.append({
                "kind": dst_kind,
                "value": value,
                "confidence": confidence,
            })

    return suggestions


def _filename_suggestions(filename: str, root: str) -> list[dict]:
    """Generate suggestions from filename parsing alone (no API).

    Used as fallback when TMDb is not available.
    """

    parsed = parse_media_filename(filename)
    suggestions: list[dict] = []
    confidence = 0.5  # Filename parsing is lower confidence

    title = parsed.get("title")
    if title:
        title = slugify(title)
        if root == "tv":
            suggestions.append({"kind": "show", "value": title, "confidence": confidence})
        else:
            suggestions.append({"kind": "name", "value": title, "confidence": confidence})

    year = parsed.get("year")
    if year:
        suggestions.append({"kind": "year", "value": year, "confidence": 0.8})

    season = parsed.get("season")
    if season:
        suggestions.append({"kind": "season", "value": season, "confidence": 0.8})

    episode = parsed.get("episode")
    if episode:
        suggestions.append({"kind": "episode", "value": episode, "confidence": 0.8})

    return suggestions
