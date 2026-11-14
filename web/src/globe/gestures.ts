// Pointer, wheel and keyboard control of the globe view.
import { clampView, rotateBy, unproject, type View } from "./view";

type Vec = { x: number; y: number };

export const WHEEL_HINT = "Click the map to zoom with the wheel";
/** Pointer travel (CSS px) below which a press counts as a tap. */
export const TAP_SLOP = 4;

/** One frame of drag inertia; null once it has died out. */
export function stepInertia(vel: Vec): Vec | null {
  const next = { x: vel.x * 0.92, y: vel.y * 0.92 };
  return Math.abs(next.x) < 0.01 && Math.abs(next.y) < 0.01 ? null : next;
}

export function zoomBy(v: View, factor: number): View {
  return clampView({ ...v, zoom: v.zoom * factor });
}

export function attachGestures(
  el: HTMLElement,
  get: () => View,
  set: (v: View) => void,
  size: () => { w: number; h: number },
  onTap?: (x: number, y: number) => void,
  onDrag?: () => void,
): () => void {
  const pointers = new Map<number, Vec>();
  // Tap detection: total path length since pointerdown, so out-and-back counts as a drag.
  let travel = 0;
  let multi = false;
  let downAt: Vec = { x: 0, y: 0 };
  let vel: Vec = { x: 0, y: 0 };
  let lastMove = 0;
  let inertiaId = 0;
  let pinchDist = 0;
  let wheelArmed = false;
  let hintTimer = 0;

  const hint = document.createElement("p");
  hint.className = "globe-hint";
  hint.textContent = WHEEL_HINT;
  hint.hidden = true;
  el.append(hint);
  if (!el.hasAttribute("tabindex")) el.tabIndex = 0;

  const stopInertia = () => { cancelAnimationFrame(inertiaId); inertiaId = 0; };
  const rotate = (dx: number, dy: number) => {
    const { w, h } = size();
    set(rotateBy(get(), dx, dy, w, h));
  };
  const local = (e: { clientX: number; clientY: number }): Vec => {
    const r = el.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const spread = () => {
    const [a, b] = [...pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  const onDown = (e: PointerEvent) => {
    wheelArmed = true;
    stopInertia();
    el.setPointerCapture?.(e.pointerId);
    pointers.set(e.pointerId, local(e));
    vel = { x: 0, y: 0 };
    if (pointers.size === 1) { travel = 0; multi = false; downAt = local(e); }
    if (pointers.size === 2) { pinchDist = spread(); multi = true; }
  };

  const onMove = (e: PointerEvent) => {
    const prev = pointers.get(e.pointerId);
    if (!prev) return;
    const p = local(e);
    pointers.set(e.pointerId, p);
    if (pointers.size === 2) {
      const d = spread();
      if (pinchDist > 0) set(zoomBy(get(), d / pinchDist));
      pinchDist = d;
      return;
    }
    const dx = p.x - prev.x, dy = p.y - prev.y;
    const before = travel;
    travel += Math.hypot(dx, dy);
    if (before < TAP_SLOP && travel >= TAP_SLOP) onDrag?.();
    rotate(dx, dy);
    const now = performance.now();
    const dt = Math.max(1, now - lastMove);
    lastMove = now;
    // Velocity in px per 60 Hz frame, smoothed.
    vel = { x: vel.x * 0.5 + (dx * 16.7 / dt) * 0.5, y: vel.y * 0.5 + (dy * 16.7 / dt) * 0.5 };
  };

  const onUp = (e: PointerEvent) => {
    if (!pointers.delete(e.pointerId)) return;
    if (pointers.size > 0) { pinchDist = 0; return; }
    if (e.type === "pointerup" && !multi && travel < TAP_SLOP) { onTap?.(downAt.x, downAt.y); return; }
    if (performance.now() - lastMove > 80) return; // released after holding still
    const tick = () => {
      const next = stepInertia(vel);
      if (!next) { inertiaId = 0; return; }
      vel = next;
      rotate(vel.x, vel.y);
      inertiaId = requestAnimationFrame(tick);
    };
    inertiaId = requestAnimationFrame(tick);
  };

  const onDblClick = (e: MouseEvent) => {
    const { w, h } = size();
    const p = local(e);
    const v = get();
    const at = unproject(v, w, h, p.x, p.y);
    set(clampView({ lat0: at?.lat ?? v.lat0, lon0: at?.lon ?? v.lon0, zoom: v.zoom * 2 }));
  };

  const onWheel = (e: WheelEvent) => {
    if (!wheelArmed) {
      hint.hidden = false;
      clearTimeout(hintTimer);
      hintTimer = window.setTimeout(() => { hint.hidden = true; }, 1500);
      return; // let the page scroll
    }
    e.preventDefault();
    set(zoomBy(get(), Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015))));
  };

  const onKey = (e: KeyboardEvent) => {
    const v = get();
    const step: Record<string, () => View> = {
      ArrowLeft: () => clampView({ ...v, lon0: v.lon0 - 5 }),
      ArrowRight: () => clampView({ ...v, lon0: v.lon0 + 5 }),
      ArrowUp: () => clampView({ ...v, lat0: v.lat0 + 5 }),
      ArrowDown: () => clampView({ ...v, lat0: v.lat0 - 5 }),
      "+": () => zoomBy(v, 1.25),
      "=": () => zoomBy(v, 1.25),
      "-": () => zoomBy(v, 0.8),
    };
    const f = step[e.key];
    if (!f) return;
    e.preventDefault();
    stopInertia();
    set(f());
  };

  const onDocDown = (e: PointerEvent) => { if (!el.contains(e.target as Node)) wheelArmed = false; };

  el.addEventListener("pointerdown", onDown);
  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerup", onUp);
  el.addEventListener("pointercancel", onUp);
  el.addEventListener("dblclick", onDblClick);
  el.addEventListener("wheel", onWheel, { passive: false });
  el.addEventListener("keydown", onKey);
  document.addEventListener("pointerdown", onDocDown);

  return () => {
    stopInertia();
    clearTimeout(hintTimer);
    el.removeEventListener("pointerdown", onDown);
    el.removeEventListener("pointermove", onMove);
    el.removeEventListener("pointerup", onUp);
    el.removeEventListener("pointercancel", onUp);
    el.removeEventListener("dblclick", onDblClick);
    el.removeEventListener("wheel", onWheel);
    el.removeEventListener("keydown", onKey);
    document.removeEventListener("pointerdown", onDocDown);
    hint.remove();
  };
}
