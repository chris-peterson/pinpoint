import { Router } from "express";
import { basename, extname, join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { defaultsFromSource } from "../defaults.js";
import { derivePath } from "../paths.js";
import { ROOT_FIELDS, MULTI_VALUE_FIELDS, EXPECTED_TAGS, ROOT_DIRS } from "../models.js";

const FOLDER_GROUPING = {
  memory: ["event"],
  music: ["artist", "album"],
  book: ["author"],
  podcast: ["show"],
  tv: ["show", "season"],
  movie: ["series"],
  comedy: ["artist"],
};

export function createWebRouter(db, configHolder, nunjucks) {
  const router = Router();

  // Home — search + browse + On This Day
  router.get("/", (req, res) => {
    const config = configHolder.config;
    const q = req.query.q || "";
    const filterRoot = req.query.root || "";
    const filterClass = req.query.file_class || "";

    const pendingCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL")
      .get().count;
    const managedCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'managed'")
      .get().count;
    const missingCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'missing'")
      .get().count;

    const rootCounts = db
      .prepare("SELECT root, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY root ORDER BY root")
      .all();
    const classCounts = db
      .prepare("SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'managed' GROUP BY file_class ORDER BY file_class")
      .all();

    // Search
    let results = [];
    if (q && q.length >= 2) {
      const likeQ = `%${q}%`;
      results = db
        .prepare(
          `SELECT f.id, f.managed_path, f.source_path, f.root, f.file_class,
                  f.status, f.favorite,
                  GROUP_CONCAT(t.name, ', ') as tag_list
           FROM files f
           LEFT JOIN file_tags ft ON f.id = ft.file_id
           LEFT JOIN tags t ON ft.tag_id = t.id
           WHERE f.status IN ('managed', 'drifted')
             AND (f.managed_path LIKE ? OR f.source_path LIKE ? OR t.name LIKE ?)
           GROUP BY f.id
           ORDER BY f.favorite DESC, f.managed_date DESC
           LIMIT 50`,
        )
        .all(likeQ, likeQ, likeQ);
    }

    // Folder cards (browse mode)
    let folders = [];
    if (!q) {
      let where = "status = 'managed'";
      const params = [];
      if (filterRoot) {
        where += " AND root = ?";
        params.push(filterRoot);
      }
      if (filterClass) {
        where += " AND file_class = ?";
        params.push(filterClass);
      }

      const managedFiles = db
        .prepare(
          `SELECT f.id, f.managed_path, f.root, f.file_class, f.favorite
           FROM files f
           WHERE ${where}
           ORDER BY f.managed_date DESC`,
        )
        .all(...params);

      const outputPrefix = config.output;
      const seenFolders = new Map();

      for (const row of managedFiles) {
        const managed = row.managed_path || "";
        const fileRoot = row.root;
        const groupingKeys = FOLDER_GROUPING[fileRoot] || [];

        let relative = managed;
        if (managed.startsWith(outputPrefix)) {
          relative = managed.slice(outputPrefix.length).replace(/^\//, "");
        }
        const parts = relative.split("/");
        const depth = groupingKeys.length + 1;
        const folderParts = parts.length > depth ? parts.slice(0, depth) : parts.slice(0, -1);
        const folderKey = folderParts.length > 0 ? folderParts.join("/") : fileRoot;

        if (!seenFolders.has(folderKey)) {
          seenFolders.set(folderKey, {
            key: folderKey,
            label: folderParts.length > 0 ? folderParts[folderParts.length - 1] : fileRoot,
            root: fileRoot,
            count: 0,
            heroId: null,
            hasImages: false,
          });
        }
        const card = seenFolders.get(folderKey);
        card.count++;
        if (!card.heroId && row.file_class === "image") {
          card.heroId = row.id;
          card.hasImages = true;
        }
      }

      folders = Array.from(seenFolders.values()).sort((a, b) =>
        a.key.localeCompare(b.key),
      );
    }

    // On This Day
    const now = new Date();
    const monthDay = `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const onThisDay = db
      .prepare(
        `SELECT id, managed_path, file_class, creation_date
         FROM files
         WHERE status = 'managed' AND root = 'memory'
           AND substr(creation_date, 6, 5) = ?
         ORDER BY creation_date ASC
         LIMIT 20`,
      )
      .all(monthDay)
      .map((row) => ({
        id: row.id,
        fileClass: row.file_class,
        year: row.creation_date ? row.creation_date.slice(0, 4) : "?",
        path: row.managed_path || "",
      }));

    res.send(
      nunjucks.render("home.html", {
        q,
        results,
        pendingCount,
        managedCount,
        missingCount,
        folders,
        onThisDay,
        filterRoot,
        filterClass,
        rootCounts,
        classCounts,
      }),
    );
  });

  // Live search API (returns HTML fragment)
  router.get("/api/search", (req, res) => {
    const q = req.query.q || "";
    if (q.length < 2) {
      return res.send(nunjucks.render("_search_results.html", { results: [], q }));
    }

    const likeQ = `%${q}%`;
    const results = db
      .prepare(
        `SELECT f.id, f.managed_path, f.source_path, f.root, f.file_class,
                f.status, f.favorite,
                GROUP_CONCAT(t.name, ', ') as tag_list
         FROM files f
         LEFT JOIN file_tags ft ON f.id = ft.file_id
         LEFT JOIN tags t ON ft.tag_id = t.id
         WHERE f.status IN ('managed', 'drifted')
           AND (f.managed_path LIKE ? OR f.source_path LIKE ? OR t.name LIKE ?)
         GROUP BY f.id
         ORDER BY f.favorite DESC, f.managed_date DESC
         LIMIT 50`,
      )
      .all(likeQ, likeQ, likeQ);

    res.send(nunjucks.render("_search_results.html", { results, q }));
  });

  // Queue page
  router.get("/queue", async (req, res) => {
    const config = configHolder.config;
    const filterRoot = req.query.root || "";
    const filterClass = req.query.file_class || "";

    let where = "status = 'pending' AND skipped_at IS NULL";
    const params = [];
    if (filterRoot) {
      where += " AND root = ?";
      params.push(filterRoot);
    }
    if (filterClass) {
      where += " AND file_class = ?";
      params.push(filterClass);
    }

    const row = db
      .prepare(
        `SELECT * FROM files WHERE ${where} ORDER BY discovery_date DESC LIMIT 1`,
      )
      .get(...params);

    const totalPending = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL")
      .get().count;

    const rootCounts = db
      .prepare(
        "SELECT root, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY root",
      )
      .all();
    const classCounts = db
      .prepare(
        "SELECT file_class, COUNT(*) as cnt FROM files WHERE status = 'pending' AND skipped_at IS NULL GROUP BY file_class",
      )
      .all();

    let file = null;
    let rootFields = [];
    let fieldDefaults = {};
    let filenameDefs = {};
    let metadataDefs = {};
    let expectedTags = [];
    let pathPreview = "";
    let sourceFolder = "";
    let folderCount = 0;
    let folderReady = false;

    if (row) {
      file = row;
      rootFields = ROOT_FIELDS[row.root] || [];
      expectedTags = EXPECTED_TAGS[row.root] || [];

      const inputPath = config.inputs.find((inp) =>
        row.source_path.startsWith(inp.path),
      )?.path || "";

      const defs = await defaultsFromSource(row.source_path, row.root, inputPath);
      filenameDefs = defs.filenameDefs;
      metadataDefs = defs.metadataDefs;
      fieldDefaults = defs.merged;

      // Compute path preview
      const tags = {};
      for (const [field, val] of Object.entries(fieldDefaults)) {
        if (val) tags[field] = [val];
      }
      const originalFilename = basename(row.source_path);
      pathPreview = derivePath(row.root, tags, originalFilename);

      // Source folder info
      const srcDir = row.source_path.slice(0, row.source_path.lastIndexOf("/"));
      sourceFolder = srcDir;
      const folderFiles = db
        .prepare(
          "SELECT id, source_path, root FROM files WHERE source_path LIKE ? AND status = 'pending' AND skipped_at IS NULL",
        )
        .all(srcDir + "/%");
      folderCount = folderFiles.length;

      // [MQ-7] Check if all folder files have stable metadata for "accept all"
      if (folderCount > 1) {
        let allReady = true;
        for (const ff of folderFiles) {
          const ffInputPath = config.inputs.find((inp) =>
            ff.source_path.startsWith(inp.path),
          )?.path || "";
          const ffDefs = await defaultsFromSource(ff.source_path, ff.root, ffInputPath);
          const ffExpected = EXPECTED_TAGS[ff.root] || [];
          const ffMerged = { ...ffDefs.filenameDefs, ...ffDefs.metadataDefs };
          for (const tag of ffExpected) {
            if (!ffMerged[tag]) {
              allReady = false;
              break;
            }
          }
          if (!allReady) break;
        }
        folderReady = allReady;
      }
    }

    res.send(
      nunjucks.render("queue.html", {
        file,
        rootFields,
        fieldDefaults,
        filenameDefs,
        metadataDefs,
        expectedTags,
        pathPreview,
        totalPending,
        rootCounts,
        classCounts,
        filterRoot,
        filterClass,
        sourceFolder,
        folderCount,
        folderReady,
        multiValueFields: [...MULTI_VALUE_FIELDS],
      }),
    );
  });

  // Browse folder — use query param since Express 5 path-to-regexp v8 doesn't support wildcards easily
  router.get("/browse", (req, res) => {
    const folderPath = req.query.path || "";
    const config = configHolder.config;
    const outputPrefix = config.output;

    const searchPrefix = join(config.output, folderPath) + "/";
    const rows = db
      .prepare(
        `SELECT f.id, f.managed_path, f.file_class, f.favorite, f.root,
                GROUP_CONCAT(t.name, ', ') as tag_list
         FROM files f
         LEFT JOIN file_tags ft ON f.id = ft.file_id
         LEFT JOIN tags t ON ft.tag_id = t.id
         WHERE f.status = 'managed' AND f.managed_path LIKE ?
         GROUP BY f.id
         ORDER BY f.managed_path ASC`,
      )
      .all(searchPrefix + "%");

    const files = [];
    const subfolders = new Map();

    for (const row of rows) {
      const managed = row.managed_path || "";
      let relative = managed;
      if (managed.startsWith(outputPrefix)) {
        relative = managed.slice(outputPrefix.length).replace(/^\//, "");
      }

      let inner = relative;
      if (relative.startsWith(folderPath + "/")) {
        inner = relative.slice(folderPath.length + 1);
      }

      const parts = inner.split("/");
      if (parts.length === 1) {
        files.push({
          id: row.id,
          name: parts[0],
          fileClass: row.file_class,
          favorite: row.favorite,
          tagList: row.tag_list || "",
        });
      } else {
        const subName = parts[0];
        const subKey = folderPath + "/" + subName;
        if (!subfolders.has(subName)) {
          subfolders.set(subName, {
            name: subName,
            key: subKey,
            count: 0,
            heroId: null,
          });
        }
        const sub = subfolders.get(subName);
        sub.count++;
        if (!sub.heroId && row.file_class === "image") {
          sub.heroId = row.id;
        }
      }
    }

    const breadcrumbs = [];
    let accumulated = "";
    for (const part of folderPath.split("/")) {
      accumulated = accumulated ? accumulated + "/" + part : part;
      breadcrumbs.push({ label: part, path: accumulated });
    }

    const pendingCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL")
      .get().count;

    res.send(
      nunjucks.render("browse.html", {
        folderPath,
        folderName: folderPath.split("/").pop(),
        breadcrumbs,
        files,
        subfolders: Array.from(subfolders.values()).sort((a, b) =>
          a.name.localeCompare(b.name),
        ),
        pendingCount,
      }),
    );
  });

  // File detail
  router.get("/files/:id", (req, res) => {
    const fileId = parseInt(req.params.id);
    const file = db.prepare("SELECT * FROM files WHERE id = ?").get(fileId);
    if (!file) return res.status(404).send("Not found");

    const tags = db
      .prepare(
        `SELECT t.id, t.name, t.type FROM tags t
         JOIN file_tags ft ON t.id = ft.tag_id
         WHERE ft.file_id = ?`,
      )
      .all(fileId);

    const rootFields = ROOT_FIELDS[file.root] || [];
    const fieldIds = new Set(rootFields.map(([id]) => id));
    const tagValues = {};
    const personValues = [];
    const extraTags = [];

    for (const tag of tags) {
      const prefix = `${tag.type}:`;
      const value = tag.name.startsWith(prefix) ? tag.name.slice(prefix.length) : tag.name;
      if (fieldIds.has(tag.type)) {
        if (MULTI_VALUE_FIELDS.has(tag.type)) {
          personValues.push(value);
        } else {
          tagValues[tag.type] = value;
        }
      } else {
        extraTags.push(tag);
      }
    }

    const pendingCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL")
      .get().count;

    const recentActions = db
      .prepare(
        "SELECT * FROM actions WHERE file_id = ? ORDER BY timestamp DESC LIMIT 20",
      )
      .all(fileId);

    res.send(
      nunjucks.render("file_detail.html", {
        file,
        tags,
        extraTags,
        tagValues,
        personValues,
        rootFields,
        pendingCount,
        recentActions,
        multiValueFields: [...MULTI_VALUE_FIELDS],
      }),
    );
  });

  // Library (flat list)
  router.get("/library", (req, res) => {
    const rows = db
      .prepare(
        `SELECT f.*, GROUP_CONCAT(t.name, ', ') as tag_list
         FROM files f
         LEFT JOIN file_tags ft ON f.id = ft.file_id
         LEFT JOIN tags t ON ft.tag_id = t.id
         WHERE f.status = 'managed'
         GROUP BY f.id
         ORDER BY f.favorite DESC, f.managed_date DESC
         LIMIT 200`,
      )
      .all();

    const pendingCount = db
      .prepare("SELECT COUNT(*) as count FROM files WHERE status = 'pending' AND skipped_at IS NULL")
      .get().count;

    res.send(
      nunjucks.render("library.html", {
        files: rows,
        pendingCount,
      }),
    );
  });

  // Serve managed files for preview
  router.get("/preview/:id", (req, res) => {
    const fileId = parseInt(req.params.id);
    const file = db.prepare("SELECT * FROM files WHERE id = ?").get(fileId);
    if (!file) return res.status(404).send("Not found");

    const filePath = file.status === "managed" ? file.managed_path : file.source_path;
    if (!filePath || !existsSync(filePath)) {
      return res.status(404).send("File not found on disk");
    }

    res.sendFile(filePath);
  });

  return router;
}
