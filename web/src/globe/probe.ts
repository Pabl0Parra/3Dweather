// Tap readout: what the waves are doing at one point.
import type { WaveSample } from "./field";
import { formatLength, type Units } from "./units";

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
