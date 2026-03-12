import { Router } from "express";
import { renameSync, mkdirSync, existsSync, rmSync, readdirSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { derivePath, resolveCollision } from "../paths.js";
import { logAction } from "../actions.js";
import { ROOT_FIELDS, MULTI_VALUE_FIELDS, DERIVED_ATTRIBUTES } from "../models.js";

export function createTagsRouter(db, configHolder) {
  const router = Router();

  // Save tags for a managed file [TP-5, OP-11]
  router.post("/api/files/:id/tags", (req, res) => {
    const fileId = parseInt(req.params.id);
    const config = configHolder.config;

    const file = db
      .prepare("SELECT * FROM files WHERE id = ?")
      .get(fileId);
    if (!file) return res.status(404).json({ error: "Not found" });

    const rootFields = ROOT_FIELDS[file.root] || [];

    // Clear existing field-based tags
    const existingTags = db
      .prepare(
        `SELECT t.id, t.name, t.type FROM tags t
         JOIN file_tags ft ON t.id = ft.tag_id
         WHERE ft.file_id = ?`,
      )
      .all(fileId);

    const fieldIds = new Set(rootFields.map(([id]) => id));
    for (const tag of existingTags) {
      if (fieldIds.has(tag.type)) {
        db.prepare("DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?").run(
          fileId, tag.id,
        );
      }
    }

    // Insert new tags from form
    const tags = {};
    const insertTag = db.prepare(
      "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)",
    );
    const getTag = db.prepare("SELECT id FROM tags WHERE name = ?");
    const linkTag = db.prepare(
      "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
    );

    for (const [fid] of rootFields) {
      let values;
      if (MULTI_VALUE_FIELDS.has(fid)) {
        values = Array.isArray(req.body[fid])
          ? req.body[fid].filter((v) => v?.trim())
          : req.body[fid]
            ? [req.body[fid]].filter((v) => v?.trim())
            : [];
      } else {
        const val = req.body[fid]?.trim() || "";
        values = val ? [val] : [];
      }
      if (values.length === 0) continue;

      tags[fid] = values;
      for (const val of values) {
        const tagName = `${fid}:${val}`;
        insertTag.run(tagName, fid);
        const tagRow = getTag.get(tagName);
        if (tagRow) linkTag.run(fileId, tagRow.id);
      }
    }

    // Include non-field tags for path derivation
    const otherTags = db
      .prepare(
        `SELECT t.type, t.name FROM tags t
         JOIN file_tags ft ON t.id = ft.tag_id
         WHERE ft.file_id = ? AND t.type NOT IN (${rootFields.map(() => "?").join(",")})`,
      )
      .all(fileId, ...rootFields.map(([id]) => id));

    for (const t of otherTags) {
      const prefix = `${t.type}:`;
      const val = t.name.startsWith(prefix) ? t.name.slice(prefix.length) : t.name;
      if (!tags[t.type]) tags[t.type] = [];
      tags[t.type].push(val);
    }

    // Relocate if managed [OP-11]
    if (file.status === "managed" && file.managed_path) {
      const originalFilename = basename(file.managed_path);
      const relPath = derivePath(file.root, tags, originalFilename);
      const fullPath = join(config.output, relPath);

      if (fullPath !== file.managed_path) {
        const finalPath = resolveCollision(fullPath, db);
        mkdirSync(dirname(finalPath), { recursive: true });
        try {
          renameSync(file.managed_path, finalPath);

          // Clean empty directories
          let dir = dirname(file.managed_path);
          while (dir !== config.output && dir.startsWith(config.output)) {
            try {
              const entries = readdirSync(dir);
              if (entries.length === 0) {
                rmSync(dir);
                dir = dirname(dir);
              } else {
                break;
              }
            } catch {
              break;
            }
          }

          db.prepare("UPDATE files SET managed_path = ? WHERE id = ?").run(
            finalPath, fileId,
          );
          logAction(db, "relocate", fileId, {
            old_path: file.managed_path,
            new_path: finalPath,
          });
        } catch (e) {
          return res.status(500).json({ error: `Relocate failed: ${e.message}` });
        }
      }
    }

    res.json({ ok: true });
  });

  // Tag autocomplete
  router.get("/api/tags/autocomplete", (req, res) => {
    const q = req.query.q || "";
    if (q.length < 1) return res.json([]);

    const rows = db
      .prepare(
        `SELECT DISTINCT name FROM tags WHERE name LIKE ? ORDER BY name LIMIT 20`,
      )
      .all(`%${q}%`);

    res.json(rows.map((r) => r.name));
  });

  return router;
}
