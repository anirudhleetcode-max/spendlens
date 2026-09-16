"""Run one experiment from a config file and record everything needed to reproduce it.

    python -m experiments.run --config experiments/configs/sroie_main.yaml

Writes experiments/results/<name>-<YYYYMMDD>/:
    config.yaml   exact config used
    env.json      timestamp, git commit (+ dirty flag), python / library / tesseract versions, CPU count
    metrics.json  results (+ dataset name, hash, subset hash, synthetic flag)
    errors.jsonl / errors.md   worst failures (when the task produces them)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import yaml

from . import ROOT

RESULTS = ROOT / "experiments" / "results"
os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # tesseract: one thread per process, we run two in parallel


def env_info() -> dict:
    def git(*args):
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return None
    libs = {}
    for pkg in ("numpy", "scikit-learn", "opencv-python-headless", "opencv-python", "pytesseract", "pillow",
                "rapidfuzz", "pyarrow", "fastapi"):
        try:
            libs[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    try:
        from app.pipeline.ocr import tesseract_version
        tess = tesseract_version()
    except Exception:
        tess = None
    from app.pipeline.preprocess import PREPROCESS_VERSION
    from app.pipeline.receipt import PARSER_VERSION
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "libraries": libs, "tesseract": tess,
        "preprocess_version": PREPROCESS_VERSION, "parser_version": PARSER_VERSION,
    }


def run_receipts(cfg: dict, run_dir: Path) -> dict:
    from .datasets import dataset_info
    from .receipts_eval import evaluate, ids_hash, select, synthetic_records, write_errors
    ds = cfg["dataset"]
    if ds == "synthetic":
        records = synthetic_records(cfg["n"], cfg["seed"])
        info = {"name": "synthetic", "generator": "backend/ml/receipts_synth.py", "seed": cfg["seed"],
                "synthetic": True, "note": cfg.get("note", "")}
    else:
        records = select(ds, cfg.get("n"), cfg.get("seed", 0))
        info = dataset_info(ds)
    out = {"dataset": info | {"n_selected": len(records), "subset_ids_sha256_16": ids_hash(records)},
           "variants": {}}
    for i, var in enumerate(cfg["variants"]):
        subset = records[: var["n"]] if var.get("n") else records
        t = time.time()
        summary, rows, errors = evaluate(subset, ds, var["ocr"], parser_cfg=var.get("parser"))
        summary["wall_seconds"] = round(time.time() - t, 1)
        summary["ocr_settings"] = var["ocr"]
        out["variants"][var["name"]] = summary
        print(f"{var['name']}: {json.dumps({k: v for k, v in summary.items() if k in ('merchant', 'date', 'total', 'ocr')})}")
        if i == 0:
            write_errors(run_dir, errors, f"{cfg['name']} / {var['name']}")
            from .analyse_errors import main as breakdown
            breakdown(str(run_dir))
            with open(run_dir / "per_receipt.jsonl", "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
    return out


def run_classifier(cfg: dict, run_dir: Path) -> dict:
    from ml.evaluate_classifier import run as run_clf
    return run_clf(cfg, run_dir)


TASKS = {"receipt_extraction": run_receipts, "category_classifier": run_classifier}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg_path = Path(a.config)
    cfg = yaml.safe_load(cfg_path.read_text())
    run_id = f"{cfg['name']}-{datetime.now().strftime('%Y%m%d')}"
    n = 2
    while (RESULTS / run_id).exists():  # never overwrite an earlier run from the same day
        run_id = f"{cfg['name']}-{datetime.now().strftime('%Y%m%d')}-r{n}"
        n += 1
    run_dir = RESULTS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(cfg_path, run_dir / "config.yaml")
    env = env_info()
    (run_dir / "env.json").write_text(json.dumps(env, indent=2) + "\n")
    print(f"run {run_id} (commit {env['git_commit']}{' dirty' if env['git_dirty'] else ''})")
    t = time.time()
    metrics = TASKS[cfg["task"]](cfg, run_dir)
    metrics["run_id"] = run_id
    metrics["seconds"] = round(time.time() - t, 1)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"wrote {run_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
