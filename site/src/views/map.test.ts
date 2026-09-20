import { describe, expect, it } from "vitest";

import type { MapData, VacancyRow } from "../lib/types";
import { DEFAULT_STATE } from "./common";
import { buildMapView, classOf, mapBreaks, shade } from "./map";

const win = { months: [0, 1], previous: null, partial: false };

const map: MapData = {
  corops: [
    { id: "groot-amsterdam", code: "CR23", name: "Groot-Amsterdam", province: "noord-holland" },
    { id: "alkmaar-en-omgeving", code: "CR19", name: "Alkmaar en omgeving", province: "noord-holland" },
    { id: "oost-groningen", code: "CR01", name: "Oost-Groningen", province: "groningen" },
  ],
  rows: [
    [0, "groot-amsterdam", "all", "all", 40],
    [1, "groot-amsterdam", "all", "all", 20],
    [1, "groot-amsterdam", "informatica", "all", 12],
    [1, "alkmaar-en-omgeving", "all", "all", 5],
    [2, "alkmaar-en-omgeving", "all", "all", 99], // outside the window
  ],
};
// The national totals include vacancies without a place, so they exceed the map's total.
const nl: VacancyRow[] = [
  [0, "all", "all", 50],
  [1, "all", "all", 30],
  [1, "informatica", "all", 15],
];

describe("mapBreaks", () => {
  it("returns no breaks when there is nothing to classify", () => {
    expect(mapBreaks([])).toEqual([]);
    expect(mapBreaks([7])).toEqual([]);
  });

  it("gives rising, rounded boundaries", () => {
    const breaks = mapBreaks([1, 2, 3, 4, 8, 12, 30, 44, 120, 260]);
    expect(breaks).toEqual([...breaks].sort((a, b) => a - b));
    expect(new Set(breaks).size).toBe(breaks.length);
    expect(breaks.every((b) => b > 1)).toBe(true);
  });

  it("puts a count in the class its boundary opens", () => {
    const breaks = [3, 8, 20, 30];
    expect(classOf(0, breaks)).toBe(0);
    expect(classOf(1, breaks)).toBe(1);
    expect(classOf(3, breaks)).toBe(2);
    expect(classOf(19, breaks)).toBe(3);
    expect(classOf(1000, breaks)).toBe(5);
  });
});

describe("buildMapView", () => {
  it("counts the months in the window, per programme", () => {
    const view = buildMapView(DEFAULT_STATE, map, nl, win);
    expect(view.areas.map((a) => [a.id, a.n])).toEqual([
      ["groot-amsterdam", 60],
      ["alkmaar-en-omgeving", 5],
      ["oost-groningen", 0],
    ]);
    expect(view.byCode.get("CR23")?.n).toBe(60);

    const informatica = buildMapView({ ...DEFAULT_STATE, programme: "informatica" }, map, nl, win);
    expect(informatica.areas[0].n).toBe(12);
  });

  it("reports the vacancies that are not on the map", () => {
    const view = buildMapView(DEFAULT_STATE, map, nl, win);
    expect(view.placed).toBe(65);
    expect(view.total).toBe(80);
    expect(view.unknown).toBe(15);
  });

  it("never reports a negative remainder", () => {
    const view = buildMapView(DEFAULT_STATE, map, [], win);
    expect(view.unknown).toBe(0);
  });

  it("gives an area without vacancies the empty class", () => {
    const view = buildMapView(DEFAULT_STATE, map, nl, win);
    expect(view.areas[view.areas.length - 1].klass).toBe(0);
  });

  it("paints the busiest area in the darkest shade, whatever the number of classes", () => {
    for (const classes of [2, 3, 4, 5]) {
      expect(shade(1, classes)).toBe(1);
      expect(shade(classes, classes)).toBe(5);
    }
    expect(shade(0, 4)).toBe(0);
  });
});
