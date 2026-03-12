import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { classifyFile } from "./models.js";
import { logAction } from "./actions.js";

const HIDDEN_PREFIXES = [".", "_"];
const AUDIO_EXTS = new Set([".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".wma", ".opus", ".aiff"]);

export function hashFile(filePath) {
  const hash = createHash("sha256");
  const data = readFileSync(filePath);
  hash.update(data);
  return hash.digest("hex");
}

function isAudioDirectory(dirPath) {
  try {
    const entries = readdirSync(dirPath);
    return entries.some((e) => AUDIO_EXTS.has(extname(e).toLowerCase()));
  } catch {
    return false;
  }
}

function walkFiles(dirPath, root) {
  const results = [];

  function walk(dir) {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      if (HIDDEN_PREFIXES.some((p) => entry.name.startsWith(p))) continue;

      const fullPath = join(dir, entry.name);

      if (entry.isDirectory()) {
        walk(fullPath);
        continue;
      }

      if (!entry.isFile()) continue;

      const ext = extname(entry.name).toLowerCase();
      const fileClass = classifyFile(ext);
      if (!fileClass) continue;

      // [AI-3] Skip images in directories that contain audio files
      if (fileClass === "image" && isAudioDirectory(dirname(fullPath))) continue;

      results.push({ path: fullPath, fileClass, ext });
    }
  }

  walk(dirPath);
  return results;
}

export function scanInput(db, inputPath, root) {
  const files = walkFiles(inputPath, root);
  let discovered = 0;
  let duplicates = 0;

  const insertFile = db.prepare(`
    INSERT OR IGNORE INTO files (source_path, root, file_class, content_hash, creation_date)
    VALUES (?, ?, ?, ?, ?)
  `);

  const checkHash = db.prepare(
    "SELECT id FROM files WHERE content_hash = ?",
  );

  const checkPath = db.prepare(
    "SELECT id FROM files WHERE source_path = ?",
  );

  for (const file of files) {
    if (checkPath.get(file.path)) continue;

    let contentHash;
    let creationDate;
    try {
      contentHash = hashFile(file.path);
      const stat = statSync(file.path);
      creationDate = (stat.birthtime || stat.mtime).toISOString().slice(0, 19);
    } catch {
      continue;
    }

    // [DS-1] Exact duplicates never enter the queue
    if (checkHash.get(contentHash)) {
      duplicates++;
      continue;
    }

    const result = insertFile.run(
      file.path, root, file.fileClass, contentHash, creationDate,
    );

    if (result.changes > 0) {
      logAction(db, "discover", result.lastInsertRowid, {
        source_path: file.path,
        content_hash: contentHash,
      });
      discovered++;
    }
  }

  return { discovered, duplicates, total: files.length };
}

export function runDiscovery(db, config) {
  let totalDiscovered = 0;
  let totalDuplicates = 0;

  for (const input of config.inputs) {
    try {
      const result = scanInput(db, input.path, input.root);
      totalDiscovered += result.discovered;
      totalDuplicates += result.duplicates;
      if (result.discovered > 0) {
        console.log(
          `[discovery] ${input.path}: ${result.discovered} new, ${result.duplicates} dups, ${result.total} total`,
        );
      }
    } catch (e) {
      console.error(`[discovery] error scanning ${input.path}:`, e.message);
    }
  }

  return { discovered: totalDiscovered, duplicates: totalDuplicates };
}
