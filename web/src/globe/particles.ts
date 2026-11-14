// Particle trails that run the way the waves travel. Trails are kept as lon/lat
// so they stay on the ground while the globe turns.
import type { LandGrid } from "./field";
import { radiusPx, unproject, wrapLon, type View } from "./view";

export const TRAIL = 14;
const GAIN = 14;
const BASE_DEG = 0.012;
const MAX_ALPHA = 0.55;
const D = Math.PI / 180;

export type Field = (lat: number, lon: number) => { u: number; v: number } | null;
type Spawn = () => [number, number];

export function particleCount(diskAreaPx: number, cssWidth: number): number {
  const max = cssWidth < 720 ? 2400 : 5000;
  return Math.round(Math.max(400, Math.min(max, diskAreaPx / 95)));
}

/** One step along the wave vector (u east, v north). */
export function stepPoint(lat: number, lon: number, u: number, v: number): [number, number] {
  const len = Math.hypot(u, v);
  if (len === 0) return [lat, lon];
  const deg = BASE_DEG * GAIN * len ** 0.65;
  const dlat = (deg * v) / len;
  const dlon = (deg * u) / len / Math.max(Math.cos(lat * D), 0.05);
  return [lat + dlat, wrapLon(lon + dlon)];
}

/** A trail segment is drawn only if it is short on screen (long ones wrap or cross the limb). */
export function segmentOk(ax: number, ay: number, bx: number, by: number, r: number): boolean {
  return Math.hypot(bx - ax, by - ay) <= 0.25 * r;
}

/** A random point on the visible disk, on the sea when one can be found. */
export function spawnOnDisk(v: View, w: number, h: number, land: LandGrid | null, rand: () => number): [number, number] {
  const r = radiusPx(v.zoom, w, h);
  let last: [number, number] = [v.lat0, v.lon0];
  for (let i = 0; i < 30; i++) {
    const rr = r * Math.sqrt(rand()) * 0.999, th = rand() * 2 * Math.PI;
    const sx = w / 2 + rr * Math.cos(th), sy = h / 2 + rr * Math.sin(th);
    if (sx < 0 || sy < 0 || sx > w || sy > h) continue; // zoomed in: keep to the screen
    const p = unproject(v, w, h, sx, sy);
    if (!p) continue;
    last = [p.lat, p.lon];
    if (!land || !land.isLand(p.lat, p.lon)) return last;
  }
  return last;
}

export class Particles {
  private n = 0;
  private lat = new Float32Array(0);
  private lon = new Float32Array(0);
  private len = new Uint8Array(0); // filled trail points
  private headIx = new Uint8Array(0); // ring position of the newest point
  private age = new Uint16Array(0);
  private maxAge = new Uint16Array(0);
  /** 0..1: during the intro, trails slide in from the screen edge. */
  arrival = 1;

  constructor(private rand: () => number = Math.random) {}

  get count(): number {
    return this.n;
  }

  resize(n: number, spawn: Spawn): void {
    const old = this.n;
    const grow = <T extends Float32Array | Uint8Array | Uint16Array>(a: T, C: new (k: number) => T, per: number): T => {
      const b = new C(n * per);
      b.set(a.subarray(0, Math.min(a.length, n * per)));
      return b;
    };
    this.lat = grow(this.lat, Float32Array, TRAIL);
    this.lon = grow(this.lon, Float32Array, TRAIL);
    this.len = grow(this.len, Uint8Array, 1);
    this.headIx = grow(this.headIx, Uint8Array, 1);
    this.age = grow(this.age, Uint16Array, 1);
    this.maxAge = grow(this.maxAge, Uint16Array, 1);
    this.n = n;
    for (let i = old; i < n; i++) this.respawn(i, spawn());
  }

  /** Newest point of particle i as [lat, lon]. */
  head(i: number): [number, number] {
    const k = i * TRAIL + this.headIx[i];
    return [this.lat[k], this.lon[k]];
  }

  private respawn(i: number, [lat, lon]: [number, number]): void {
    const base = i * TRAIL;
    this.lat.fill(lat, base, base + TRAIL);
    this.lon.fill(lon, base, base + TRAIL);
    this.len[i] = 1;
    this.headIx[i] = 0;
    // Stagger first lifetimes so particles don't all respawn together.
    this.age[i] = 0;
    this.maxAge[i] = 40 + Math.floor(this.rand() * 81);
  }

  step(field: Field, spawn: Spawn, isGone: (lat: number, lon: number) => boolean): void {
    for (let i = 0; i < this.n; i++) {
      const [lat, lon] = this.head(i);
      if (this.age[i] >= this.maxAge[i] || isGone(lat, lon)) { this.respawn(i, spawn()); continue; }
      const f = field(lat, lon);
      if (!f) { this.respawn(i, spawn()); continue; }
      const [nlat, nlon] = stepPoint(lat, lon, f.u, f.v);
      const h = (this.headIx[i] + 1) % TRAIL;
      this.headIx[i] = h;
      this.lat[i * TRAIL + h] = nlat;
      this.lon[i * TRAIL + h] = nlon;
      if (this.len[i] < TRAIL) this.len[i]++;
      this.age[i]++;
    }
  }

  /** Draw trails, older segments fainter. Coordinates are CSS pixels. */
  draw(ctx: CanvasRenderingContext2D, v: View, w: number, h: number): void {
    const r = radiusPx(v.zoom, w, h);
    const cx = w / 2, cy = h / 2;
    const s0 = Math.sin(v.lat0 * D), c0 = Math.cos(v.lat0 * D);
    // Intro: points start pushed out towards the screen edge and settle onto the globe.
    const push = 1 + (1 - this.arrival) * 1.6;
    const xs = new Float32Array(TRAIL), ys = new Float32Array(TRAIL);
    const vis = new Uint8Array(TRAIL);
    const paths: Path2D[] = Array.from({ length: TRAIL - 1 }, () => new Path2D());
    for (let i = 0; i < this.n; i++) {
      const n = this.len[i];
      if (n < 2) continue;
      for (let j = 0; j < n; j++) {
        const k = i * TRAIL + ((this.headIx[i] - (n - 1 - j) + TRAIL) % TRAIL); // oldest → newest
        const p = this.lat[k] * D, dl = (this.lon[k] - v.lon0) * D;
        const cp = Math.cos(p), sp = Math.sin(p), cdl = Math.cos(dl);
        vis[j] = s0 * sp + c0 * cp * cdl >= 0 ? 1 : 0;
        xs[j] = cx + r * cp * Math.sin(dl) * push;
        ys[j] = cy - r * (c0 * sp - s0 * cp * cdl) * push;
      }
      for (let j = 1; j < n; j++) {
        if (!vis[j] || !vis[j - 1] || !segmentOk(xs[j - 1], ys[j - 1], xs[j], ys[j], r)) continue;
        const path = paths[TRAIL - 1 - (n - j)]; // newest segment in the brightest bucket
        path.moveTo(xs[j - 1], ys[j - 1]);
        path.lineTo(xs[j], ys[j]);
      }
    }
    ctx.lineWidth = 1.1;
    ctx.strokeStyle = "#ffffff";
    for (let b = 0; b < paths.length; b++) {
      ctx.globalAlpha = MAX_ALPHA * ((b + 1) / paths.length) * this.arrival ** 0.5;
      ctx.stroke(paths[b]);
    }
    ctx.globalAlpha = 1;
  }
}
