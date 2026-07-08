"""Repository paths resolved from this package location (not from cwd)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "configs" / "settings.yaml"

REQUIRED_CONFIG_PATHS: tuple[Path, ...] = (SETTINGS_PATH,)
