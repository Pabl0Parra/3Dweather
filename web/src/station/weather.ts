// Station weather from the latest forecast run: wx/latest.json -> wx/{dir}/stations/{cc}/{region}.json.

export type StationWx = {
  v: 1; run: string; start: string | null; step_h: number; n: number; fields: string[];
  scale: Record<string, number>; stations: Record<string, Record<string, (number | null)[]>>;
};
export type WxRow = Record<string, number | null>;
export type WxSeries = { run: string; times: Date[]; rows: WxRow[] };

export function decodeStation(file: StationWx, id: string): WxSeries | null {
  const s = file.stations[id];
  if (!s || !file.start) return null;
  const t0 = Date.parse(file.start.replace(/Z$/, ":00Z"));
  const times = Array.from({ length: file.n }, (_, k) => new Date(t0 + k * file.step_h * 3600000));
  const rows = times.map((_, k) => Object.fromEntries(file.fields.map((f) => {
    const v = s[f]?.[k];
    return [f, v == null ? null : v / file.scale[f]];
  })));
  return { run: file.run, times, rows };
}

export async function loadWeather(base: string, cc: string, region: string, id: string): Promise<WxSeries | null> {
  try {
    const latest = await fetch(`${base}/latest.json`);
    if (!latest.ok) return null;
    const { dir } = (await latest.json()) as { dir: string };
    const res = await fetch(`${base}/${dir}/stations/${cc}/${region || "_"}.json`);
    if (!res.ok) return null;
    return decodeStation((await res.json()) as StationWx, id);
  } catch {
    return null;
  }
}
