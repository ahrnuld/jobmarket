"""Paths and settings. Everything is overridable through environment variables or a .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# pipeline/src/jobmarket/config.py -> repository root is three levels up from the package dir
REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines; existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    db_path: Path
    reference_dir: Path
    manual_dir: Path
    history_dir: Path
    labels_dir: Path
    corrections_file: Path
    changelog_file: Path
    publish_dir: Path
    snapshots_dir: Path
    adzuna_app_id: str
    adzuna_app_key: str

    @property
    def has_adzuna_credentials(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)


def load_settings(repo_root: Path | None = None) -> Settings:
    root = repo_root or REPO_ROOT
    _load_dotenv(root / ".env")
    data = root / "data"
    return Settings(
        repo_root=root,
        db_path=Path(os.environ.get("JOBMARKET_DB", root / "var" / "jobmarket.sqlite")),
        reference_dir=data / "reference",
        manual_dir=data / "manual",
        history_dir=data / "aggregates",
        labels_dir=data / "labels",
        corrections_file=data / "corrections.yaml",
        changelog_file=data / "changelog.yaml",
        # The static site reads only from here; written atomically after validation (NFR-07).
        publish_dir=root / "site" / "public" / "data",
        snapshots_dir=root / "var" / "snapshots",
        adzuna_app_id=os.environ.get("ADZUNA_APP_ID", ""),
        adzuna_app_key=os.environ.get("ADZUNA_APP_KEY", ""),
    )
