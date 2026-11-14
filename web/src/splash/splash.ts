// Ignition: a 3 s opening that assembles the real globe and hands over to the live map.
// Motion runs one timeline for the DOM parts; its playhead is the progress the globe reads.
import { animate } from "motion";
import type { GlobeHandle } from "../globe/globe";
import { HOLD_S, INTRO_S, introAt, scramble } from "./intro";

const WORD = "3DWEATHER";
const TAGLINE = "Seven days of ocean, live.";
const CHROME = ".site-header, .controls, .credits";
const MAX_HOLD_MS = 6000; // with the 2.45 s run-up, the splash never lasts much over 8 s

function runLabel(run: string | undefined): string {
  if (!run) return "RUN ——";
  const m = run.match(/^(\d{4}-\d{2}-\d{2})T(\d{2})/);
  return m ? `RUN ${m[1]} ${m[2]}Z` : `RUN ${run}`;
}

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

export function playSplash(
  globe: GlobeHandle,
  opts: { reduced: boolean; dataReady: Promise<void> },
): Promise<void> {
  const html = document.documentElement;
  const chrome = [...document.querySelectorAll<HTMLElement>(CHROME)];
  const layer = document.createElement("div");
  layer.className = "splash";
  layer.setAttribute("aria-hidden", "true");

  return new Promise<void>((resolve) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      cancelAnimationFrame(raf);
      clearTimeout(holdTimer);
      tl?.cancel();
      ["pointerdown", "keydown", "wheel"].forEach((t) => window.removeEventListener(t, skip, true));
      globe.setIntro(null);
      html.classList.remove("splash-pending");
      chrome.forEach((el) => { el.style.opacity = ""; el.style.transform = ""; });
      layer.remove();
      resolve();
    };
    let raf = 0;
    let holdTimer = 0;
    let tl: ReturnType<typeof animate> | null = null;
    // Input that skips the splash only skips it: it must not also reach the globe,
    // the timeline's Space key, or controls that are still invisible.
    const skip = (e: Event) => {
      e.stopPropagation();
      if (e.type === "keydown") e.preventDefault();
      if (e.type === "pointerdown") {
        const eat = (c: Event) => { c.stopPropagation(); c.preventDefault(); };
        window.addEventListener("click", eat, { capture: true, once: true });
        setTimeout(() => window.removeEventListener("click", eat, true), 600);
      }
      finish();
    };

    if (opts.reduced) {
      // Reduced motion: a short fade from black, no particles in flight.
      layer.classList.add("splash-fade");
      document.body.append(layer);
      globe.setIntro(null);
      html.classList.remove("splash-pending");
      tl = animate(layer, { opacity: [1, 0] }, { duration: 0.3, ease: "easeOut" });
      tl.then(finish);
      return;
    }

    layer.innerHTML = `
      <div class="sp-horizon"></div>
      <div class="sp-readouts"><p class="sp-run"></p><p class="sp-model"></p><p class="sp-cells"></p></div>
      <div class="sp-mark"><div class="sp-word"></div><div class="sp-tag">${TAGLINE}</div></div>`;
    document.body.append(layer);
    const $ = <T extends HTMLElement>(s: string) => layer.querySelector<T>(s)!;
    const horizon = $(".sp-horizon"), readouts = $(".sp-readouts"), mark = $(".sp-mark");
    const runEl = $(".sp-run"), modelEl = $(".sp-model"), cellsEl = $(".sp-cells"), wordEl = $(".sp-word"), tag = $(".sp-tag");
    globe.setIntro(introAt(0));

    tl = animate([
      [horizon, { scaleX: [0, 1], opacity: [0, 1] }, { duration: 0.3, at: 0, ease: "easeOut" }],
      [readouts, { opacity: [0, 1] }, { duration: 0.2, at: 0.3 }],
      [horizon, { opacity: [1, 0] }, { duration: 0.4, at: 0.9 }],
      [wordEl, { opacity: [0, 1] }, { duration: 0.2, at: 1.85 }],
      [tag, { opacity: [0, 1], y: [6, 0] }, { duration: 0.4, at: 2.1 }],
      [mark, { opacity: [1, 0], scale: [1, 1.06] }, { duration: 0.5, at: HOLD_S }],
      [readouts, { opacity: [1, 0] }, { duration: 0.4, at: HOLD_S }],
      [chrome, { opacity: [0, 1], y: [16, 0] }, { duration: INTRO_S - HOLD_S, at: HOLD_S, ease: "easeOut" }],
    ]);

    let ready = false, holding = false;
    opts.dataReady.then(
      () => { ready = true; if (holding) { holding = false; clearTimeout(holdTimer); tl!.play(); } },
      () => finish(), // the forecast failed: end on the globe, whose retry notice is showing
    );

    const rand = Math.random;
    const tick = () => {
      const t = tl!.time;
      if (t >= HOLD_S && !ready && !holding) {
        holding = true;
        tl!.pause();
        // A stalled connection may never succeed or fail: don't hold the page hostage.
        holdTimer = window.setTimeout(finish, MAX_HOLD_MS);
      }
      globe.setIntro(introAt(holding ? HOLD_S : t));
      const info = globe.info();
      const r = clamp01((t - 0.3) / 0.5);
      runEl.textContent = scramble(runLabel(info?.run), r, rand);
      modelEl.textContent = scramble("MODEL GFS-WAVE · OPEN-METEO", r, rand);
      const n = info?.cells ?? 0;
      const c = 1 - (1 - clamp01((t - 0.3) / 1.3)) ** 3;
      cellsEl.textContent = `CELLS ${Math.round(n * c).toLocaleString("en-US")}`;
      wordEl.textContent = scramble(WORD, clamp01((t - 1.85) / 0.5), rand);
      if (t >= INTRO_S - 1e-3 && !holding) { finish(); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    tl.then(() => { if (!holding) finish(); });
    ["pointerdown", "keydown", "wheel"].forEach((t) => window.addEventListener(t, skip, true));
  });
}
