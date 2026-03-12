import { Router } from "express";
import { renameSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { derivePath, resolveCollision } from "../paths.js";
import { logAction } from "../actions.js";
import { defaultsFromSource } from "../defaults.js";
import { ALL_TAG_FIELDS, MULTI_VALUE_FIELDS, DERIVED_ATTRIBUTES } from "../models.js";

export function createQueueRouter(db, configHolder) {
  const router = Router();

  // Accept a single file [MQ accept]
  router.post("/api/files/:id/accept", async (req, res) => {
    const fileId = parseInt(req.params.id);
    const config = configHolder.config;

    const file = db
      .prepare("SELECT * FROM files WHERE id = ? AND status = 'pending'")
      .get(fileId);
    if (!file) return res.status(404).json({ error: "File not found or not pending" });

    const inputPath = config.inputs.find((inp) =>
      file.source_path.startsWith(inp.path),
    )?.path || "";

    const { filenameDefs, metadataDefs } = await defaultsFromSource(
      file.source_path, file.root, inputPath,
    );
    const fieldDefaults = { ...filenameDefs, ...metadataDefs };

    // Build tags from form data, falling back to defaults
    const tags = {};
    for (const field of ALL_TAG_FIELDS) {
      if (MULTI_VALUE_FIELDS.has(field)) {
        let values = [];
        if (req.body[field]) {
          values = Array.isArray(req.body[field])
            ? req.body[field].filter((v) => v.trim())
            : [req.body[field]].filter((v) => v.trim());
        }
        if (values.length === 0 && fieldDefaults[field]) {
          values = [fieldDefaults[field]];
        }
        if (values.length > 0) tags[field] = values;
      } else {
        let value = req.body[field]?.trim() || "";
        if (!value) value = fieldDefaults[field] || "";
        if (value) {
          tags[field] = [value];
          if (DERIVED_ATTRIBUTES.has(field)) continue;
        }
      }
    }

    // Persist tags
    const insertTag = db.prepare(
      "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)",
    );
    const getTag = db.prepare("SELECT id FROM tags WHERE name = ?");
    const linkTag = db.prepare(
      "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
    );

    for (const [field, values] of Object.entries(tags)) {
      if (DERIVED_ATTRIBUTES.has(field)) continue;
      for (const val of values) {
        const tagName = `${field}:${val}`;
        insertTag.run(tagName, field);
        const tagRow = getTag.get(tagName);
        if (tagRow) linkTag.run(fileId, tagRow.id);
      }
    }

    // Derive output path
    const originalFilename = basename(file.source_path);
    const relPath = derivePath(file.root, tags, originalFilename);
    const fullPath = join(config.output, relPath);
    const finalPath = resolveCollision(fullPath, db);

    // Move file
    mkdirSync(dirname(finalPath), { recursive: true });
    try {
      renameSync(file.source_path, finalPath);
    } catch (e) {
      return res.status(500).json({ error: `Move failed: ${e.message}` });
    }

    // Update DB
    db.prepare(
      "UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now') WHERE id = ?",
    ).run(finalPath, fileId);

    logAction(db, "accept", fileId, {
      source_path: file.source_path,
      destination_path: finalPath,
    });

    res.json({ ok: true, path: finalPath });
  });

  // Accept all files in a source folder [MQ-7]
  router.post("/api/folder/accept", async (req, res) => {
    const folderPath = req.body.folder;
    if (!folderPath) return res.status(400).json({ error: "folder is required" });

    const config = configHolder.config;
    const rows = db
      .prepare(
        "SELECT * FROM files WHERE source_path LIKE ? AND status = 'pending' AND skipped_at IS NULL",
      )
      .all(folderPath + "/%");

    if (rows.length === 0) {
      return res.json({ ok: true, accepted: 0 });
    }

    const insertTag = db.prepare(
      "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)",
    );
    const getTag = db.prepare("SELECT id FROM tags WHERE name = ?");
    const linkTag = db.prepare(
      "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
    );

    let accepted = 0;
    const errors = [];

    for (const file of rows) {
      const inputPath = config.inputs.find((inp) =>
        file.source_path.startsWith(inp.path),
      )?.path || "";

      const { filenameDefs, metadataDefs } = await defaultsFromSource(
        file.source_path, file.root, inputPath,
      );
      const fieldDefaults = { ...filenameDefs, ...metadataDefs };

      const tags = {};
      for (const field of ALL_TAG_FIELDS) {
        const value = fieldDefaults[field] || "";
        if (value) {
          tags[field] = [value];
          if (DERIVED_ATTRIBUTES.has(field)) continue;
          const tagName = `${field}:${value}`;
          insertTag.run(tagName, field);
          const tagRow = getTag.get(tagName);
          if (tagRow) linkTag.run(file.id, tagRow.id);
        }
      }

      const originalFilename = basename(file.source_path);
      const relPath = derivePath(file.root, tags, originalFilename);
      const fullPath = join(config.output, relPath);
      const finalPath = resolveCollision(fullPath, db);

      mkdirSync(dirname(finalPath), { recursive: true });
      try {
        renameSync(file.source_path, finalPath);
        db.prepare(
          "UPDATE files SET status = 'managed', managed_path = ?, managed_date = datetime('now') WHERE id = ?",
        ).run(finalPath, file.id);
        logAction(db, "accept", file.id, {
          source_path: file.source_path,
          destination_path: finalPath,
          batch: true,
        });
        accepted++;
      } catch (e) {
        errors.push({ file: file.source_path, error: e.message });
      }
    }

    res.json({ ok: true, accepted, errors });
  });

  // Reject a file — log first (so FK exists), then delete dependents, then the file
  router.post("/api/files/:id/reject", (req, res) => {
    const fileId = parseInt(req.params.id);
    const file = db
      .prepare("SELECT * FROM files WHERE id = ? AND status = 'pending'")
      .get(fileId);
    if (!file) return res.status(404).json({ error: "Not found" });

    // Clean up FK dependents before deleting the file
    db.prepare("DELETE FROM file_tags WHERE file_id = ?").run(fileId);
    db.prepare("DELETE FROM suggestions WHERE file_id = ?").run(fileId);
    db.prepare("DELETE FROM actions WHERE file_id = ?").run(fileId);
    db.prepare("DELETE FROM files WHERE id = ?").run(fileId);
    // Log after delete (can't FK-reference a deleted row, so log to null)
    logAction(db, "reject", null, { source_path: file.source_path, file_id: fileId });
    res.json({ ok: true });
  });

  // Skip a file
  router.post("/api/files/:id/skip", (req, res) => {
    const fileId = parseInt(req.params.id);
    db.prepare(
      "UPDATE files SET skipped_at = datetime('now') WHERE id = ? AND status = 'pending'",
    ).run(fileId);
    logAction(db, "discover", fileId, { action: "skip" });
    res.json({ ok: true });
  });

  // Toggle favorite
  router.post("/api/files/:id/favorite", (req, res) => {
    const fileId = parseInt(req.params.id);
    const file = db.prepare("SELECT favorite FROM files WHERE id = ?").get(fileId);
    if (!file) return res.status(404).json({ error: "Not found" });

    const newVal = file.favorite ? 0 : 1;
    db.prepare("UPDATE files SET favorite = ? WHERE id = ?").run(newVal, fileId);
    logAction(db, newVal ? "favorite" : "unfavorite", fileId, {});
    res.json({ ok: true, favorite: !!newVal });
  });

  // Preview path (AJAX)
  router.post("/api/files/:id/preview-path", async (req, res) => {
    const fileId = parseInt(req.params.id);
    const file = db.prepare("SELECT * FROM files WHERE id = ?").get(fileId);
    if (!file) return res.status(404).json({ error: "Not found" });

    const tags = {};
    for (const [field, val] of Object.entries(req.body)) {
      if (val && typeof val === "string" && val.trim()) {
        tags[field] = [val.trim()];
      }
    }

    const originalFilename = basename(file.source_path);
    const path = derivePath(file.root, tags, originalFilename);
    res.json({ path });
  });

  return router;
}
