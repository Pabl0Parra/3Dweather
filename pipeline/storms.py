"""Thunderstorm index (sprite s): our own rule, tuned against the reference run.

The reference publishes no formula (spec §8). Scaled CAPE, gated by rain and by an
unstable lifted index, gave the best overlap with the captured frames (IoU 0.38 of
storm cells); the constants come from the grid search in tools/compare_reference_rules.py.
"""
from __future__ import annotations

import numpy as np

K = 0.1
POWER = 0.75
RAIN_FULL_MMH = 3.0


def storm_index(cape: np.ndarray, rain_mmh: np.ndarray, lifted_index: np.ndarray) -> np.ndarray:
    """0..255 per globe cell; missing inputs count as no storm."""
    cape = np.clip(np.nan_to_num(np.asarray(cape, np.float64)), 0, None)
    rain = np.nan_to_num(np.asarray(rain_mmh, np.float64))
    unstable = np.nan_to_num(np.asarray(lifted_index, np.float64), nan=1.0) < 0
    idx = np.clip(K * cape ** POWER, 0, 255) * np.clip(rain / RAIN_FULL_MMH, 0, 1) * unstable
    return idx.astype(np.float32)


def frame_s(index: np.ndarray) -> np.ndarray:
    r = np.clip(np.rint(np.nan_to_num(index)), 0, 255).astype(np.uint8)
    zero = np.zeros_like(r)
    return np.dstack([r, zero, zero])
