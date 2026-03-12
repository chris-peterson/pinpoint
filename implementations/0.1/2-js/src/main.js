import { resolve, join } from "node:path";
import { existsSync } from "node:fs";
import express from "express";
import nunjucks from "nunjucks";

import { ConfigHolder } from "./config.js";
import { openDatabase } from "./database.js";
import { runDiscovery } from "./discovery.js";
import { createQueueRouter } from "./api/queue.js";
import { createTagsRouter } from "./api/tags.js";
import { createWebRouter } from "./web/routes.js";

const PORT = 8420;

// Parse --config flag
const args = process.argv.slice(2);
let configPath = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--config" && args[i + 1]) {
    configPath = resolve(args[i + 1]);
  }
}

const configHolder = new ConfigHolder(configPath);
const config = configHolder.config;

console.log(`[pinpoint] data dir: ${config.dataDir}`);
console.log(`[pinpoint] output:   ${config.output}`);
console.log(`[pinpoint] inputs:   ${config.inputs.map((i) => `${i.path} (${i.root})`).join(", ")}`);

const dbPath = join(config.dataDir, "pinpoint.db");
const db = openDatabase(dbPath);

// Run initial discovery
const disc = runDiscovery(db, config);
console.log(
  `[discovery] complete: ${disc.discovered} new files, ${disc.duplicates} duplicates`,
);

// Set up Express
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Static files
const staticDir = resolve(import.meta.dirname, "web", "static");
app.use("/static", express.static(staticDir));

// Nunjucks templating
const templatesDir = resolve(import.meta.dirname, "web", "templates");
const nunjucksEnv = nunjucks.configure(templatesDir, {
  autoescape: true,
  noCache: true,
});

// Mount routers
app.use(createQueueRouter(db, configHolder));
app.use(createTagsRouter(db, configHolder));
app.use(createWebRouter(db, configHolder, nunjucksEnv));

app.listen(PORT, () => {
  console.log(`[pinpoint] listening on http://localhost:${PORT}`);
});

// Re-run discovery periodically
setInterval(() => {
  try {
    const result = runDiscovery(db, configHolder.config);
    if (result.discovered > 0) {
      console.log(`[discovery] periodic: ${result.discovered} new files`);
    }
  } catch (e) {
    console.error("[discovery] periodic error:", e.message);
  }
}, 10_000);
