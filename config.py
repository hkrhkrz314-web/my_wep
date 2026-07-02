"""
===================================================================
Project: Wolf Host - لوحة استضافة البوتات
Author: @BLACK_ZERO2
Channel: https://t.me/ROXScripts2
Year: 2026
License: MIT
===================================================================
"""

import os
import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables with secure defaults."""

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "wolf")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "wolf123456")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "") or secrets.token_hex(32)

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    BOTS_DIR: str = os.getenv("BOTS_DIR", os.path.expanduser("~/wolfhost/bots"))
    LOGS_DIR: str = os.getenv("LOGS_DIR", os.path.expanduser("~/wolfhost/logs"))
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.expanduser("~/wolfhost/data"))
    TMP_DIR: str = os.getenv("TMP_DIR", os.path.expanduser("~/wolfhost/tmp"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{os.path.expanduser('~/wolfhost/data/wolfhost.db')}")

    WATCHDOG_INTERVAL: int = 30
    MAX_LOG_LINES: int = 500
    WS_HEARTBEAT_INTERVAL: int = 10
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: set = {".zip"}

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
