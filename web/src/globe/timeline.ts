// Forecast timeline: hour maths, labels and the slider/play controls.

export const SPEEDS = [0.5, 1, 2];
export const HOURS_PER_SECOND = 1.5;
const LESS_CERTAIN_AFTER_H = 120;
const H = 3_600_000;

/** Hours since the run, clamped to the forecast window. */
export function initialHour(runIso: string, now: Date, hours: number): number {
  const h = (now.getTime() - Date.parse(runIso)) / H;
  return Math.max(0, Math.min(hours, h));
}

/** Step playback forward, wrapping to 0 after the last hour. */
export function advance(hour: number, dtSeconds: number, speed: number, hours: number): number {
  const next = hour + dtSeconds * HOURS_PER_SECOND * speed;
  return next >= hours ? 0 : next;
}

function clock(t: Date, timeZone?: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone,
  }).formatToParts(t);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("weekday")} ${get("day")} ${get("month")}, ${get("hour")}:${get("minute")}`;
}

function relative(deltaH: number): string {
  if (Math.abs(deltaH) <= 0.5) return "now";
  const a = Math.abs(deltaH);
  const span = a < 48 ? `${Math.round(a)} h` : `${Math.round(a / 24)} days`;
  return deltaH > 0 ? `in ${span}` : `${span} ago`;
}

/** "Fri 13 Nov, 18:00 · in 12 h", with " · less certain" past hour 120. */
export function timeLabel(runIso: string, hour: number, now: Date, timeZone?: string): string {
  const t = new Date(Date.parse(runIso) + hour * H);
  let s = `${clock(t, timeZone)} · ${relative((t.getTime() - now.getTime()) / H)}`;
  if (hour > LESS_CERTAIN_AFTER_H) s += " · less certain";
  return s;
}

/** Hours (from the run) of each local midnight inside the window. */
function midnights(runIso: string, hours: number): number[] {
  const run = Date.parse(runIso);
  const d = new Date(run);
  d.setHours(24, 0, 0, 0);
  const out: number[] = [];
  for (; (d.getTime() - run) / H <= hours; d.setDate(d.getDate() + 1)) out.push((d.getTime() - run) / H);
  return out;
}

export type TimelineHandle = {
  setHour(h: number): void;
  setPlaying(p: boolean): void;
  /** Hold playback (e.g. off screen) without changing the play state. */
  setSuspended(s: boolean): void;
  playing(): boolean;
};

const SPEED_TEXT: Record<number, string> = { 0.5: "½×", 1: "1×", 2: "2×" };

export function mountTimeline(
  root: HTMLElement,
  opts: { hours: number; runIso: string; onHour: (h: number) => void },
): TimelineHandle {
  const { hours, runIso, onHour } = opts;
  root.classList.add("timeline");
  root.innerHTML = `
    <button type="button" class="tl-play" aria-label="Play"><span aria-hidden="true">▶</span></button>
    <div class="tl-track">
      <div class="tl-ticks" aria-hidden="true"></div>
      <input class="tl-slider" type="range" min="0" max="${hours}" step="0.05" value="0" aria-label="Forecast time" />
    </div>
    <button type="button" class="tl-speed" aria-label="Playback speed">1×</button>
    <output class="tl-label" aria-live="off"></output>`;
  const play = root.querySelector<HTMLButtonElement>(".tl-play")!;
  const slider = root.querySelector<HTMLInputElement>(".tl-slider")!;
  const speedBtn = root.querySelector<HTMLButtonElement>(".tl-speed")!;
  const label = root.querySelector<HTMLOutputElement>(".tl-label")!;
  const ticks = root.querySelector<HTMLDivElement>(".tl-ticks")!;

  for (const m of midnights(runIso, hours)) {
    const t = document.createElement("span");
    t.className = "tl-day";
    t.style.left = `${(m / hours) * 100}%`;
    t.textContent = new Intl.DateTimeFormat("en-GB", { weekday: "short" }).format(new Date(Date.parse(runIso) + m * H + H));
    ticks.append(t);
  }
  const nowH = (Date.now() - Date.parse(runIso)) / H;
  if (nowH >= 0 && nowH <= hours) {
    const n = document.createElement("span");
    n.className = "tl-now";
    n.style.left = `${(nowH / hours) * 100}%`;
    n.title = "Now";
    ticks.append(n);
  }

  let hour = 0;
  let speedIx = 1;
  let isPlaying = false;
  let suspended = false;
  let raf = 0;
  let last = 0;

  const show = (h: number) => {
    hour = h;
    slider.value = String(h);
    label.textContent = timeLabel(runIso, h, new Date());
  };
  const emit = (h: number) => { show(h); onHour(h); };

  const tick = (t: number) => {
    const dt = last ? Math.min(0.25, (t - last) / 1000) : 0;
    last = t;
    emit(advance(hour, dt, SPEEDS[speedIx], hours));
    raf = requestAnimationFrame(tick);
  };

  const run = () => {
    cancelAnimationFrame(raf);
    last = 0;
    if (isPlaying && !suspended) raf = requestAnimationFrame(tick);
  };
  const setPlaying = (p: boolean) => {
    if (p === isPlaying) return;
    isPlaying = p;
    play.setAttribute("aria-label", p ? "Pause" : "Play");
    play.firstElementChild!.textContent = p ? "❚❚" : "▶";
    run();
  };
  const setSuspended = (s: boolean) => {
    if (s === suspended) return;
    suspended = s;
    run();
  };

  play.addEventListener("click", () => setPlaying(!isPlaying));
  speedBtn.addEventListener("click", () => {
    speedIx = (speedIx + 1) % SPEEDS.length;
    speedBtn.textContent = SPEED_TEXT[SPEEDS[speedIx]];
  });
  slider.addEventListener("input", () => emit(Number(slider.value)));
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || e.repeat) return;
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "BUTTON" || t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && t !== slider) || t.isContentEditable)) return;
    e.preventDefault();
    setPlaying(!isPlaying);
  });

  show(0);
  return { setHour: show, setPlaying, setSuspended, playing: () => isPlaying };
}
