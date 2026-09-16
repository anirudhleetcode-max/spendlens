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
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    # Full path to tesseract.exe on Windows if it is not on PATH,
    # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
    tesseract_cmd: str = ""
    max_upload_mb: int = 8
    model_path: str = str(BACKEND_DIR / "ml" / "artifacts" / "category_model.joblib")


@lru_cache
def get_settings() -> Settings:
    return Settings()
