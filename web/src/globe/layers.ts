// The globe's layers: what each loads, how bytes become colour, and how it is labelled.
// Colour scales are our own.
import { decodeAirTemp, decodeHeight, decodeRain } from "./codecs";
import { RAMP_STOPS, type Rgba } from "./ramp";

export type LayerId = "rain" | "wind" | "temperature" | "waves" | "currents";
export type Family = "a" | "b" | "t" | "s" | "w" | "c";
export type Shade =
  | { family: Family; kind: "scalar"; channel: number; decode: (b: number) => number }
  | { family: Family; kind: "vector"; channels: [number, number] };
export type FlowSpec = { family: Family; channels: [number, number]; scale: number; seaOnly: boolean };
export type LegendKind = "length" | "speed" | "temp" | "rain";

export type Layer = {
  id: LayerId;
  path: string;
  title: string; // document title
  heading: string; // tab label
  description: string;
  families: Family[];
  shade: Shade;
  ramp: [number, Rgba][];
  /** Vector layers: speed at the top of the ramp; the ramp index is sqrt(speed / max). */
  vecMax?: number;
  legend: { title: string; kind: LegendKind; max: number; sqrt: boolean };
  overLand: boolean;
  flow: FlowSpec;
  peak: string;
  biggestLabel: string;
  credits: string;
  model: string;
};

const OM = 'via <a href="https://open-meteo.com/">Open-Meteo.com</a> (CC BY 4.0)';
const COAST = "Coastlines: Natural Earth";
const WIND_FLOW: FlowSpec = { family: "a", channels: [0, 1], scale: 25, seaOnly: false };

export const LAYERS: Record<LayerId, Layer> = {
  rain: {
    id: "rain", path: "/weather-map", title: "Rain and cloud map · 3Dweather", heading: "Rain",
    description: "Forecast rain and cloud for the next seven days on an interactive 3D globe.",
    families: ["a", "b"], shade: { family: "a", kind: "scalar", channel: 2, decode: decodeRain },
    ramp: [
      [0, [0, 0, 0, 0]], [0.1, [60, 120, 200, 110]], [1, [40, 150, 230, 185]], [4, [90, 95, 235, 210]],
      [10, [170, 70, 210, 228]], [25, [240, 90, 170, 240]], [64, [255, 230, 250, 250]],
    ],
    legend: { title: "Rain", kind: "rain", max: 64, sqrt: true }, overLand: true, flow: WIND_FLOW,
    peak: "rain", biggestLabel: "Heaviest rain",
    credits: `Rain and cloud: NOAA GFS ${OM} · ${COAST}`, model: "GFS 13 KM",
  },
  wind: {
    id: "wind", path: "/wind-map", title: "Wind map · 3Dweather", heading: "Wind",
    description: "Forecast wind speed for the next seven days on an interactive 3D globe.",
    families: ["a", "b"], shade: { family: "a", kind: "vector", channels: [0, 1] }, vecMax: 40,
    ramp: [
      [0, [20, 40, 90, 150]], [5, [30, 110, 170, 175]], [10, [40, 170, 170, 195]], [15, [120, 200, 110, 210]],
      [20, [230, 210, 70, 220]], [28, [240, 120, 50, 230]], [40, [220, 60, 160, 240]],
    ],
    legend: { title: "Wind speed", kind: "speed", max: 40, sqrt: true }, overLand: true, flow: WIND_FLOW,
    peak: "wind", biggestLabel: "Strongest wind",
    credits: `Wind: NOAA GFS; gusts: ECMWF IFS ${OM} · ${COAST}`, model: "GFS · ECMWF IFS",
  },
  temperature: {
    id: "temperature", path: "/temperature-map", title: "Temperature map · 3Dweather", heading: "Temperature",
    description: "Forecast air temperature for the next seven days on an interactive 3D globe.",
    families: ["t", "a"], shade: { family: "t", kind: "scalar", channel: 0, decode: decodeAirTemp },
    ramp: [
      [-40, [110, 60, 170, 205]], [-20, [70, 90, 200, 205]], [0, [80, 170, 220, 205]], [15, [90, 190, 120, 208]],
      [25, [230, 200, 80, 212]], [35, [235, 110, 50, 222]], [45, [150, 30, 40, 232]],
    ],
    legend: { title: "Air temperature", kind: "temp", max: 45, sqrt: false }, overLand: true, flow: WIND_FLOW,
    peak: "hot", biggestLabel: "Hottest place",
    credits: `Temperature: NOAA GFS ${OM} · ${COAST}`, model: "GFS 13 KM",
  },
  waves: {
    id: "waves", path: "/wave-map", title: "Wave map · 3Dweather", heading: "Waves",
    description: "Forecast wave height for the next seven days on an interactive 3D globe.",
    families: ["w"], shade: { family: "w", kind: "scalar", channel: 0, decode: decodeHeight },
    ramp: RAMP_STOPS,
    legend: { title: "Wave height", kind: "length", max: 16, sqrt: true }, overLand: false,
    flow: { family: "w", channels: [1, 2], scale: 1, seaOnly: true },
    peak: "wave", biggestLabel: "Biggest waves",
    credits: `Waves: NOAA GFS-Wave ${OM} · ${COAST}`, model: "GFS-WAVE · OPEN-METEO",
  },
  currents: {
    id: "currents", path: "/ocean-currents-map", title: "Ocean currents map · 3Dweather", heading: "Currents",
    description: "Forecast ocean surface currents and sea temperature for the next seven days on an interactive 3D globe.",
    families: ["c"], shade: { family: "c", kind: "vector", channels: [0, 1] }, vecMax: 2,
    ramp: [
      [0, [10, 30, 60, 120]], [0.25, [20, 90, 140, 170]], [0.5, [30, 150, 190, 200]], [1, [80, 210, 220, 220]],
      [2, [235, 250, 255, 240]],
    ],
    legend: { title: "Current speed", kind: "speed", max: 2, sqrt: true }, overLand: false,
    flow: { family: "c", channels: [0, 1], scale: 1, seaOnly: true },
    peak: "current", biggestLabel: "Strongest current",
    credits: `Currents and sea temperature: E.U. Copernicus Marine Service Information (Mercator) ${OM} · ${COAST}`,
    model: "MERCATOR · COPERNICUS",
  },
};

export const LAYER_IDS: LayerId[] = ["rain", "wind", "temperature", "waves", "currents"];

export function layerForPath(path: string): LayerId {
  const p = path.replace(/\/+$/, "");
  return LAYER_IDS.find((id) => LAYERS[id].path === p) ?? "waves";
}

export function colourOn(ramp: [number, Rgba][], v: number): Rgba {
  if (v <= ramp[0][0]) return [...ramp[0][1]] as Rgba;
  for (let i = 1; i < ramp.length; i++) {
    const [v1, c1] = ramp[i];
    if (v <= v1) {
      const [v0, c0] = ramp[i - 1];
      const t = (v - v0) / (v1 - v0);
      return c0.map((c, k) => Math.round(c + (c1[k] - c) * t)) as Rgba;
    }
  }
  return [...ramp[ramp.length - 1][1]] as Rgba;
}

/** Value a ramp index stands for: the decoded byte, or a sqrt-spaced speed for vector layers. */
export function rampValue(l: Layer, i: number): number {
  return l.shade.kind === "scalar" ? l.shade.decode(i) : (i / 255) ** 2 * (l.vecMax ?? 1);
}

/** 256 RGBA entries for a 256x1 lookup texture. */
export function rampTable(l: Layer): Uint8Array {
  const t = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) t.set(colourOn(l.ramp, rampValue(l, i)), i * 4);
  return t;
}

import { legendTicks, type Units } from "./units";

const SPEED_K: Record<Units["speed"], [number, string]> = { kn: [1.943844, "kn"], kmh: [3.6, "km/h"], ms: [1, "m/s"], mph: [2.236936, "mph"] };
const WIND_TICKS: Record<Units["speed"], number[]> = { kn: [10, 20, 40, 60], kmh: [20, 40, 80, 120], ms: [5, 10, 20, 30], mph: [10, 25, 50, 75] };
const CURRENT_TICKS: Record<Units["speed"], number[]> = { kn: [0.5, 1, 2, 3], kmh: [1, 2, 4, 6], ms: [0.25, 0.5, 1, 1.5], mph: [0.5, 1, 2, 4] };

export type LegendScale = { title: string; unit: string; ticks: [number, string][]; pos: (v: number) => number; spoken: string };

/** Legend ticks (positions in the layer's own units) and a 0..100 position function. */
export function legendScale(l: Layer, u: Units): LegendScale {
  const lo = l.ramp[0][0], hi = l.legend.max;
  const pos = (v: number) => {
    const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    return (l.legend.sqrt ? Math.sqrt(t) : t) * 100;
  };
  let unit: string, ticks: [number, string][], spoken: string;
  switch (l.legend.kind) {
    case "length":
      unit = u.length; ticks = legendTicks(u.length); spoken = u.length === "ft" ? "feet" : "metres";
      break;
    case "speed": {
      const [k, label] = SPEED_K[u.speed];
      const table = hi > 5 ? WIND_TICKS : CURRENT_TICKS;
      unit = label; spoken = label;
      ticks = table[u.speed].map((t) => [t / k, String(t)]);
      break;
    }
    case "temp":
      if (u.temp === "F") { unit = "°F"; ticks = [0, 32, 60, 90, 110].map((f) => [((f - 32) * 5) / 9, String(f)]); spoken = "degrees Fahrenheit"; }
      else { unit = "°C"; ticks = [-30, -15, 0, 15, 30, 45].map((c) => [c, String(c)]); spoken = "degrees Celsius"; }
      break;
    case "rain":
      if (u.length === "ft") { unit = "in/h"; ticks = [0.02, 0.1, 0.5, 1, 2].map((i) => [i * 25.4, String(i)]); spoken = "inches per hour"; }
      else { unit = "mm/h"; ticks = [0.5, 2, 8, 25, 64].map((m) => [m, String(m)]); spoken = "millimetres per hour"; }
      break;
  }
  return { title: l.legend.title, unit, ticks, pos, spoken };
}

/** CSS linear-gradient stops for the legend bar, on the same scale as legendScale().pos. */
export function legendGradient(l: Layer): string {
  const pos = legendScale(l, { length: "m", speed: "ms", temp: "C" } as Units).pos;
  return l.ramp.map(([v, [r, g, b]]) => `rgb(${r},${g},${b}) ${pos(v).toFixed(1)}%`).join(", ");
}
