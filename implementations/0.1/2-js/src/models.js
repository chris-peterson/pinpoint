export const ROOTS = ["memory", "music", "movie", "tv", "podcast", "book", "comedy"];

export const ROOT_FIELDS = {
  memory: [
    ["event", "Event"],
    ["name", "Name"],
    ["person", "Person"],
  ],
  music: [
    ["artist", "Artist"],
    ["album", "Album"],
    ["year", "Year"],
    ["track", "Track"],
    ["name", "Name"],
  ],
  movie: [
    ["series", "Series"],
    ["name", "Title"],
    ["year", "Year"],
  ],
  tv: [
    ["show", "Show"],
    ["season", "Season"],
    ["episode", "Episode"],
    ["name", "Name"],
  ],
  podcast: [
    ["show", "Show"],
    ["episode", "Episode"],
    ["name", "Name"],
  ],
  book: [
    ["author", "Author"],
    ["series", "Series"],
    ["name", "Title"],
  ],
  comedy: [
    ["artist", "Artist"],
    ["name", "Title"],
    ["year", "Year"],
  ],
};

export const ALL_TAG_FIELDS = new Set(
  Object.values(ROOT_FIELDS).flatMap((fields) => fields.map(([id]) => id)),
);

export const MULTI_VALUE_FIELDS = new Set(["person"]);

export const EXPECTED_TAGS = {
  memory: ["event", "name"],
  music: ["artist", "album", "name"],
  movie: ["name"],
  tv: ["show", "season", "episode", "name"],
  podcast: ["show", "episode", "name"],
  book: ["author", "name"],
  comedy: ["artist", "name"],
};

export const DERIVED_ATTRIBUTES = new Set(["year", "month", "class"]);

export const ACTION_VERBS = [
  "discover", "accept", "reject", "delete",
  "tag_add", "tag_remove", "favorite", "unfavorite",
  "relocate", "rename", "move", "missing",
  "stack_create", "stack_reorder", "stack_dissolve",
  "suggestion_accept", "suggestion_dismiss",
];

const IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".svg"]);
const VIDEO_EXTS = new Set([".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"]);
const AUDIO_EXTS = new Set([".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".wma", ".opus", ".aiff"]);
const DOC_EXTS = new Set([".pdf", ".epub", ".mobi", ".djvu"]);

export function classifyFile(ext) {
  const e = ext.toLowerCase();
  if (IMAGE_EXTS.has(e)) return "image";
  if (VIDEO_EXTS.has(e)) return "video";
  if (AUDIO_EXTS.has(e)) return "audio";
  if (DOC_EXTS.has(e)) return "document";
  return null;
}

export const ROOT_DIRS = {
  memory: "memories",
  music: "music",
  movie: "movies",
  tv: "tv",
  podcast: "podcast",
  book: "books",
  comedy: "comedy",
};
