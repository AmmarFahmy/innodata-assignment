"""Configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_STYLE_GUIDE = _PACKAGE_DIR / "style_guide.md"


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str
    style_guide_path: Path
    max_concurrency: int

    @property
    def style_guide_text(self) -> str:
        return self.style_guide_path.read_text(encoding="utf-8")


def load_config() -> Config:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    style_guide_path = Path(
        os.environ.get("STYLE_GUIDE_PATH", str(_DEFAULT_STYLE_GUIDE))
    ).expanduser()
    if not style_guide_path.is_file():
        raise RuntimeError(f"Style guide file not found: {style_guide_path}")
    try:
        max_concurrency = max(1, int(os.environ.get("MAX_CONCURRENCY", "8")))
    except ValueError:
        max_concurrency = 8
    return Config(
        api_key=api_key,
        model=model,
        style_guide_path=style_guide_path,
        max_concurrency=max_concurrency,
    )
