import numpy as np
import pytest
from PIL import Image, ImageDraw

from dashcamutils import autofit

W, H = 1280, 720
HOOD_TOP = 560


def _scene(rng: np.random.Generator, tilt: float = 0.0) -> Image.Image:
    img = Image.new("L", (W * 2, H * 2), 150)
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x = int(rng.integers(0, W * 2))
        d.rectangle(
            (x, 0, x + int(rng.integers(8, 60)), H * 2), fill=int(rng.integers(20, 230))
        )
    img = img.resize((W, H), Image.Resampling.LANCZOS)
    return img.rotate(tilt, resample=Image.Resampling.BICUBIC, fillcolor=150)


def _sequence(tmp_path, tilt: float = 0.0, n: int = 10, hood: bool = False):
    rng = np.random.default_rng(3)
    yy = np.arange(H)[:, None]
    xx = np.arange(W)[None, :]
    # a curved hood: highest in the middle
    mask = yy > HOOD_TOP + 0.0004 * (xx - W / 2) ** 2
    paths = []
    for k in range(n):
        arr = np.asarray(_scene(rng, tilt)).copy()
        if hood:
            arr[mask] = 30
        p = tmp_path / f"f{k}.png"
        Image.fromarray(arr).save(p)
        paths.append(str(p))
    return paths


def test_hood_crop_found(tmp_path):
    crop = autofit.estimate_hood_crop(_sequence(tmp_path, hood=True))
    assert crop is not None
    assert H - HOOD_TOP <= crop <= H - HOOD_TOP + 15


def test_no_hood_means_no_crop(tmp_path):
    assert autofit.estimate_hood_crop(_sequence(tmp_path)) == 0


def test_static_scene_gives_no_answer(tmp_path):
    paths = _sequence(tmp_path, n=1) * 6
    assert autofit.estimate_hood_crop(paths) is None


def test_too_few_images(tmp_path):
    assert autofit.estimate_hood_crop(_sequence(tmp_path, n=2)) is None
    assert autofit.estimate_angle(_sequence(tmp_path, n=2)) is None


@pytest.mark.parametrize("tilt", [0.0, 1.5, -2.0, 3.0])
def test_angle_corrects_tilt(tmp_path, tilt):
    angle = autofit.estimate_angle(_sequence(tmp_path, tilt=tilt))
    assert angle is not None
    assert angle == pytest.approx(-tilt, abs=0.3)


def test_fit_keeps_explicit_values_and_falls_back(tmp_path):
    assert autofit.fit([], 120, 1.5) == (120, 1.5)
    assert autofit.fit([], None, None) == (0, 0.0)
