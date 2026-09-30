"""Evaluate an exported BeaconNet ONNX model on fresh held-out synthetic patches.

Usage:  python tools/eval_beaconnet.py [--model models/beaconnet.onnx] [--n 4000] [--out models/beaconnet_eval_onnx.json]
Reports ROC-AUC, recall/FPR at threshold 0.5 and at the 5 % false-positive operating point,
overall and on the 'detectable' subset (beacon peak >= 3x Gaussian noise sigma).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from train_beaconnet import make_patch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models" / "beaconnet.onnx"))
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import onnxruntime as ort
    sess = ort.InferenceSession(a.model, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(a.seed)
    S, L, R = [], [], []
    for _ in range(a.n):
        x, y, has, _, _, meta = make_patch(rng)
        hm = sess.run(None, {"x": x[None, None].astype(np.float32)})[0]
        S.append(float(hm.max())); L.append(int(has)); R.append(meta["snr"])
    S, L, R = np.array(S), np.array(L), np.array(R)
    pos, neg = S[L == 1], S[L == 0]
    auc = float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())
    th5 = float(np.quantile(neg, 0.95))
    det = R >= 3.0

    def at(th, mask=None):
        m = (L == 1) if mask is None else ((L == 1) & mask)
        return {"threshold": round(th, 3), "recall": float((S[m] > th).mean()), "false_positive_rate": float((neg > th).mean())}
    ev = {"model": Path(a.model).name, "heldout_patches": a.n, "seed": a.seed, "roc_auc": auc,
          "at_threshold_0.5": at(0.5), "at_fpr_5pct": at(th5),
          "detectable_subset": {"definition": "positives with beacon peak >= 3x Gaussian noise sigma", "n": int(det[L == 1].sum()),
                                "roc_auc": float((S[(L == 1) & det][:, None] > neg[None, :]).mean()),
                                "at_threshold_0.5": at(0.5, det), "at_fpr_5pct": at(th5, det)},
          "note": "held-out synthetic patches (same generator, unseen seed); not a real-camera evaluation"}
    print(json.dumps(ev, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(ev, indent=1))


if __name__ == "__main__":
    main()
