"""Append-only action log."""

from __future__ import annotations

import json

import aiosqlite

from pinpoint.models import ActionVerb


async def log_action(
    db: aiosqlite.Connection,
    verb: ActionVerb,
    file_id: int | None = None,
    detail: dict | None = None,
) -> int:
    """Log a state-changing operation to the actions table."""
    detail_json = json.dumps(detail) if detail else None
    cursor = await db.execute(
        "INSERT INTO actions (verb, file_id, detail) VALUES (?, ?, ?)",
        (verb.value, file_id, detail_json),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]
