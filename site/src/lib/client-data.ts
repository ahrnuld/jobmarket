// Browser-side access to public/data, with an in-memory cache per file.

import type { GeoData, MapData, Meta, Stats } from "./types";

const cache = new Map<string, Promise<unknown>>();

function getJson<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${url}`);
      return r.json();
    }).catch((e) => {
      cache.delete(url); // allow a retry
      throw e;
    }));
  }
  return cache.get(url) as Promise<T>;
}

export const fetchMeta = () => getJson<Meta>("/data/meta.json");
export const fetchStats = () => getJson<Stats>("/data/stats.json");
export const fetchMap = (): Promise<MapData> =>
  getJson<MapData>("/data/map.json").catch((e) => {
    if (String(e).startsWith("Error: 404")) return { corops: [], rows: [] };
    throw e;
  });

export async function fetchGeo(geoId: string, kinds: (keyof GeoData)[]): Promise<GeoData> {
  const file = geoId.replace(":", "-");
  const out: Partial<GeoData> = { vacancies: [], skills: [], families: [], titles: [], salaries: [] };
  await Promise.all(kinds.map(async (k) => {
    try {
      (out as Record<string, unknown>)[k] = await getJson(`/data/geo/${file}/${k}.json`);
    } catch (e) {
      // A geography without data has no files; anything else is a real error.
      if (!String(e).startsWith("Error: 404")) throw e;
    }
  }));
  return out as GeoData;
}
