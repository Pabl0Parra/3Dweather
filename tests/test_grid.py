from pipeline.grid import GLOBE


def test_grid_axes():
    assert (GLOBE.w, GLOBE.h) == (768, 384)
    assert GLOBE.lons()[0] == -179.82422 and abs(GLOBE.lons()[-1] - 179.70703) < 1e-4
    assert GLOBE.lats()[0] == 89.7364 and abs(GLOBE.lats()[-1] - (-89.736251)) < 1e-4


def test_cell_of_reference_peak():
    assert GLOBE.cell_of(44.25, -141.0) == (97, 83)  # native max of the reference run
    assert abs(GLOBE.lats()[97] - 44.28) < 0.01 and abs(GLOBE.lons()[83] - (-140.92)) < 0.01


def test_cell_of_wraps_longitude():
    assert GLOBE.cell_of(0.0, 179.95)[1] == 0
