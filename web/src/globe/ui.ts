// Wave-height legend built from the colour ramp.
import { RAMP_STOPS } from "./ramp";
import { legendTicks, type Units } from "./units";

const MAX_M = 16;
// Same square-root scale as the height encoding, so small waves get room.
const pos = (m: number) => Math.sqrt(m / MAX_M) * 100;

/** Draws the legend; call the returned function when the length unit changes. */
export function mountLegend(root: HTMLElement, length: Units["length"] = "m"): (length: Units["length"]) => void {
  root.classList.add("legend");
  const stops = RAMP_STOPS.map(([m, [r, g, b]]) => `rgb(${r},${g},${b}) ${pos(m).toFixed(1)}%`).join(", ");
  root.innerHTML = `
    <span class="lg-title">Wave height</span>
    <div class="lg-bar" style="background: linear-gradient(to right, ${stops})"></div>
    <div class="lg-ticks"></div>`;
  root.setAttribute("role", "img");
  const ticks = root.querySelector<HTMLDivElement>(".lg-ticks")!;
  const update = (unit: Units["length"]) => {
    const t = legendTicks(unit);
    ticks.innerHTML = t.map(([m, label]) => `<span style="left:${pos(m).toFixed(1)}%">${label}</span>`).join("") + `<span class="lg-unit">${unit}</span>`;
    root.setAttribute("aria-label", `Wave height colour scale, ${t.map(([, l]) => l).join(", ")} ${unit === "ft" ? "feet" : "metres"}`);
  };
  update(length);
  return update;
}
