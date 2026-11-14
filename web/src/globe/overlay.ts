// 2D overlay above the WebGL globe: graticule and coastline.
import { project, type View } from "./view";

const COAST = "rgba(140,235,255,0.55)";
const GRATICULE = "rgba(90,150,210,0.18)";

/** Screen points of one flat [lon, lat, lon, lat, ...] line, split where it goes behind the globe. */
export function visibleRuns(v: View, w: number, h: number, flat: number[]): [number, number][][] {
  const runs: [number, number][][] = [];
  let run: [number, number][] | null = null;
  for (let i = 0; i + 1 < flat.length; i += 2) {
    const p = project(v, w, h, flat[i + 1], flat[i]);
    if (p.visible) {
      if (!run) runs.push((run = []));
      run.push([p.x, p.y]);
    } else {
      run = null;
    }
  }
  return runs;
}

function graticule(): number[][] {
  const lines: number[][] = [];
  for (let lon = -180; lon < 180; lon += 30) {
    const l: number[] = [];
    for (let lat = -90; lat <= 90; lat += 2) l.push(lon, lat);
    lines.push(l);
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const l: number[] = [];
    for (let lon = -180; lon <= 180; lon += 2) l.push(lon, lat);
    lines.push(l);
  }
  return lines;
}

const GRID = graticule();

function stroke(ctx: CanvasRenderingContext2D, v: View, w: number, h: number, lines: number[][]): void {
  ctx.beginPath();
  for (const line of lines)
    for (const run of visibleRuns(v, w, h, line)) {
      if (run.length < 2) continue;
      ctx.moveTo(run[0][0], run[0][1]);
      for (let k = 1; k < run.length; k++) ctx.lineTo(run[k][0], run[k][1]);
    }
  ctx.stroke();
}

/** Graticule every 30 degrees, then the coastline. Coordinates are CSS pixels. */
export function drawOverlay(ctx: CanvasRenderingContext2D, v: View, w: number, h: number, coast: number[][]): void {
  ctx.clearRect(0, 0, w, h);
  ctx.lineJoin = "round";
  ctx.lineWidth = 1;
  ctx.strokeStyle = GRATICULE;
  stroke(ctx, v, w, h, GRID);
  ctx.strokeStyle = COAST;
  ctx.lineWidth = v.zoom > 4 ? 1.2 : 0.8;
  stroke(ctx, v, w, h, coast);
}
