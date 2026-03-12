import { readFileSync, watchFile } from "node:fs";
import { resolve, dirname } from "node:path";
import { homedir } from "node:os";
import YAML from "yaml";

const DEFAULT_CONFIG_PATH = resolve(homedir(), ".pinpoint", "config.yaml");

function expandPath(p, baseDir) {
  if (p.startsWith("~/")) return resolve(homedir(), p.slice(2));
  return resolve(baseDir, p);
}

function parseConfig(raw, configDir) {
  const inputs = (raw.inputs || []).map((inp) => ({
    path: expandPath(inp.path, configDir),
    root: inp.root,
  }));
  const output = expandPath(raw.output || "~/.pinpoint/files", configDir);
  const dataDir = expandPath(raw.data_dir || "~/.pinpoint", configDir);
  const analysis = {
    tmdbApiKey: raw.analysis?.tmdb_api_key || process.env.TMDB_API_KEY || "",
    ollamaUrl: raw.analysis?.ollama_url || "http://localhost:11434",
    ollamaModel: raw.analysis?.ollama_model || "llava",
    enabled: raw.analysis?.enabled !== false,
  };
  return { inputs, output, dataDir, analysis };
}

export function loadConfig(configPath) {
  const p = configPath || process.env.PINPOINT_CONFIG || DEFAULT_CONFIG_PATH;
  const resolved = resolve(p);
  const configDir = dirname(resolved);
  const text = readFileSync(resolved, "utf-8");
  const raw = YAML.parse(text);
  return parseConfig(raw, configDir);
}

export class ConfigHolder {
  constructor(configPath) {
    this.configPath =
      configPath || process.env.PINPOINT_CONFIG || DEFAULT_CONFIG_PATH;
    this.config = loadConfig(this.configPath);
    this._watch();
  }

  _watch() {
    watchFile(this.configPath, { interval: 2000 }, () => {
      try {
        this.config = loadConfig(this.configPath);
        console.log("[config] reloaded");
      } catch (e) {
        console.error("[config] reload failed:", e.message);
      }
    });
  }
}
