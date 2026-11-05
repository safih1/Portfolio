"""Configuration and paths for Lead Hunter."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_DIR.parents[1]

# Root .env first, project-local .env second (project wins).
load_dotenv(REPO_ROOT / ".env")
load_dotenv(PROJECT_DIR / ".env", override=False)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _resolve_path(value: str, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


DB_PATH = _resolve_path(env("LEADHUNTER_DB"), PROJECT_DIR / "data" / "leads.db")
DATA_DIR = PROJECT_DIR / "data"

GROQ_API_KEY = env("GROQ_API_KEY")
GROQ_MODEL = env("GROQ_MODEL", "openai/gpt-oss-120b")

SENDER_NAME = env("SENDER_NAME", env("FROM_NAME", "Safi Irfan"))
SENDER_EMAIL = env("FROM_EMAIL", env("SMTP_USER", ""))
SENDER_COMPANY = env("SENDER_COMPANY", "Safi AI Automation")
CALENDLY_LINK = env("CALENDLY_LINK", "")
PORTFOLIO_URL = env("PORTFOLIO_URL", "")

GOOGLE_PLACES_API_KEY = env("GOOGLE_PLACES_API_KEY")
FACEBOOK_PAGE_ACCESS_TOKEN = env("FACEBOOK_PAGE_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = env("FACEBOOK_PAGE_ID")
FACEBOOK_APP_SECRET = env("FACEBOOK_APP_SECRET")
FACEBOOK_VERIFY_TOKEN = env("FACEBOOK_VERIFY_TOKEN", "lead-hunter-verify")

DEFAULT_SERVICES = [
    "AI receptionist / voice agent",
    "n8n workflow automation",
    "CRM setup and cleanup",
    "Landing page / website",
    "AI chatbot",
]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
