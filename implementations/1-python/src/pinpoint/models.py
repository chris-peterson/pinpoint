"""Domain model dataclasses."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class FileStatus(enum.StrEnum):
    PENDING = "pending"
    MANAGED = "managed"
    MISSING = "missing"
    DRIFTED = "drifted"


class ActionVerb(enum.StrEnum):
    DISCOVER = "discover"
    ACCEPT = "accept"
    REJECT = "reject"
    DELETE = "delete"
    TAG_ADD = "tag_add"
    TAG_REMOVE = "tag_remove"
    FAVORITE = "favorite"
    UNFAVORITE = "unfavorite"
    RELOCATE = "relocate"
    RENAME = "rename"
    MOVE = "move"
    MISSING = "missing"
    STACK_CREATE = "stack_create"
    STACK_REORDER = "stack_reorder"
    STACK_DISSOLVE = "stack_dissolve"
    SUGGESTION_ACCEPT = "suggestion_accept"
    SUGGESTION_DISMISS = "suggestion_dismiss"


class SuggestionStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


@dataclass
class File:
    id: int
    source_path: str
    managed_path: str | None
    status: FileStatus
    root: str
    file_class: str
    content_hash: str
    perceptual_hash: str | None
    creation_date: datetime | None
    discovery_date: datetime
    managed_date: datetime | None
    favorite: bool
    stack_id: int | None
    analysis_status: str | None

    @classmethod
    def from_row(cls, row: dict) -> File:
        return cls(
            id=row["id"],
            source_path=row["source_path"],
            managed_path=row["managed_path"],
            status=FileStatus(row["status"]),
            root=row["root"],
            file_class=row["file_class"],
            content_hash=row["content_hash"],
            perceptual_hash=row["perceptual_hash"],
            creation_date=_parse_dt(row["creation_date"]),
            discovery_date=_parse_dt(row["discovery_date"]),  # type: ignore[arg-type]
            managed_date=_parse_dt(row["managed_date"]),
            favorite=bool(row["favorite"]),
            stack_id=row["stack_id"],
            analysis_status=row["analysis_status"],
        )


@dataclass
class Tag:
    id: int
    name: str
    type: str
    builtin: bool

    @classmethod
    def from_row(cls, row: dict) -> Tag:
        return cls(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            builtin=bool(row["builtin"]),
        )


@dataclass
class FileTag:
    file_id: int
    tag_id: int
    region: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict) -> FileTag:
        return cls(
            file_id=row["file_id"],
            tag_id=row["tag_id"],
            region=row["region"],
            created_at=_parse_dt(row["created_at"]),  # type: ignore[arg-type]
        )


@dataclass
class Action:
    id: int
    timestamp: datetime
    verb: ActionVerb
    file_id: int | None
    detail: str | None

    @classmethod
    def from_row(cls, row: dict) -> Action:
        return cls(
            id=row["id"],
            timestamp=_parse_dt(row["timestamp"]),  # type: ignore[arg-type]
            verb=ActionVerb(row["verb"]),
            file_id=row["file_id"],
            detail=row["detail"],
        )


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
