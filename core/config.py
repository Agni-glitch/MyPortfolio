from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    mongo_uri: str
    mongo_db_name: str = "portfolio"

    cloudinary_url: str = ""
    cloudinary_folder: str = "portfolio"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_email: str

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_email: str = ""
    smtp_password: str = ""

    site_url: str = ""
    site_name: str = "My Portfolio"
    environment: str = "production"

    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5

    # Provided automatically by Vercel at build and run time.
    vercel_project_production_url: str = ""
    vercel_git_commit_sha: str = ""

    @model_validator(mode="after")
    def _default_site_url(self):
        if not self.site_url:
            host = self.vercel_project_production_url
            self.site_url = f"https://{host}" if host else "http://localhost:8000"
        self.site_url = self.site_url.rstrip("/")
        return self

    @property
    def asset_version(self) -> str:
        """Cache-buster for /static URLs; changes on every deploy."""
        return self.vercel_git_commit_sha[:8] or "dev"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def admin_email_normalized(self) -> str:
        return self.admin_email.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
