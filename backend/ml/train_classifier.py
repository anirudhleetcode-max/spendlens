"""Train, evaluate and save the category classifier.

    python -m ml.train_classifier        (from backend/)

Equivalent to `python -m experiments.run --config experiments/configs/category_main.yaml` from the
project root: evaluates baselines + LogReg on the strict synthetic split, calibrates, picks the
abstention threshold on validation, then writes ml/artifacts/category_model.joblib and its model card.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from experiments import run
    sys.argv = [sys.argv[0], "--config", str(ROOT / "experiments" / "configs" / "category_main.yaml")]
    run.main()


if __name__ == "__main__":
    main()
