"""The text model used for categorisation. Kept in its own module so training and the API
build exactly the same pipeline."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline


def features() -> FeatureUnion:
    # word n-grams capture "petrol", "movie ticket"; char n-grams survive OCR typos
    # ("pharrnacy") and unseen brand names that share pieces with known ones ("...mart", "...medicals").
    return FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True,
                                 token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9]+\b", lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, sublinear_tf=True,
                                 lowercase=True, max_features=40000)),
    ])


def make_logreg() -> Pipeline:
    return Pipeline([("tfidf", features()),
                     ("clf", LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced"))])


def make_cnb() -> Pipeline:
    return Pipeline([("tfidf", features()), ("clf", ComplementNB(alpha=0.3))])
