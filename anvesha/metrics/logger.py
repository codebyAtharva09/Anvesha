"""Run logging: per-frame CSV, summary JSON, config snapshot, event log and
the automatic performance report (HTML with charts, + PDF charts)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import uuid
from pathlib import Path

import yaml

from .metrics import COLUMNS


def experiment_id(cfg) -> str:
    return f"{cfg.name}-{cfg.run.pipeline}-s{cfg.run.seed}-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:4]}"


def write_run(base: Path, cfg, eng, summary: dict, report: bool = True) -> Path:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    exp = experiment_id(cfg)
    summary = dict(summary)
    summary["experiment_id"] = exp
    summary["created"] = dt.datetime.now().isoformat(timespec="seconds")
    with open(base / "frames.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in eng.metrics.rows:
            w.writerow([f"{x:.4f}" if isinstance(x, float) else x for x in r])
    (base / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    (base / "config.yaml").write_text(yaml.safe_dump(cfg.to_dict(), sort_keys=False))
    (base / "events.log").write_text("\n".join(eng.event_log))
    if report:
        from ..report.report import run_report
        run_report(base, cfg, eng.metrics.arrays(), summary, eng.event_log)
    return base
