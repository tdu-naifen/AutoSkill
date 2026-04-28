"""Centralized configuration for AutoSkill."""
import os
from pathlib import Path

def load_dotenv():
    """Load .env file from CWD if present."""
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
