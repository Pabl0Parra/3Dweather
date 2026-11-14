import pytest

import pipeline.sprites


@pytest.fixture(autouse=True, scope="session")
def fast_webp():
    """Lossless WebP is byte-exact at any effort; the lowest keeps the suite quick."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline.sprites, "WEBP_METHOD", 0)
        yield
