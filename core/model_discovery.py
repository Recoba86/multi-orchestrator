"""Read-only model declaration discovery, separate from config and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class DiscoveryResult:
    source: str
    available: bool
    models: tuple[str, ...] = ()
    detail: str = ""


def _discover_toml_models(source: str, directory: Path, pattern: str) -> DiscoveryResult:
    models: list[str] = []
    invalid_count = 0
    try:
        if not directory.is_dir():
            return DiscoveryResult(source, False, detail="source directory not found")
        paths = sorted(directory.glob(pattern))
        if not paths:
            return DiscoveryResult(source, False, detail="no declaration files found")
        # A matching directory is not a declaration file.  Treat the source as
        # unavailable rather than accidentally reading a non-file path.
        if any(not path.is_file() for path in paths):
            return DiscoveryResult(source, False, detail="source path is not a file")
        for path in paths:
            with path.open("rb") as declaration:
                data = tomllib.load(declaration)
            if not isinstance(data, dict):
                raise ValueError("declaration root is not a table")
            if "model" not in data or data["model"] is None:
                continue
            model = data["model"]
            if not isinstance(model, str) or not model.strip():
                invalid_count += 1
                continue
            if model not in models:
                models.append(model)
    except Exception:
        return DiscoveryResult(source, False, detail="source could not be read")

    if not models and invalid_count > 0:
        return DiscoveryResult(source, False, detail="no valid declarations")

    detail = f"{len(models)} model(s)"
    if invalid_count > 0:
        detail = f"{detail}, {invalid_count} invalid declaration(s)"
    return DiscoveryResult(source, True, tuple(models), detail)


def discover_codex_models(target_home: str | Path) -> tuple[DiscoveryResult, ...]:
    """Discover declared Codex models without probing or mutating the environment."""
    codex_home = Path(target_home).expanduser() / ".codex"
    return (
        _discover_toml_models("codex-profiles", codex_home, "*.config.toml"),
        _discover_toml_models("codex-agents", codex_home / "agents", "*.toml"),
    )
