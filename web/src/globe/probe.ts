// Tap readout: what the waves are doing at one point.
import type { Sample, WaveSample } from "./field";
import type { Layer } from "./layers";
import { formatLength, formatRain, formatSpeed, formatTemp, type Units } from "./units";

const POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

export function compass(deg: number): string {
  const d = ((deg % 360) + 360) % 360;
  return POINTS[Math.round(d / 45) % 8];
}

export function formatCoord(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
}

export function readoutLines(s: WaveSample | null, lat: number, lon: number, u: Units): string[] {
  const coord = formatCoord(lat, lon);
  if (!s) return ["Land — no wave data", coord];
  if (![s.heightM, s.periodS, s.fromDeg].every(Number.isFinite)) return ["No wave data here", coord];
  if (s.heightM < 0.05) return ["Calm", coord];
  return [formatLength(s.heightM, u.length), `Period ${Math.round(s.periodS)} s`, `From ${compass(s.fromDeg)} (${Math.round(s.fromDeg) % 360}°)`, coord];
}

const fin = (x: number | undefined): x is number => x !== undefined && Number.isFinite(x);
const dir = (deg: number) => `${compass(deg)} (${Math.round(deg) % 360}°)`;

/** Readout lines for any layer. `s` is null on land for sea-only layers. */
export function readoutFor(layer: Layer, s: Sample | null, lat: number, lon: number, u: Units): string[] {
  const coord = formatCoord(lat, lon);
  switch (layer.id) {
    case "waves":
      return readoutLines(s && { heightM: s.waveM ?? NaN, periodS: s.periodS ?? NaN, fromDeg: s.waveFromDeg ?? NaN, u: 0, v: 0 }, lat, lon, u);
    case "currents": {
      if (!s) return ["Land — no current data", coord];
      if (!fin(s.currentMs)) return ["No current data here", coord];
      const lines = [s.currentMs < 0.05 ? "Slack" : `Current ${formatSpeed(s.currentMs, u.speed, 1)} toward ${compass(s.currentToDeg ?? 0)}`];
      if (fin(s.seaC)) lines.push(`Sea ${formatTemp(s.seaC, u.temp)}`);
      return [...lines, coord];
    }
    case "wind": {
      if (!s || !fin(s.windMs)) return ["No wind data here", coord];
      const lines = [s.windMs < 0.5 ? "Calm" : `Wind ${formatSpeed(s.windMs, u.speed)} from ${dir(s.windFromDeg ?? 0)}`];
      if (fin(s.gustMs)) lines.push(`Gusts ${formatSpeed(s.gustMs, u.speed)}`);
      return [...lines, coord];
    }
    case "rain": {
      if (!s || !fin(s.rainMmh)) return ["No rain data here", coord];
      const lines = [s.rainMmh < 0.05 ? "No rain" : `Rain ${formatRain(s.rainMmh, u.length)}`];
      if (fin(s.cloudPct)) lines.push(`Cloud ${Math.round(s.cloudPct)} %`);
      return [...lines, coord];
    }
    case "temperature":
      return s && fin(s.airC) ? [`Air ${formatTemp(s.airC, u.temp)}`, coord] : ["No temperature data here", coord];
  }
}

/** The readout panel. The marker itself is drawn by the globe on the flow canvas. */
export class Probe {
  private panel: HTMLDivElement;
  private body: HTMLDivElement;
  private point: { lat: number; lon: number } | null = null;
  onHide: () => void = () => {};

  constructor(root: HTMLElement) {
    this.panel = document.createElement("div");
    this.panel.className = "probe";
    this.panel.setAttribute("role", "dialog");
    this.panel.setAttribute("aria-label", "Conditions here");
    this.panel.hidden = true;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "probe-close";
    close.setAttribute("aria-label", "Close");
    close.textContent = "×";
    close.addEventListener("click", () => this.hide());
    // Keep taps on the panel from reaching the globe's gestures.
    this.panel.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.panel.addEventListener("dblclick", (e) => e.stopPropagation());
    this.body = document.createElement("div");
    this.panel.append(close, this.body);
    root.append(this.panel);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.hide(); });
  }

  show(lat: number, lon: number, lines: string[]): void {
    this.point = { lat, lon };
    this.body.replaceChildren(
      ...lines.map((l, i) => {
        const p = document.createElement("p");
        p.className = i === 0 ? "probe-main" : "probe-line";
        p.textContent = l;
        return p;
      }),
    );
    this.panel.hidden = false;
  }

  hide(): void {
    if (!this.point) return;
    this.point = null;
    this.panel.hidden = true;
    this.onHide();
  }

  at(): { lat: number; lon: number } | null {
    return this.point;
  }
}
