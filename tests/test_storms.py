import numpy as np

from pipeline.storms import frame_s, storm_index

SHAPE = (384, 768)


def full(v):
    return np.full(SHAPE, v, np.float32)


def test_no_cape_no_storm():
    assert (storm_index(full(0), full(10), full(-5)) == 0).all()


def test_no_rain_no_storm():
    assert (storm_index(full(2000), full(0), full(-5)) == 0).all()


def test_stable_air_no_storm():
    assert (storm_index(full(2000), full(10), full(2)) == 0).all()


def test_index_grows_with_cape_and_rain():
    a = storm_index(full(500), full(3), full(-3))[0, 0]
    b = storm_index(full(1500), full(3), full(-3))[0, 0]
    c = storm_index(full(1500), full(1), full(-3))[0, 0]
    assert 0 < a < b and 0 < c < b
    assert np.isclose(a, 0.1 * 500 ** 0.75)


def test_index_clips_at_255_and_missing_is_zero():
    assert storm_index(full(1e6), full(10), full(-5))[0, 0] == 255
    f = frame_s(storm_index(full(np.nan), full(np.nan), full(np.nan)))
    assert f.dtype == np.uint8 and (f == 0).all()
