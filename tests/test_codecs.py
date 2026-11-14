import numpy as np

from pipeline.codecs import decode_wave_height, encode_vector, encode_wave_height, wave_vector


def test_height_reference_value():
    assert encode_wave_height(np.array([13.82]))[0] == 237  # reference frame max
    assert abs(decode_wave_height(np.array([237]))[0] - 13.82) < 0.01


def test_height_clips_and_handles_nan():
    out = encode_wave_height(np.array([-1.0, 0.0, 16.0, 40.0, np.nan]))
    assert out.tolist() == [0, 0, 255, 255, 0] and out.dtype == np.uint8


def test_height_roundtrip_within_one_byte():
    b = np.arange(256, dtype=np.uint8)
    assert (encode_wave_height(decode_wave_height(b)) == b).all()


def test_vector_points_where_waves_travel():
    vx, vy = wave_vector(np.array([270.0, 0.0]), np.array([10.0, 25.0]))  # from west; from north
    g, b = encode_vector(vx, vy)
    assert (g[0], b[0]) == (179, 128)  # travels east, length 0.4
    assert (g[1], b[1]) == (128, 1)  # travels south, length 1


def test_vector_clips_long_period_and_nan():
    vx, vy = wave_vector(np.array([180.0, np.nan]), np.array([60.0, 8.0]))
    g, b = encode_vector(vx, vy)
    assert (g[0], b[0]) == (128, 255) and (g[1], b[1]) == (128, 128)


# --- phase 3a: every other quantity ---
import pytest

from pipeline import codecs as C

RANGES = {
    "wind": (-50, 50), "gust": (0, 60), "rain": (0, 64), "air_temp": (-60, 50),
    "sea_temp": (-2, 34), "current": (-2.5, 2.5), "pressure": (940, 1060), "cloud": (0, 100),
}


@pytest.mark.parametrize("name", sorted(RANGES))
def test_round_trip_within_one_level(name):
    enc, dec = getattr(C, f"encode_{name}"), getattr(C, f"decode_{name}")
    lo, hi = RANGES[name]
    x = np.linspace(lo, hi, 2001)
    b = enc(x)
    assert b.dtype == np.uint8
    step = np.max(np.abs(np.diff(dec(np.arange(1, 256)))))  # largest gap between levels
    assert np.max(np.abs(dec(b) - x)) <= step + 1e-9


def test_missing_values_encode_as_none():
    nan = np.array([np.nan])
    assert C.encode_wind(nan)[0] == 128 and C.encode_current(nan)[0] == 128
    for name in ("gust", "rain", "air_temp", "sea_temp", "pressure", "cloud"):
        assert getattr(C, f"encode_{name}")(nan)[0] == 0, name


def test_out_of_range_clips():
    assert C.encode_pressure(np.array([930.0, 1070.0])).tolist() == [1, 255]
    assert C.encode_gust(np.array([70.0]))[0] == 255
    assert C.encode_air_temp(np.array([-70.0, 55.0])).tolist() == [0, 255]
    assert C.encode_wind(np.array([-80.0, 80.0])).tolist() == [1, 255]


def test_known_bytes():
    assert C.encode_wind(np.array([10.0, -5.0])).tolist() == [153, 115]
    assert abs(C.decode_pressure(np.array([1]))[0] - 940) < 1e-9
    assert np.isnan(C.decode_pressure(np.array([0]))[0])
