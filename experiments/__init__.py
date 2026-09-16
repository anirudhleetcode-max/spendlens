"""Experiments package. Run from the project root: `python -m experiments.run --config ...`.
The backend code is imported from ../backend."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
