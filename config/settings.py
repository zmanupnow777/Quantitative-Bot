"""Project-wide configuration loaded from environment variables and `.env`."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
VALID_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")

ALPACA_API_KEY: str
ALPACA_SECRET_KEY: str
ALPACA_BASE_URL: str
DATA_DIR: Path
REPORTS_DIR: Path
LOGS_DIR: Path
DEFAULT_START_DATE: str
DEFAULT_END_DATE: str
DEFAULT_TIMEFRAME: str
CACHE_MAX_AGE_HOURS: int
MAX_RETRIES: int
RETRY_DELAY_SECONDS: float
LOG_LEVEL: str
LOG_FORMAT: str


def _get_env_int(name: str, default: int) -> int:
    """Return an integer environment variable with a safe default."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    """Return a float environment variable with a safe default."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def refresh(env_path: Path | None = None, *, override: bool = False) -> None:
    """Reload configuration values from the environment and an optional `.env` file."""

    global ALPACA_API_KEY
    global ALPACA_SECRET_KEY
    global ALPACA_BASE_URL
    global DATA_DIR
    global REPORTS_DIR
    global LOGS_DIR
    global DEFAULT_START_DATE
    global DEFAULT_END_DATE
    global DEFAULT_TIMEFRAME
    global CACHE_MAX_AGE_HOURS
    global MAX_RETRIES
    global RETRY_DELAY_SECONDS
    global LOG_LEVEL
    global LOG_FORMAT

    load_dotenv(env_path or ENV_FILE, override=override)

    ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "cache"))
    REPORTS_DIR = Path(os.getenv("REPORTS_DIR", PROJECT_ROOT / "reports"))
    LOGS_DIR = Path(os.getenv("LOGS_DIR", PROJECT_ROOT / "logs"))

    DEFAULT_START_DATE = os.getenv("DEFAULT_START_DATE", "2020-01-01")
    DEFAULT_END_DATE = os.getenv("DEFAULT_END_DATE", date.today().isoformat())
    DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "1d")

    CACHE_MAX_AGE_HOURS = _get_env_int("CACHE_MAX_AGE_HOURS", 24)
    MAX_RETRIES = _get_env_int("MAX_RETRIES", 3)
    RETRY_DELAY_SECONDS = _get_env_float("RETRY_DELAY_SECONDS", 2.0)

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
    )

    for directory in (DATA_DIR, REPORTS_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


refresh()

__all__ = [
    "ALPACA_API_KEY",
    "ALPACA_BASE_URL",
    "ALPACA_SECRET_KEY",
    "CACHE_MAX_AGE_HOURS",
    "DATA_DIR",
    "DEFAULT_END_DATE",
    "DEFAULT_START_DATE",
    "DEFAULT_TIMEFRAME",
    "ENV_FILE",
    "LOG_FORMAT",
    "LOG_LEVEL",
    "LOGS_DIR",
    "MAX_RETRIES",
    "PROJECT_ROOT",
    "REPORTS_DIR",
    "RETRY_DELAY_SECONDS",
    "VALID_TIMEFRAMES",
    "refresh",
]
