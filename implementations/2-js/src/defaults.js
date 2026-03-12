import { basename, extname } from "node:path";

function slugify(text) {
  return text
    .replace(/[\._]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleCase(text) {
  const minor = new Set([
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
    "by", "with", "from", "but", "nor", "so", "yet",
  ]);
  return text
    .split(" ")
    .map((w, i, arr) => {
      if (i === 0 || i === arr.length - 1) {
        return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
      }
      if (minor.has(w.toLowerCase())) return w.toLowerCase();
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    })
    .join(" ");
}

export function defaultsFromFilename(sourcePath, root, inputPath) {
  const filename = basename(sourcePath);
  const ext = extname(filename);
  const stem = filename.slice(0, -ext.length || undefined);
  const defaults = {};

  // Derive relative path from input for directory-based hints
  let relPath = "";
  if (inputPath && sourcePath.startsWith(inputPath)) {
    relPath = sourcePath.slice(inputPath.length).replace(/^\//, "");
  }
  const relParts = relPath.split("/").slice(0, -1);

  switch (root) {
    case "memory": {
      if (relParts.length > 0) {
        defaults.event = titleCase(relParts.join(":"));
      }
      break;
    }
    case "music": {
      if (relParts.length >= 2) {
        defaults.artist = titleCase(relParts[0]);
        defaults.album = titleCase(relParts[1]);
      } else if (relParts.length === 1) {
        defaults.artist = titleCase(relParts[0]);
      }
      const trackMatch = stem.match(/^(\d{1,3})\s*[-.\s]\s*(.+)/);
      if (trackMatch) {
        defaults.track = trackMatch[1].padStart(2, "0");
        defaults.name = titleCase(slugify(trackMatch[2]));
      } else {
        defaults.name = titleCase(slugify(stem));
      }
      break;
    }
    case "movie":
    case "comedy": {
      const yearMatch = stem.match(/[\(\[]?((?:19|20)\d{2})[\)\]]?/);
      if (yearMatch) {
        defaults.year = yearMatch[1];
        const title = stem.slice(0, yearMatch.index).trim();
        defaults.name = titleCase(slugify(title)) || titleCase(slugify(stem));
      } else {
        defaults.name = titleCase(slugify(stem));
      }
      break;
    }
    case "tv": {
      const seMatch = stem.match(/(.+?)[.\s-]*[Ss](\d{1,2})[Ee](\d{1,2})/);
      if (seMatch) {
        defaults.show = titleCase(slugify(seMatch[1]));
        defaults.season = String(parseInt(seMatch[2])).padStart(2, "0");
        defaults.episode = String(parseInt(seMatch[3])).padStart(2, "0");
        const rest = stem.slice(seMatch.index + seMatch[0].length);
        const nameClean = slugify(rest.replace(/^[\s.\-]+/, ""));
        if (nameClean) defaults.name = titleCase(nameClean);
      } else if (relParts.length >= 1) {
        defaults.show = titleCase(relParts[0]);
      }
      break;
    }
    case "podcast": {
      if (relParts.length >= 1) {
        defaults.show = titleCase(relParts[0]);
      }
      defaults.name = titleCase(slugify(stem));
      break;
    }
    case "book": {
      if (relParts.length >= 1) {
        defaults.author = titleCase(relParts[0]);
      }
      defaults.name = titleCase(slugify(stem));
      break;
    }
  }

  return defaults;
}

export async function extractAudioMetadata(filePath) {
  try {
    const { parseFile } = await import("music-metadata");
    const metadata = await parseFile(filePath);
    const c = metadata.common;
    const result = {};
    if (c.title) result.name = c.title;
    if (c.artist) result.artist = c.artist;
    if (c.album) result.album = c.album;
    if (c.year) result.year = String(c.year);
    if (c.track?.no) result.track = String(c.track.no).padStart(2, "0");
    if (c.date) result.date = c.date;
    return result;
  } catch {
    return {};
  }
}

export async function defaultsFromSource(sourcePath, root, inputPath) {
  const filenameDefs = defaultsFromFilename(sourcePath, root, inputPath);
  const ext = extname(sourcePath).toLowerCase();
  const audioExts = new Set([".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".wma", ".opus", ".aiff"]);

  let metadataDefs = {};
  if (audioExts.has(ext)) {
    metadataDefs = await extractAudioMetadata(sourcePath);
  }

  return { filenameDefs, metadataDefs, merged: { ...filenameDefs, ...metadataDefs } };
}
