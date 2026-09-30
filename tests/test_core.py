"""Fast unit / integration tests:  python -m pytest -q tests"""
import numpy as np
import pytest

from anvesha import config as C
from anvesha.estimation.filters import Estimator
from anvesha.pat.engine import Engine
from anvesha.perception.detectors import Detector
from anvesha.search.belief import BeliefMap, DetectionModel
from anvesha.sim import trajectories as trj
from anvesha.sim.optics import render_spot


def test_config_validation_rejects_bad_values():
    cfg = C.Config()
    cfg.control.rate_hz = 10  # PS requires >= 20 Hz
    with pytest.raises(C.ConfigError):
        C.validate(cfg)


@pytest.mark.parametrize("kind", ["straight", "circular", "figure8", "random", "spiral", "sinusoidal", "user"])
def test_trajectories_stay_on_screen(kind):
    rng = np.random.default_rng(0)
    t = trj.make(kind, 2000, 2000, 200.0, rng, radius=350)
    for _ in range(240 * 20):
        t.step(1 / 240)
        assert -1 <= t.pos[0] <= 2001 and -1 <= t.pos[1] <= 2001


def test_subpixel_centroid_on_clean_spot():
    img = np.full((120, 120), 10.0, np.float32)
    render_spot(img, 60.37, 58.81, 10.0, 200.0, 0.8, "square")
    img += np.random.default_rng(1).normal(0, 2, img.shape).astype(np.float32)
    dets, _ = Detector("mf_cfar", 6.0, "iwcog").detect(np.clip(img, 0, 255).astype(np.uint8), 10.0)
    assert dets, "beacon not detected"
    assert abs(dets[0].u - 60.37) < 0.2 and abs(dets[0].v - 58.81) < 0.2


def test_salt_and_pepper_does_not_create_detections():
    rng = np.random.default_rng(2)
    img = np.full((240, 320), 20, np.uint8)
    m = rng.random(img.shape)
    img[m < 0.05] = 0
    img[m > 0.95] = 255
    dets, st = Detector("mf_cfar", 6.0, "iwcog").detect(img, 10.0)
    assert st.sp_frac > 0.05 and len([d for d in dets if d.score > 0.35]) == 0


def test_imm_converges_on_constant_velocity():
    est = Estimator("imm", 800, 300, 2000, 1.0, True)
    est.init(np.array([0.0, 0.0]), 0.0)
    rng = np.random.default_rng(3)
    for k in range(1, 90):
        t = k / 30
        est.predict_to(t, np.zeros(2))
        est.update(np.array([100 * t, -50 * t]) + rng.normal(0, 1, 2))
    assert np.allclose(est.x[2:4], [100, -50], atol=10)


def test_negative_information_moves_belief_out_of_footprint():
    bm = BeliefMap(2000, 2000, 25, 200)
    dm = DetectionModel(6.0, 10.0, 220.0)
    before = bm.mass_in(np.array([1000.0, 1000.0]), np.array([320.0, 240.0])).sum()
    bm.miss_update(np.array([1000.0, 1000.0]), np.array([320.0, 240.0]), dm.pd_vec(1.0))
    after = bm.mass_in(np.array([1000.0, 1000.0]), np.array([320.0, 240.0])).sum()
    assert after < 0.5 * before


def test_runs_are_bit_reproducible():
    def run():
        cfg = C.apply_pipeline(C.Config(), "anvesha")
        cfg.run.duration_s = 3
        cfg.noise.salt_pepper = True
        e = Engine(cfg)
        e.run()
        A = e.metrics.arrays()
        return A["tgt_x"], A["err_los_px"]
    a, b = run(), run()
    assert np.array_equal(a[0], b[0]) and np.allclose(a[1], b[1], equal_nan=True)


def test_end_to_end_clean_meets_ps_checks():
    cfg = C.apply_pipeline(C.Config(), "anvesha")
    cfg.run.duration_s = 8
    s = Engine(cfg).run()
    assert s["acquired"] and s["acquisition_time_s"] <= 2.0
    assert s["tracking_error_los_px"]["mean"] <= 10.0
    assert s["fps_loop"] >= 20.0
