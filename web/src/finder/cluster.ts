// Grid clustering for the finder map: points falling in the same screen-sized cell at a zoom level
// become one marker at their mean position. Cheap enough to redo on every pan/zoom over 25,000 points.

export type Point = { lat: number; lon: number; name: string; path: string };
export type Cluster = { lat: number; lon: number; n: number; name?: string; path?: string };

/** Web-Mercator world pixel x/y at `zoom` (256 px tiles). */
function pixel(lat: number, lon: number, zoom: number): [number, number] {
  const size = 256 * 2 ** zoom;
  const s = Math.sin((Math.max(-85, Math.min(85, lat)) * Math.PI) / 180);
  return [((lon + 180) / 360) * size, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * size];
}

export function clusterPoints(points: Point[], zoom: number, cellPx = 60): Cluster[] {
  const cells = new Map<string, { lat: number; lon: number; n: number; first: Point }>();
  for (const p of points) {
    const [x, y] = pixel(p.lat, p.lon, zoom);
    const key = `${Math.floor(x / cellPx)}:${Math.floor(y / cellPx)}`;
    const c = cells.get(key);
    if (c) { c.lat += p.lat; c.lon += p.lon; c.n += 1; }
    else cells.set(key, { lat: p.lat, lon: p.lon, n: 1, first: p });
  }
  return [...cells.values()].map((c) => (c.n === 1
    ? { lat: c.first.lat, lon: c.first.lon, n: 1, name: c.first.name, path: c.first.path }
    : { lat: c.lat / c.n, lon: c.lon / c.n, n: c.n }));
}

/** The same longitude on the world copy nearest `center` (Leaflet lets the view run past ±180). */
export function wrapNear(lon: number, center: number): number {
  return lon + 360 * Math.round((center - lon) / 360);
}
