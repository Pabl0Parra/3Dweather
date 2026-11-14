// Wave-height legend built from the colour ramp.
import { LEGEND_TICKS, RAMP_STOPS } from "./ramp";

const MAX_M = 16;
// Same square-root scale as the height encoding, so small waves get room.
const pos = (m: number) => Math.sqrt(m / MAX_M) * 100;

export function mountLegend(root: HTMLElement): void {
  root.classList.add("legend");
  const stops = RAMP_STOPS.map(([m, [r, g, b]]) => `rgb(${r},${g},${b}) ${pos(m).toFixed(1)}%`).join(", ");
  root.innerHTML = `
    <span class="lg-title">Wave height</span>
    <div class="lg-bar" style="background: linear-gradient(to right, ${stops})"></div>
    <div class="lg-ticks">${LEGEND_TICKS.map((m) => `<span style="left:${pos(m).toFixed(1)}%">${m}</span>`).join("")}<span class="lg-unit">m</span></div>`;
  root.setAttribute("role", "img");
  root.setAttribute("aria-label", `Wave height colour scale, ${LEGEND_TICKS.join(", ")} metres`);
}
