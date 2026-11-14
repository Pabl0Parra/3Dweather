// The run pointer and per-run manifest written by the pipeline.

export type Latest = { run: string; dir: string; built: string };

export type GlobeManifest = {
  run: string;
  w: number;
  h: number;
  north: number;
  west: number;
  dlon: number;
  dlat: number;
  every: number;
  hours: number;
  frames: number;
  cols: number;
  chunks: number[];
  sources: Record<string, string>;
  peaks: Record<string, [number, number, number][]>;
};

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function loadLatest(base: string): Promise<Latest> {
  return getJson<Latest>(`${base}/latest.json`);
}

export function loadManifest(base: string, dir: string): Promise<GlobeManifest> {
  return getJson<GlobeManifest>(`${base}/${dir}/globe.json`);
}

/** The two frames around an hour and how far between them it is. */
export function framePair(m: GlobeManifest, hour: number): { a: number; b: number; mix: number } {
  const h = Math.max(0, Math.min(m.hours, hour));
  const a = Math.min(m.frames - 1, Math.floor(h / m.every));
  const b = Math.min(m.frames - 1, a + 1);
  return { a, b, mix: a === b ? 0 : h / m.every - a };
}

export function chunkSlot(m: GlobeManifest, frame: number): { chunk: number; slot: number } {
  let start = 0;
  for (let chunk = 0; chunk < m.chunks.length; chunk++) {
    if (frame < start + m.chunks[chunk]) return { chunk, slot: frame - start };
    start += m.chunks[chunk];
  }
  throw new RangeError(`frame ${frame} is past the last chunk`);
}
