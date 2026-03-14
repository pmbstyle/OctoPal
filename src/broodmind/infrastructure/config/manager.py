from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key, unset_key


class ConfigManager:
    def __init__(self, env_path: str | Path = ".env") -> None:
        self.env_path = Path(env_path)
        if not self.env_path.exists():
            self.env_path.touch(mode=0o600)
        for key, value in self._read_env_values().items():
            os.environ.setdefault(key, value)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the .env file."""
        if value is None:
            value = ""
        str_value = str(value)
        set_key(str(self.env_path), key, str_value)
        # Update current environment so subsequent calls in the same process see it
        os.environ[key] = str_value

    def unset(self, key: str) -> None:
        """Remove a value from the .env file and current process environment."""
        unset_key(str(self.env_path), key)
        os.environ.pop(key, None)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the .env file or environment."""
        val = self._read_env_values().get(key)
        if val is None:
            return os.environ.get(key, default)
        return val

    def exists(self) -> bool:
        return self.env_path.exists()

    def _read_env_values(self) -> dict[str, str]:
        encodings = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
        for encoding in encodings:
            try:
                values = dotenv_values(self.env_path, encoding=encoding)
                return {key: value for key, value in values.items() if key and value is not None}
            except UnicodeDecodeError:
                continue
        return {}
