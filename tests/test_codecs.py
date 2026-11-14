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
