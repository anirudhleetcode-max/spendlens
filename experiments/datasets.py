"""Public receipt datasets: download, verify, load into one common record shape.

    python -m experiments.datasets download sroie     # ~183 MB, test split only
    python -m experiments.datasets download cord      # ~234 MB, test split only
    python -m experiments.datasets verify

Files go to data/raw/ (git-ignored). Nothing from these datasets is committed except aggregate
metrics and short OCR snippets in error-analysis files. See data/README.md for licences.

Record shape (dict):
    id          str   stable id inside the dataset
    image       bytes original JPEG/PNG bytes
    fields      dict  {"merchant", "date", "total", "address", "n_items"} - None when not labelled
    gt_lines    list[str]  ground-truth text lines (reading order), for CER
    source      str   dataset name
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

from . import ROOT

RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.json"

SOURCES = {
    "sroie": {
        "name": "ICDAR 2019 SROIE (deduplicated v2 mirror), test split",
        "url": "https://huggingface.co/datasets/rth/sroie-2019-v2/resolve/main/data/test-00000-of-00001.parquet",
        "page": "https://huggingface.co/datasets/rth/sroie-2019-v2",
        "original": "https://rrc.cvc.uab.es/?ch=13",
        "licence": "Mirror card declares CC-BY-2.0; the original ICDAR 2019 RRC data is distributed for "
                   "research use after registration. Used here for evaluation only; not redistributed.",
        "file": "sroie_test.parquet",
        "sha256": "695057e834bc72fdd84c2f09d0a7e93ecdd439cbda16318bc17eb1d0a5e9a893",
        "rows": 347,
        "region": "Malaysia (MYR, English receipts)",
    },
    "cord": {
        "name": "CORD v2 (Clova), test split",
        "url": "https://huggingface.co/datasets/naver-clova-ix/cord-v2/resolve/main/data/"
               "test-00000-of-00001-9c204eb3f4e11791.parquet",
        "page": "https://huggingface.co/datasets/naver-clova-ix/cord-v2",
        "original": "https://github.com/clovaai/cord",
        "licence": "CC-BY-4.0",
        "file": "cord_test.parquet",
        "sha256": "51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7",
        "rows": 100,
        "region": "Indonesia (IDR, '.' as thousands separator, no decimals)",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def path_for(name: str) -> Path:
    return RAW / SOURCES[name]["file"]


def download(name: str) -> Path:
    src = SOURCES[name]
    RAW.mkdir(parents=True, exist_ok=True)
    dest = path_for(name)
    if dest.exists() and sha256(dest) == src["sha256"]:
        print(f"{name}: already present and verified")
        return dest
    tmp = dest.with_suffix(".part")
    print(f"{name}: downloading {src['url']}")
    req = urllib.request.Request(src["url"], headers={"User-Agent": "spendlens-eval/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    digest = sha256(tmp)
    if digest != src["sha256"]:
        tmp.unlink()
        raise SystemExit(f"{name}: hash mismatch ({digest}); upstream file changed - update SOURCES after review")
    tmp.replace(dest)
    write_manifest()
    return dest


def write_manifest() -> None:
    out = {}
    for name, src in SOURCES.items():
        p = path_for(name)
        out[name] = {k: v for k, v in src.items()} | {
            "present_locally": p.exists(), "bytes": p.stat().st_size if p.exists() else None}
    MANIFEST.write_text(json.dumps(out, indent=2) + "\n")


def require(name: str) -> Path:
    p = path_for(name)
    if not p.exists():
        raise FileNotFoundError(f"Dataset required before evaluation: run `python -m experiments.datasets download {name}`")
    return p


def dataset_info(name: str) -> dict:
    src = SOURCES[name]
    return {"name": name, "title": src["name"], "sha256": src["sha256"], "licence": src["licence"],
            "synthetic": False, "region": src["region"]}


# ---------- loaders ----------

def _sroie_records(path: Path):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=16, columns=["image", "objects"]):
        for row in batch.to_pylist():
            ent = row["objects"]["entities"]
            img = row["image"]
            yield {
                "id": Path(img.get("path") or "").stem,
                "image": img["bytes"],
                "fields": {"merchant": ent.get("company"), "date": ent.get("date"), "total": ent.get("total"),
                           "address": ent.get("address"), "n_items": None},
                "gt_lines": list(row["objects"]["text"]),
                "source": "sroie",
            }


def _cord_records(path: Path):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    idx = 0
    for batch in pf.iter_batches(batch_size=8):
        for row in batch.to_pylist():
            gt = json.loads(row["ground_truth"])
            parse = gt.get("gt_parse", {})
            menu = parse.get("menu", [])
            menu = menu if isinstance(menu, list) else [menu]
            total = (parse.get("total") or {}).get("total_price")
            # rebuild text lines from the word-level annotation (grouped by row_id)
            rows: dict[int, list[tuple[float, float, str]]] = {}
            for line in gt.get("valid_line", []):
                for w in line.get("words", []):
                    q = w.get("quad", {})
                    rows.setdefault(w.get("row_id", 0), []).append(
                        (q.get("x1", 0), (q.get("y1", 0) + q.get("y3", 0)) / 2, w.get("text", "")))
            ordered = sorted(rows.values(), key=lambda ws: sum(y for _, y, _ in ws) / len(ws))  # top to bottom
            gt_lines = [" ".join(t for _, _, t in sorted(ws)) for ws in ordered]
            yield {
                "id": f"cord-test-{idx:03d}",
                "image": row["image"]["bytes"],
                "fields": {"merchant": None, "date": None, "total": total, "address": None, "n_items": len(menu)},
                "gt_lines": gt_lines,
                "source": "cord",
            }
            idx += 1


def load(name: str):
    path = require(name)
    return _sroie_records(path) if name == "sroie" else _cord_records(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("name", choices=sorted(SOURCES))
    sub.add_parser("verify")
    a = ap.parse_args()
    if a.cmd == "download":
        download(a.name)
    else:
        ok = True
        for name in SOURCES:
            p = path_for(name)
            state = "missing" if not p.exists() else ("ok" if sha256(p) == SOURCES[name]["sha256"] else "HASH MISMATCH")
            ok &= state != "HASH MISMATCH"
            print(f"{name:6} {state}")
        write_manifest()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
