// Display units, stored per browser. Storage may be blocked; everything still works.
import { LEGEND_TICKS } from "./ramp";

export type Units = { length: "m" | "ft"; speed: "kn" | "kmh" | "ms" | "mph"; temp: "C" | "F" };
export const DEFAULT_UNITS: Units = { length: "m", speed: "kn", temp: "C" };

const KEY = "3dw.units";
const FT_PER_M = 3.28084;
const OPTIONS: { [K in keyof Units]: { value: Units[K]; label: string }[] } = {
  length: [{ value: "m", label: "m" }, { value: "ft", label: "ft" }],
  speed: [
    { value: "kn", label: "kn" }, { value: "kmh", label: "km/h" }, { value: "ms", label: "m/s" }, { value: "mph", label: "mph" },
  ],
  temp: [{ value: "C", label: "°C" }, { value: "F", label: "°F" }],
};
const GROUP_NAMES: Record<keyof Units, string> = { length: "Wave height", speed: "Wind speed", temp: "Temperature" };

export function formatLength(m: number, u: Units["length"]): string {
  return u === "ft" ? `${(m * FT_PER_M).toFixed(1)} ft` : `${m.toFixed(1)} m`;
}

export function formatSpeed(ms: number, u: Units["speed"], decimals = 0): string {
  const [k, label] = { kn: [1.943844, "kn"], kmh: [3.6, "km/h"], ms: [1, "m/s"], mph: [2.236936, "mph"] }[u] as [number, string];
  return `${decimals ? (ms * k).toFixed(decimals) : Math.round(ms * k)} ${label}`;
}

const MM_PER_IN = 25.4;

/** Rain rate: mm/h, or inches per hour alongside feet. */
export function formatRain(mmh: number, length: Units["length"]): string {
  return length === "ft" ? `${(mmh / MM_PER_IN).toFixed(2)} in/h` : `${mmh.toFixed(1)} mm/h`;
}

export function formatTemp(c: number, u: Units["temp"]): string {
  return u === "F" ? `${Math.round((c * 9) / 5 + 32)} °F` : `${Math.round(c)} °C`;
}

/** Legend ticks as [position in metres, label]; feet use round numbers. */
export function legendTicks(u: Units["length"]): [number, string][] {
  if (u === "ft") return [3, 10, 20, 30, 40].map((ft) => [ft / FT_PER_M, String(ft)]);
  return LEGEND_TICKS.map((m) => [m, String(m)]);
}

function defaultStore(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}

export function loadUnits(store: Storage | null = defaultStore()): Units {
  let raw: Partial<Record<keyof Units, unknown>> = {};
  try {
    const s = store?.getItem(KEY);
    if (s) raw = JSON.parse(s) ?? {};
  } catch { /* blocked or corrupt: defaults */ }
  const pick = <K extends keyof Units>(k: K): Units[K] =>
    OPTIONS[k].some((o) => o.value === raw[k]) ? (raw[k] as Units[K]) : DEFAULT_UNITS[k];
  return { length: pick("length"), speed: pick("speed"), temp: pick("temp") };
}

export function saveUnits(u: Units, store: Storage | null = defaultStore()): void {
  try { store?.setItem(KEY, JSON.stringify(u)); } catch { /* blocked: this session only */ }
}

/** Popover with one radio group per quantity. Returns the units in force now. */
export function mountUnitsMenu(button: HTMLButtonElement, onChange: (u: Units) => void): Units {
  let units = loadUnits();
  const panel = document.createElement("div");
  panel.className = "units-menu";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Units");
  panel.hidden = true;
  for (const key of Object.keys(OPTIONS) as (keyof Units)[]) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${GROUP_NAMES[key]}</legend>`;
    for (const o of OPTIONS[key]) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `units-${key}`;
      input.value = o.value;
      input.checked = units[key] === o.value;
      input.addEventListener("change", () => {
        units = { ...units, [key]: o.value };
        saveUnits(units);
        onChange(units);
      });
      label.append(input, ` ${o.label}`);
      fs.append(label);
    }
    panel.append(fs);
  }
  button.after(panel);
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");

  const open = (o: boolean) => {
    panel.hidden = !o;
    button.setAttribute("aria-expanded", String(o));
    if (o) panel.querySelector<HTMLInputElement>("input:checked")?.focus();
  };
  button.addEventListener("click", () => open(panel.hidden));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !panel.hidden) { open(false); button.focus(); }
  });
  document.addEventListener("pointerdown", (e) => {
    const t = e.target as Node;
    if (!panel.hidden && !panel.contains(t) && !button.contains(t)) open(false);
  });
  return units;
}
