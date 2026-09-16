import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SpendLens"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "spendlens"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    jwt_ephemeral: bool = False  # set at startup when a random development secret is in use
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    # Full path to tesseract.exe on Windows if it is not on PATH,
    # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
    tesseract_cmd: str = ""
    max_upload_mb: int = 8
    # rebuild the category model in the background when the saved one can't be loaded
    auto_rebuild_model: bool = True
    # comma-separated emails allowed to call POST /api/categories/retrain
    admin_emails: str = ""
    # development | production. Production refuses to start with a placeholder JWT secret.
    env: str = "development"
    login_max_attempts: int = 10          # per email+IP within the window below
    login_window_seconds: int = 300
    orphan_receipt_hours: int = 24        # unsaved scans older than this are deleted
    model_path: str = str(BACKEND_DIR / "ml" / "artifacts" / "category_model.joblib")


PLACEHOLDER_SECRETS = {
    "", "secret", "changeme", "change-me", "change-me-in-production",
    "replace-with-a-long-random-string", "replace-with-a-long-random-string-at-least-32-chars",
}


class InsecureSecretError(RuntimeError):
    pass


def check_jwt_secret(s: Settings) -> Settings:
    """Refuse a placeholder / short JWT secret in production; in development use a random one for this
    process (tokens stop working after a restart) and say so loudly."""
    if s.jwt_secret not in PLACEHOLDER_SECRETS and len(s.jwt_secret) >= 32:
        return s
    if s.env.lower() == "production":
        raise InsecureSecretError(
            "JWT_SECRET is a placeholder or shorter than 32 characters. Generate one with "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\" and put it in backend/.env")
    logging.getLogger("spendlens").warning(
        "JWT_SECRET is not set to a real secret - using a random one for this run (sessions end on restart). "
        "Set JWT_SECRET in backend/.env.")
    s.jwt_secret = secrets.token_urlsafe(48)
    s.jwt_ephemeral = True
    return s


@lru_cache
def get_settings() -> Settings:
    return check_jwt_secret(Settings())
