"""Configuration model for ANVESHA.

Every tunable parameter of the simulation, perception, estimation, search and
control chain lives here, with the SIH26169 reference values as defaults.
Configurations are plain dataclasses so they can be serialised into every log
and report (reproducibility), loaded from YAML scenario files and validated
before a run starts.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# --------------------------------------------------------------------------- #
# Section dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class ScreenCfg:
    width_px: int = 2000            # PS #1: min 2000 x 2000
    height_px: int = 2000
    background: str = "dark_sky"    # dark_sky | uniform | starfield | clutter
    background_level: float = 12.0  # mean DN of the background (8-bit scale)
    n_stars: int = 60               # only for starfield
    n_distractors: int = 0          # static bright distractor spots (beacon look-alikes)
    distractor_level: float = 140.0


@dataclass
class CameraCfg:
    width_px: int = 640             # PS #3
    height_px: int = 480
    fov_x_deg: float = 4.0          # PS #4 default 4 x 3 deg
    fov_y_deg: float = 3.0
    rate_hz: float = 30.0           # PS #5: >= 30 Hz
    monochrome: bool = True         # PS #2
    psf_sigma_px: float = 0.8       # optical blur (diffraction + defocus), sensor pixels
    bit_depth: int = 8
    # adaptive FOV (zoom). PS allows a user-defined FOV; zoom levels are
    # multiples of the base FOV. [1.0] disables zoom.
    zoom_levels: List[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])
    zoom_change_s: float = 0.15     # time for a zoom change (lens settle)


@dataclass
class GimbalCfg:
    max_pan_rate_dps: float = 5.0   # PS #13 (5-10 deg/s, default 5)
    max_tilt_rate_dps: float = 5.0  # PS #14
    max_accel_dps2: float = 40.0    # actuator acceleration limit
    rate_loop_tau_s: float = 0.04   # first-order rate-loop lag
    actuator_latency_s: float = 0.010
    pan_limit_deg: float = 30.0     # mechanical travel (+/-)
    tilt_limit_deg: float = 30.0
    start_centered: bool = True     # PS #6: initial camera position = screen centre


@dataclass
class TargetCfg:
    shape: str = "square"           # square | circle | gaussian   (PS #9)
    size_px: float = 10.0           # PS #10: 5-20 px, default 10 (screen px at base FOV)
    peak_level: float = 220.0       # DN above background, clear conditions
    trajectory: str = "circular"    # straight | circular | figure8 | random | spiral | sinusoidal | user
    speed_px_s: float = 120.0       # characteristic speed on the screen
    initial: str = "random"         # random | center | [x, y]
    initial_xy: Optional[List[float]] = None
    radius_px: float = 350.0        # circular / figure8 / spiral scale
    period_s: float = 20.0
    user_waypoints: Optional[List[List[float]]] = None
    blink_hz: float = 0.0           # optional beacon modulation (0 = steady)
    occlusions: List[List[float]] = field(default_factory=list)  # [[t_start, t_end], ...]
    n_targets: int = 1              # PS #8 (1 mandatory, multiple optional)


@dataclass
class PlatformCfg:
    motion: str = "none"            # none | linear | circular | random | spiral | figure8 | vibration
    amplitude_px_per_frame: float = 0.0   # PS disturbances #5: up to +/-20 px/frame
    period_s: float = 8.0
    vibration_hz: List[float] = field(default_factory=lambda: [7.0, 13.0])
    imu_available: bool = True      # real terminals carry an IMU/INS; used for feed-forward
    imu_noise_dps: float = 0.02
    imu_bias_dps: float = 0.01


@dataclass
class NoiseCfg:
    gaussian: bool = True           # sensor read noise is always present on a real FPA
    gaussian_sigma: float = 2.0     # DN; PS max std 20
    poisson: bool = False
    poisson_scale: float = 1.0      # photons per DN (lower = noisier)
    salt_pepper: bool = False
    salt_pepper_frac: float = 0.10  # PS: ~10 % of image
    jitter_px: float = 0.0          # PS: max +/-20 px/frame camera jitter
    jitter_mode: str = "uniform"    # uniform | gaussian | sinusoidal


@dataclass
class AtmosphereCfg:
    condition: str = "clear"        # clear | haze | fog | rain | low_light
    severity: float = 0.5           # 0..1 scales contrast/brightness loss
    turbulence: float = 0.0         # 0..1 scintillation + beam-wander strength


@dataclass
class PerceptionCfg:
    detector: str = "mf_cfar"       # threshold | blob | cnn | mf_cfar | fusion
    cfar_k: float = 6.0             # detection threshold in noise sigmas
    centroid: str = "iwcog"         # cog | iwcog | gauss_fit
    roi_scale: float = 6.0          # ROI half-size in beacon sizes while tracking
    use_cnn_verifier: bool = True
    latency_s: float = 0.0          # extra modelled processing latency


@dataclass
class EstimatorCfg:
    kind: str = "imm"               # none | kf_cv | imm
    q_cv: float = 800.0             # px/s^2 process noise (CV)
    q_ct: float = 300.0
    q_ca: float = 2000.0
    meas_sigma_px: float = 1.5
    adaptive_r: bool = True
    gate_chi2: float = 13.8         # 99.9 % for 2 dof
    coast_s: float = 0.6            # prediction-only period before declaring LOST


@dataclass
class SearchCfg:
    kind: str = "belief"            # spiral | raster | belief
    cell_px: int = 25
    allow_zoom: bool = True
    target_speed_prior_px_s: float = 250.0
    dwell_frames: int = 2
    reject_static: bool = True      # PS target is a *moving* beacon: a lock that stays static > static_s is treated as a look-alike
    static_s: float = 0.8
    static_speed_px_s: float = 8.0
    static_disp_px: float = 12.0
    static_revisit_s: float = 0.4   # a detection seen again at the same world position after this long is static    # max world-frame displacement over static_s for a "static" lock


@dataclass
class ControlCfg:
    kind: str = "predictive"        # pid | predictive
    kp: float = 6.0                 # 1/s (loop crossover; ~40 deg phase margin with modelled lags)
    ki: float = 0.0
    kd: float = 0.15
    feedforward: bool = True        # target-rate feed-forward from the estimator
    imu_feedforward: bool = True    # platform-rate feed-forward from the IMU
    latency_comp: bool = True
    rate_hz: float = 60.0           # PS #15 control update >= 20 Hz


@dataclass
class RunCfg:
    duration_s: float = 20.0
    seed: int = 1
    sim_rate_hz: float = 240.0
    pipeline: str = "anvesha"       # baseline_a | baseline_b | baseline_c | anvesha
    realtime: bool = False
    lock_px: float = 10.0           # PS #17 tracking-error criterion
    record_frames: bool = False


@dataclass
class Config:
    name: str = "default"
    description: str = ""
    screen: ScreenCfg = field(default_factory=ScreenCfg)
    camera: CameraCfg = field(default_factory=CameraCfg)
    gimbal: GimbalCfg = field(default_factory=GimbalCfg)
    target: TargetCfg = field(default_factory=TargetCfg)
    platform: PlatformCfg = field(default_factory=PlatformCfg)
    noise: NoiseCfg = field(default_factory=NoiseCfg)
    atmosphere: AtmosphereCfg = field(default_factory=AtmosphereCfg)
    perception: PerceptionCfg = field(default_factory=PerceptionCfg)
    estimator: EstimatorCfg = field(default_factory=EstimatorCfg)
    search: SearchCfg = field(default_factory=SearchCfg)
    control: ControlCfg = field(default_factory=ControlCfg)
    run: RunCfg = field(default_factory=RunCfg)

    # ------------------------------------------------------------------ #
    @property
    def deg_per_px(self) -> float:
        """Angular size of one *screen* pixel = one camera pixel at base zoom."""
        return self.camera.fov_x_deg / self.camera.width_px

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def copy(self) -> "Config":
        return copy.deepcopy(self)


# --------------------------------------------------------------------------- #
# Loading / merging / validation
# --------------------------------------------------------------------------- #
def _merge_into(dc: Any, data: Dict[str, Any], path: str = "") -> None:
    for k, v in (data or {}).items():
        if not hasattr(dc, k):
            raise ValueError(f"Unknown configuration key '{path}{k}'")
        cur = getattr(dc, k)
        if dataclasses.is_dataclass(cur) and isinstance(v, dict):
            _merge_into(cur, v, f"{path}{k}.")
        else:
            setattr(dc, k, v)


def from_dict(data: Dict[str, Any], base: Optional[Config] = None) -> Config:
    cfg = (base or Config()).copy()
    _merge_into(cfg, data)
    validate(cfg)
    return cfg


def load(path: str | Path, base: Optional[Config] = None) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return from_dict(data, base)


def set_dotted(cfg: Config, dotted: str, value: Any) -> None:
    obj = cfg
    parts = dotted.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    if not hasattr(obj, parts[-1]):
        raise ValueError(f"Unknown key {dotted}")
    cur = getattr(obj, parts[-1])
    if isinstance(cur, bool):
        value = str(value).lower() in ("1", "true", "yes", "on")
    elif isinstance(cur, int) and not isinstance(cur, bool):
        value = int(float(value))
    elif isinstance(cur, float):
        value = float(value)
    setattr(obj, parts[-1], value)


class ConfigError(ValueError):
    pass


def validate(cfg: Config) -> None:
    """Reject physically meaningless or out-of-spec configurations early."""
    errs = []
    s, c, g, t, n = cfg.screen, cfg.camera, cfg.gimbal, cfg.target, cfg.noise
    if s.width_px < c.width_px or s.height_px < c.height_px:
        errs.append("screen must be larger than the camera frame")
    if not (0.1 <= c.fov_x_deg <= 60 and 0.1 <= c.fov_y_deg <= 60):
        errs.append("camera FOV out of range (0.1..60 deg)")
    if c.rate_hz < 1:
        errs.append("camera rate must be >= 1 Hz")
    if not (0.1 <= g.max_pan_rate_dps <= 100 and 0.1 <= g.max_tilt_rate_dps <= 100):
        errs.append("gimbal rate limits out of range")
    if not (1 <= t.size_px <= 100):
        errs.append("target size out of range (1..100 px)")
    valid_traj = {"straight", "circular", "figure8", "random", "spiral", "sinusoidal", "user", "static"}
    if t.trajectory not in valid_traj:
        errs.append(f"trajectory must be one of {sorted(valid_traj)}")
    if not (0 <= n.salt_pepper_frac <= 0.5):
        errs.append("salt & pepper fraction must be 0..0.5")
    if not (0 <= n.gaussian_sigma <= 60):
        errs.append("gaussian sigma must be 0..60 DN")
    if not (0 <= n.jitter_px <= 60):
        errs.append("jitter must be 0..60 px/frame")
    if cfg.atmosphere.condition not in {"clear", "haze", "fog", "rain", "low_light"}:
        errs.append("atmosphere.condition invalid")
    if not (0 <= cfg.atmosphere.severity <= 1):
        errs.append("atmosphere.severity must be 0..1")
    if cfg.control.rate_hz < 20:
        errs.append("control rate must be >= 20 Hz (PS #15)")
    if cfg.run.sim_rate_hz < cfg.camera.rate_hz or cfg.run.sim_rate_hz < cfg.control.rate_hz:
        errs.append("simulation rate must be >= camera and control rates")
    if cfg.run.pipeline not in {"baseline_a", "baseline_b", "baseline_c", "anvesha"}:
        errs.append("run.pipeline invalid")
    if errs:
        raise ConfigError("; ".join(errs))


PIPELINE_PRESETS: Dict[str, Dict[str, Any]] = {
    # Baseline A: global threshold + centre-of-gravity + PID, spiral search, no estimator
    "baseline_a": {
        "perception": {"detector": "threshold", "centroid": "cog", "use_cnn_verifier": False},
        "estimator": {"kind": "none"},
        "search": {"kind": "spiral", "allow_zoom": False},
        "control": {"kind": "pid", "kp": 12.0, "ki": 20.0, "kd": 0.05, "feedforward": False, "imu_feedforward": False, "latency_comp": False},
    },
    # Baseline B: blob detection + constant-velocity Kalman + PID, spiral search
    "baseline_b": {
        "perception": {"detector": "blob", "centroid": "cog", "use_cnn_verifier": False},
        "estimator": {"kind": "kf_cv", "adaptive_r": False},
        "search": {"kind": "spiral", "allow_zoom": False},
        "control": {"kind": "pid", "kp": 12.0, "ki": 20.0, "kd": 0.05, "feedforward": False, "imu_feedforward": False, "latency_comp": False},
    },
    # Baseline C: learned (CNN heat-map) detector + constant-velocity Kalman + PID, spiral search
    "baseline_c": {
        "perception": {"detector": "cnn", "centroid": "cog", "use_cnn_verifier": False},
        "estimator": {"kind": "kf_cv", "adaptive_r": False},
        "search": {"kind": "spiral", "allow_zoom": False},
        "control": {"kind": "pid", "kp": 12.0, "ki": 20.0, "kd": 0.05, "feedforward": False, "imu_feedforward": False, "latency_comp": False},
    },
    # Candidate: ANVESHA belief-driven coarse PAT
    "anvesha": {
        "perception": {"detector": "fusion", "centroid": "iwcog", "use_cnn_verifier": True},
        "estimator": {"kind": "imm", "adaptive_r": True},
        "search": {"kind": "belief"},
        "control": {"kind": "predictive", "feedforward": True, "imu_feedforward": True, "latency_comp": True},
    },
}


def apply_pipeline(cfg: Config, pipeline: str) -> Config:
    out = from_dict(PIPELINE_PRESETS[pipeline], cfg)
    out.run.pipeline = pipeline
    return out
