"""Train BeaconNet (small fully-convolutional beacon heat-map network) on
physics-informed synthetic patches and export it to ONNX.

Data: every patch is rendered with the *same* optics and disturbance models the
simulator uses (anvesha.sim.optics / disturbances): box beacon (2-20 px) with
PSF, haze/fog veil + blur, rain streaks, low-light gain, stars, Poisson,
Gaussian (sigma 0-20) and salt & pepper (0-15 %) noise. 50 % of patches contain
no beacon (only clutter) so the network learns to reject look-alikes.

Usage:  python tools/train_beaconnet.py --steps 3000 --out models/beaconnet.onnx
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anvesha.sim.optics import render_spot  # noqa: E402
from anvesha.perception.learned import normalise  # noqa: E402

P = 64


def make_patch(rng: np.random.Generator):
    img = np.full((P, P), rng.uniform(5, 40), np.float32)
    # smooth background structure
    small = rng.standard_normal((4, 4)).astype(np.float32) * rng.uniform(0, 10)
    img += cv2.resize(small, (P, P), interpolation=cv2.INTER_CUBIC)
    # stars (point-like distractors)
    for _ in range(rng.integers(0, 4)):
        render_spot(img, rng.uniform(0, P), rng.uniform(0, P), 1.0, float(rng.uniform(10, 120)), 0.8, "gaussian")
    has = rng.random() < 0.5
    size = float(np.exp(rng.uniform(np.log(2.5), np.log(20))))
    blur = float(rng.uniform(0.6, 2.5))
    u = v = -1.0
    amp_trans = 1.0
    cond = rng.choice(["clear", "haze", "fog", "rain", "low"])
    sev = rng.uniform(0, 1)
    if cond == "haze":
        amp_trans = 1 - 0.55 * sev
    elif cond == "fog":
        amp_trans = 1 - 0.8 * sev
        blur += 2.2 * sev
    if has:
        u, v = rng.uniform(8, P - 8), rng.uniform(8, P - 8)
        peak = float(rng.uniform(25, 230)) * amp_trans
        render_spot(img, u, v, size, peak, blur, "square" if rng.random() < 0.8 else "circle")
    if cond in ("haze", "fog"):
        img = img * (0.3 + 0.7 * amp_trans) + (90 if cond == "fog" else 45) * sev
    if cond == "rain":
        for _ in range(rng.integers(0, 6)):
            x, y = rng.uniform(0, P, 2)
            L = rng.uniform(8, 30)
            a = math.radians(100) + rng.normal(0, 0.1)
            cv2.line(img, (int(x), int(y)), (int(x + L * math.cos(a)), int(y + L * math.sin(a))),
                     float(rng.uniform(25, 90)), 1, cv2.LINE_AA)
    if cond == "low":
        img *= 1 - 0.85 * sev
    if rng.random() < 0.5:
        sc = rng.uniform(0.3, 3.0)
        img = rng.poisson(np.clip(img, 0, None) * sc).astype(np.float32) / sc
    img += rng.standard_normal(img.shape).astype(np.float32) * rng.uniform(0, 20)
    out = np.clip(img, 0, 255).astype(np.uint8)
    if rng.random() < 0.4:
        f = rng.uniform(0, 0.15)
        m = rng.random(out.shape)
        out[m < f / 2] = 0
        out[m > 1 - f / 2] = 255
    if (out == 0).mean() + (out == 255).mean() > 0.004:
        out = cv2.medianBlur(out, 3)
    x, _, _ = normalise(out)
    y = np.zeros((P, P), np.float32)
    if has:
        yy, xx = np.mgrid[0:P, 0:P]
        s = max(1.2, min(size / 4.0, 3.0))
        y = np.exp(-0.5 * ((xx - u) ** 2 + (yy - v) ** 2) / s ** 2).astype(np.float32)
    return x, y, has, (u, v), size


def build_model():
    import torch.nn as nn

    class BeaconNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.f = nn.Sequential(
                nn.Conv2d(1, 8, 3, padding=1), nn.ReLU(),
                nn.Conv2d(8, 12, 3, padding=2, dilation=2), nn.ReLU(),
                nn.Conv2d(12, 16, 3, padding=2, dilation=2), nn.ReLU(),
                nn.Conv2d(16, 16, 3, padding=4, dilation=4), nn.ReLU(),
                nn.Conv2d(16, 12, 3, padding=1), nn.ReLU(),
                nn.Conv2d(12, 1, 1), nn.Sigmoid())

        def forward(self, x):
            return self.f(x)
    return BeaconNet()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "models" / "beaconnet.onnx"))
    ap.add_argument("--device", default="auto", help="auto | cuda | cpu (auto uses the GPU when CUDA is available)")
    a = ap.parse_args()
    import torch
    torch.manual_seed(a.seed)
    torch.set_num_threads(2)
    rng = np.random.default_rng(a.seed)
    dev = torch.device("cuda" if (a.device == "auto" and torch.cuda.is_available()) or a.device == "cuda" else "cpu")
    print("training on", dev, torch.cuda.get_device_name(0) if dev.type == "cuda" else "", flush=True)
    net = build_model().to(dev)
    opt = torch.optim.Adam(net.parameters(), 2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.steps)
    nparam = sum(p.numel() for p in net.parameters())
    t0 = time.time()
    for step in range(a.steps):
        xs, ys = zip(*[make_patch(rng)[:2] for _ in range(a.batch)])
        x = torch.from_numpy(np.stack(xs)[:, None]).to(dev)
        y = torch.from_numpy(np.stack(ys)[:, None]).to(dev)
        p = net(x).clamp(1e-5, 1 - 1e-5)
        # focal-style weighted BCE (positives are rare)
        w = 1 + 30 * y
        loss = -(w * (y * torch.log(p) * (1 - p) ** 2 + (1 - y) * torch.log(1 - p) * p ** 2)).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if step % 250 == 0:
            print(f"step {step:5d} loss {loss.item():.4f}  {time.time() - t0:.0f}s", flush=True)
    net.eval()
    net = net.to(dev)
    # held-out evaluation on fresh seeded patches: presence detection + localisation
    rng_e = np.random.default_rng(12345)
    tp = fp = fn = tn = 0
    errs = []
    with torch.no_grad():
        for _ in range(2000):
            x, y, has, (u, v), size = make_patch(rng_e)
            hm = net(torch.from_numpy(x[None, None]).to(dev))[0, 0].cpu().numpy()
            m = float(hm.max())
            det = m > 0.5
            if has and det:
                tp += 1
                iy, ix = np.unravel_index(int(np.argmax(hm)), hm.shape)
                errs.append(math.hypot(ix - u, iy - v))
            elif has:
                fn += 1
            elif det:
                fp += 1
            else:
                tn += 1
    ev = {"params": int(nparam), "steps": a.steps, "heldout_patches": 2000, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
          "recall": tp / max(tp + fn, 1), "false_positive_rate": fp / max(fp + tn, 1),
          "peak_loc_error_px_median": float(np.median(errs)) if errs else None,
          "note": "held-out synthetic patches from the same generator (in-distribution); not a real-camera evaluation"}
    print(json.dumps(ev, indent=1))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    net = net.cpu()
    dummy = torch.zeros(1, 1, 64, 64)
    torch.onnx.export(net, dummy, str(out), input_names=["x"], output_names=["hm"], opset_version=17,
                      dynamic_axes={"x": {0: "n", 2: "h", 3: "w"}, "hm": {0: "n", 2: "h", 3: "w"}}, dynamo=False)
    (out.parent / "beaconnet_eval.json").write_text(json.dumps(ev, indent=1))
    print("saved", out)


if __name__ == "__main__":
    main()
