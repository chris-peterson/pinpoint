"""Suggestion storage and retrieval helpers."""

from __future__ import annotations

import aiosqlite


async def store_suggestions(
    db: aiosqlite.Connection,
    file_id: int,
    suggestions: list[dict],
) -> int:
    """Store analysis suggestions for a file.

    Each suggestion dict has: kind, value, confidence, region (optional).
    Returns the number of suggestions inserted.
    """
    count = 0
    for s in suggestions:
        # Skip if an identical suggestion already exists
        existing = await db.execute(
            "SELECT id FROM suggestions WHERE file_id = ? AND kind = ? AND value = ?",
            (file_id, s["kind"], s["value"]),
        )
        if await existing.fetchone():
            continue
        await db.execute(
            """INSERT INTO suggestions (file_id, kind, value, confidence, region)
               VALUES (?, ?, ?, ?, ?)""",
            (file_id, s["kind"], s["value"], s.get("confidence"), s.get("region")),
        )
        count += 1
    if count:
        await db.commit()
    return count


async def get_suggestions(
    db: aiosqlite.Connection,
    file_id: int,
    status: str = "pending",
) -> list[dict]:
    """Get suggestions for a file, ordered by confidence descending."""
    cursor = await db.execute(
        """SELECT id, kind, value, confidence, region, status
           FROM suggestions
           WHERE file_id = ? AND status = ?
           ORDER BY confidence DESC""",
        (file_id, status),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "kind": r[1],
            "value": r[2],
            "confidence": r[3],
            "region": r[4],
            "status": r[5],
        }
        for r in rows
    ]


async def suggestions_as_defaults(
    db: aiosqlite.Connection,
    file_id: int,
) -> dict[str, str]:
    """Get the highest-confidence pending suggestion for each kind as a defaults dict.

    Returns {kind: value} for the best suggestion per field.
    """
    suggestions = await get_suggestions(db, file_id, status="pending")
    defaults: dict[str, str] = {}
    for s in suggestions:
        kind = s["kind"]
        if kind not in defaults:  # first = highest confidence
            defaults[kind] = s["value"]
    return defaults
