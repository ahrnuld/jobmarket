// Build-time access to the published data in public/data (written by `jobmarket publish`).

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { GeoData, Meta, Stats } from "./types";

const DATA_DIR = join(process.cwd(), "public", "data");
const cache = new Map<string, unknown>();

function readJson<T>(rel: string): T {
  if (!cache.has(rel)) cache.set(rel, JSON.parse(readFileSync(join(DATA_DIR, rel), "utf-8")));
  return cache.get(rel) as T;
}

export const geoFile = (geoId: string) => geoId.replace(":", "-");

export function loadMeta(): Meta {
  return readJson<Meta>("meta.json");
}

export function loadStats(): Stats {
  return readJson<Stats>("stats.json");
}

const KINDS = ["vacancies", "skills", "families", "titles", "salaries"] as const;

export function loadGeo(geoId: string): GeoData {
  const out = {} as GeoData;
  for (const kind of KINDS) {
    try {
      (out as unknown as Record<string, unknown>)[kind] = readJson(`geo/${geoFile(geoId)}/${kind}.json`);
    } catch {
      (out as unknown as Record<string, unknown>)[kind] = [];
    }
  }
  return out;
}
