ROOTS = ["memory", "music", "movie", "tv", "podcast", "book", "comedy"]

ROOT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "memory": [("event", "Event"), ("person", "Person"), ("name", "Name")],
    "music": [
        ("artist", "Artist"),
        ("feat", "Featured"),
        ("album", "Album"),
        ("year", "Year"),
        ("track", "Track"),
        ("name", "Name"),
    ],
    "movie": [("series", "Series"), ("name", "Title"), ("year", "Year")],
    "tv": [
        ("show", "Show"),
        ("season", "Season"),
        ("episode", "Episode"),
        ("name", "Name"),
    ],
    "podcast": [("show", "Show"), ("episode", "Episode"), ("name", "Name")],
    "book": [("author", "Author"), ("series", "Series"), ("name", "Title")],
    "comedy": [("artist", "Artist"), ("name", "Title"), ("year", "Year")],
}

ALL_TAG_FIELDS = {f for fields in ROOT_FIELDS.values() for f, _ in fields}

MULTI_VALUE_FIELDS = {"person", "feat"}

EXPECTED_TAGS: dict[str, list[str]] = {
    "memory": ["event", "name"],
    "music": ["artist", "album", "name"],
    "movie": ["name"],
    "tv": ["show", "season", "episode", "name"],
    "podcast": ["show", "episode", "name"],
    "book": ["author", "name"],
    "comedy": ["artist", "name"],
}

DERIVED_ATTRIBUTES = {"month", "class"}

ROOT_DIRS = {
    "memory": "memories",
    "music": "music",
    "movie": "movies",
    "tv": "tv",
    "podcast": "podcast",
    "book": "books",
    "comedy": "comedy",
}

TAG_SOURCES = ["metadata", "filename", "api", "ai", "manual"]

SOURCE_WEIGHTS = {
    "metadata": 0.9,
    "api": 0.85,
    "filename": 0.6,
    "directory": 0.5,
    "ai": 0.3,
    "manual": 1.0,
    "fallback": 0.1,
}

ACTION_VERBS = [
    "discover", "auto_import", "stuck", "delete", "tag_add", "tag_remove", "tag_edit",
    "favorite", "unfavorite", "relocate", "rename", "move", "missing",
    "stack_create", "stack_reorder", "stack_dissolve",
]

MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif", ".svg"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"},
    "audio": {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".aiff", ".alac"},
}


def classify_file(ext: str) -> str:
    ext = ext.lower()
    for cls, exts in MEDIA_EXTENSIONS.items():
        if ext in exts:
            return cls
    return "document"
