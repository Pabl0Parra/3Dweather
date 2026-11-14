// Byte decodings of the wave sprite. Must match pipeline/codecs.py.

export const MAX_HEIGHT_M = 16;
export const MAX_PERIOD_S = 25;

/** R channel: square-root scale, 0-16 m. */
export function decodeHeight(b: number): number {
  return (b / 255) ** 2 * MAX_HEIGHT_M;
}

/** G/B channels: vector pointing where the waves travel (x east, y north), length = period / 25 s. */
export function decodeWave(g: number, b: number): { periodS: number; fromDeg: number } {
  const vx = (g - 128) / 127;
  const vy = (b - 128) / 127;
  const travel = (Math.atan2(vx, vy) * 180) / Math.PI;
  return { periodS: Math.hypot(vx, vy) * MAX_PERIOD_S, fromDeg: (((travel + 180) % 360) + 360) % 360 };
}
