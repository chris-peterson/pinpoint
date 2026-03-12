import { extname } from "node:path";
import { ROOT_DIRS } from "./models.js";

function firstOr(tags, key, fallback = "_unknown") {
  const vals = tags[key];
  if (!vals || vals.length === 0) return fallback;
  return vals[0];
}

function has(tags, key) {
  const vals = tags[key];
  return vals && vals.length > 0 && vals[0] !== "";
}

function pad2(n) {
  const s = String(n).replace(/^0+/, "");
  return s.padStart(2, "0");
}

function yearFromDate(tags) {
  if (has(tags, "year")) return firstOr(tags, "year");
  const d = firstOr(tags, "date", "");
  if (d && d.length >= 4) return d.slice(0, 4);
  return "";
}

function monthFromDate(tags) {
  const d = firstOr(tags, "date", "");
  if (d && d.length >= 7) return d.slice(0, 7);
  return d ? d.slice(0, 4) + "-01" : "";
}

export function derivePath(root, tags, originalFilename) {
  const ext = extname(originalFilename);
  const stem = originalFilename.slice(0, -ext.length || undefined);
  const rootDir = ROOT_DIRS[root] || root;

  const name = has(tags, "name") ? firstOr(tags, "name") : stem;

  switch (root) {
    case "memory": {
      const month = monthFromDate(tags) || "_unknown";
      const event = firstOr(tags, "event", "");
      const eventSegments = event ? event.split(":").map((s) => s.trim()) : [];
      const parts = [rootDir, month, ...eventSegments];
      const filename = name + ext;
      return [...parts, filename].join("/");
    }

    case "music": {
      const artist = firstOr(tags, "artist");
      const album = firstOr(tags, "album", "");
      const track = firstOr(tags, "track", "");
      const year = yearFromDate(tags);

      const parts = [rootDir, artist];

      if (album) {
        const albumDir = year ? `[${year}] ${album}` : album;
        parts.push(albumDir);
      }

      let filename;
      if (track) {
        filename = `${pad2(track)} - ${name}${ext}`;
      } else {
        filename = `${name}${ext}`;
      }
      parts.push(filename);
      return parts.join("/");
    }

    case "movie": {
      const series = firstOr(tags, "series", "");
      const year = yearFromDate(tags);
      const parts = [rootDir];
      if (series) {
        series.split(":").forEach((s) => parts.push(s.trim()));
      }
      const filename = year ? `${name} [${year}]${ext}` : `${name}${ext}`;
      parts.push(filename);
      return parts.join("/");
    }

    case "tv": {
      const show = firstOr(tags, "show");
      const season = firstOr(tags, "season", "");
      const episode = firstOr(tags, "episode", "");
      const parts = [rootDir, show];
      if (season) parts.push(`Season ${pad2(season)}`);
      let filename;
      if (episode) {
        filename = `${pad2(episode)} - ${name}${ext}`;
      } else {
        filename = `${name}${ext}`;
      }
      parts.push(filename);
      return parts.join("/");
    }

    case "podcast": {
      const show = firstOr(tags, "show");
      const episode = firstOr(tags, "episode", "");
      const parts = [rootDir, show];
      let filename;
      if (episode) {
        filename = `${pad2(episode)} - ${name}${ext}`;
      } else {
        filename = `${name}${ext}`;
      }
      parts.push(filename);
      return parts.join("/");
    }

    case "book": {
      const author = firstOr(tags, "author");
      const series = firstOr(tags, "series", "");
      const parts = [rootDir, author];
      if (series) {
        series.split(":").forEach((s) => parts.push(s.trim()));
      }
      parts.push(`${name}${ext}`);
      return parts.join("/");
    }

    case "comedy": {
      const artist = firstOr(tags, "artist");
      const year = yearFromDate(tags);
      const parts = [rootDir, artist];
      const filename = year ? `[${year}] ${name}${ext}` : `${name}${ext}`;
      parts.push(filename);
      return parts.join("/");
    }

    default:
      return `${rootDir}/${originalFilename}`;
  }
}

export function resolveCollision(fullPath, db) {
  const ext = extname(fullPath);
  const base = fullPath.slice(0, -ext.length);
  let candidate = fullPath;
  let suffix = 1;
  while (
    db
      .prepare("SELECT 1 FROM files WHERE managed_path = ? AND status = 'managed'")
      .get(candidate)
  ) {
    candidate = `${base}-${suffix}${ext}`;
    suffix++;
  }
  return candidate;
}
