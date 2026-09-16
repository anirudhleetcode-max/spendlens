"""Fold user category corrections (Mongo `category_feedback`) into the classifier.

    python -m ml.retrain
The running API picks the new model up via POST /api/categories/retrain (or on restart).
"""
import pymongo

from app.config import get_settings
from app.services.classifier import retrain_with_feedback


def main() -> None:
    s = get_settings()
    rows = list(pymongo.MongoClient(s.mongo_uri)[s.mongo_db].category_feedback.find({}, {"text": 1, "category": 1}))
    print(retrain_with_feedback(rows))


if __name__ == "__main__":
    main()
