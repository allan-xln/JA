import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";

export function resolveSessionDir() {
  return path.resolve(process.cwd(), "..", config.sessionDir);
}

export function ensureSessionDir() {
  const dir = resolveSessionDir();
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function resetSessionDir() {
  const dir = resolveSessionDir();
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, ".gitkeep"), "");
  return dir;
}
