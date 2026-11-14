// Byte decodings of the globe sprites. Must match pipeline/codecs.py.

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

/** Wind component, m/s: 128 = calm, +-127 steps = +-50 m/s. */
export const decodeWind = (b: number): number => ((b - 128) * 50) / 127;
export const decodeGust = (b: number): number => (b / 255) * 60;
export const decodeRain = (b: number): number => (b / 255) ** 2 * 64;
export const decodeAirTemp = (b: number): number => (b / 255) * 110 - 60;
export const decodeSeaTemp = (b: number): number => (b / 255) * 36 - 2;
export const decodeCurrent = (b: number): number => ((b - 128) / 127) * 2.5;
/** hPa; byte 0 means no value. */
export const decodePressure = (b: number): number | null => (b === 0 ? null : 940 + ((b - 1) / 254) * 120);
export const decodeCloud = (b: number): number => (b / 255) * 100;
