// Build-time only: turns the COROP boundaries (src/data/corop-2026.json, CBS/Kadaster via
// cartomap, CC BY 4.0) into SVG paths. The geometry is rendered into the HTML once; the browser
// only recolours the existing paths when a filter changes, so it never downloads the shapes.

import geo from "../data/corop-2026.json";

const WIDTH = 560;

export interface MapShape {
  code: string; // CBS statcode, e.g. "CR01"
  name: string;
  d: string;
}

export interface MapGeometry {
  viewBox: string;
  shapes: MapShape[];
  attribution: string;
  licence: string;
}

/**
 * Equirectangular projection: longitude is compressed by the cosine of the mid latitude. Over
 * the 300 km of the Netherlands this is indistinguishable from a proper conformal projection
 * at this size, and it needs no dependency.
 */
export function buildGeometry(): MapGeometry {
  const points = geo.features.flatMap((f) => f.rings.flat());
  const lats = points.map((p) => p[1]);
  const lons = points.map((p) => p[0]);
  const k = Math.cos((((Math.min(...lats) + Math.max(...lats)) / 2) * Math.PI) / 180);
  const minX = Math.min(...lons) * k;
  const maxX = Math.max(...lons) * k;
  const minY = -Math.max(...lats);
  const maxY = -Math.min(...lats);
  const scale = WIDTH / (maxX - minX);
  const height = (maxY - minY) * scale;
  const px = (lon: number) => (lon * k - minX) * scale;
  const py = (lat: number) => (-lat - minY) * scale;

  const shapes = geo.features.map((f) => ({
    code: f.code,
    name: f.name,
    d: f.rings
      .map((ring) => ring.map((p, i) => `${i ? "L" : "M"}${px(p[0]).toFixed(1)} ${py(p[1]).toFixed(1)}`).join("") + "Z")
      .join(""),
  }));
  return {
    viewBox: `0 0 ${WIDTH} ${Math.ceil(height)}`,
    shapes,
    attribution: geo.source,
    licence: geo.licence,
  };
}
