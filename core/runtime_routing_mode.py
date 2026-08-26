"""Persistent SolMode/GrokMode operator-intent state (plan Task 1).

MANUAL_ONLY invariant (normative, spec §2.1): the persisted mode changes
ONLY through an explicit operator call to ``write_mode`` (via the CLI).
No health, telemetry, or selection code path may write mode state; reads
never mutate the authoritative file.

State lives at one authoritative path per target home
(``~/.agents/runtime-routing/mode.json`` by default), schema::

    {"version": 1, "mode": "sol_mode" | "grok_mode"}

Canonical stored values are exactly ``sol_mode`` / ``grok_mode`` — no
aliases. Missing/corrupt/unknown/unsupported state fails closed to
SOL_MODE and records a JSON anomaly sidecar next to the state file;
``read_mode`` never raises.
"""

from __future__ import annotations

from enum import Enum
import json
import os
from pathlib import Path

__all__ = [
    "RoutingMode",
    "SOL_MODE",
    "GROK_MODE",
    "MODE_STATE_PATH_DEFAULT",
    "STATE_SCHEMA_VERSION",
    "parse_mode",
    "read_mode",
    "write_mode",
]


class RoutingMode(Enum):
    SOL_MODE = "sol_mode"
    GROK_MODE = "grok_mode"


SOL_MODE = RoutingMode.SOL_MODE
GROK_MODE = RoutingMode.GROK_MODE

MODE_STATE_PATH_DEFAULT = Path.home() / ".agents" / "runtime-routing" / "mode.json"
STATE_SCHEMA_VERSION = 1

_STATE_DIR_MODE = 0o700
_STATE_FILE_MODE = 0o600


def parse_mode(value: object) -> RoutingMode:
    """Parse an exact canonical mode value; anything else raises ValueError.

    Aliases ("SolMode", "SOLMODE", "grok", ...) are deliberately rejected:
    canonical storage values are only ``sol_mode`` / ``grok_mode``.
    """
    if not isinstance(value, str):
        raise ValueError(f"mode must be a string, got {type(value).__name__}")
    try:
        return RoutingMode(value)
    except ValueError as exc:
        raise ValueError(
            f"invalid mode {value!r}; expected one of: "
            f"{', '.join(m.value for m in RoutingMode)}"
        ) from exc


def _anomaly_path(state_path: Path) -> Path:
    return Path(str(state_path) + ".anomaly")


def _record_anomaly(state_path: Path, reason: str, observed: object,
                    resolved: RoutingMode) -> None:
    """Best-effort anomaly sidecar; never masks the fail-closed result."""
    payload = {
        "reason": reason,
        "observed": observed if isinstance(observed, (str, int, float,
                                                      bool, type(None))) else str(observed),
        "resolved": resolved.value,
    }
    try:
        parent = state_path.parent
        if parent.is_dir():
            tmp = parent / (state_path.name + ".anomaly.tmp")
            tmp.write_text(json.dumps(payload, sort_keys=True),
                           encoding="utf-8")
            os.replace(tmp, _anomaly_path(state_path))
    except OSError:
        pass


def read_mode(state_path: Path | None = None) -> RoutingMode:
    """Load persisted mode; fail closed to SOL_MODE on any anomaly."""
    path = MODE_STATE_PATH_DEFAULT if state_path is None else Path(state_path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        # Sidecar needs the parent dir; create it for the sidecar only —
        # read_mode must NEVER create the authoritative mode.json itself.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return SOL_MODE
        _record_anomaly(path, "missing", None, SOL_MODE)
        return SOL_MODE
    except OSError:
        _record_anomaly(path, "unreadable", None, SOL_MODE)
        return SOL_MODE

    # Refuse symlinks for the authoritative file (no following).
    if path.is_symlink():
        _record_anomaly(path, "symlink", None, SOL_MODE)
        return SOL_MODE

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _record_anomaly(path, "corrupt", repr(exc)[:200], SOL_MODE)
        return SOL_MODE

    if not isinstance(data, dict) or set(data) - {"version", "mode"}:
        _record_anomaly(path, "unexpected_schema", None, SOL_MODE)
        return SOL_MODE

    version = data.get("version", 1)  # missing version treated as v1
    if not isinstance(version, int) or isinstance(version, bool) \
            or version != STATE_SCHEMA_VERSION:
        _record_anomaly(path, "unsupported_version", version, SOL_MODE)
        return SOL_MODE

    stored = data.get("mode")
    if not isinstance(stored, str):
        _record_anomaly(path, "non_string_mode", stored, SOL_MODE)
        return SOL_MODE

    try:
        return parse_mode(stored)
    except ValueError:
        _record_anomaly(path, "unknown_value", stored, SOL_MODE)
        return SOL_MODE


def write_mode(mode: RoutingMode, state_path: Path | None = None) -> None:
    """Atomically persist the operator's explicit mode choice.

    Same-filesystem temp file + ``os.replace`` (atomic swap, no partial
    content visible under the authoritative name). File mode 0600, dir 0700.
    Symlinked destination paths are rejected without touching the target.
    """
    # Accept only genuine RoutingMode members; strings/aliases are rejected
    # before any I/O so invalid calls cannot touch persisted state.
    if isinstance(mode, RoutingMode):
        validated = mode
    else:
        raise ValueError(
            f"write_mode expects a RoutingMode member, got {mode!r}; "
            f"valid: {', '.join(m.value for m in RoutingMode)}"
        )
    path = MODE_STATE_PATH_DEFAULT if state_path is None else Path(state_path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if path.is_symlink():
        raise RuntimeError(
            f"refusing to write through symlinked state path: {path}"
        )

    payload = json.dumps(
        {"version": STATE_SCHEMA_VERSION, "mode": validated.value},
        sort_keys=True,
    ).encode("utf-8")

    tmp = parent / f".{path.name}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _STATE_FILE_MODE)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, _STATE_FILE_MODE)
        os.replace(tmp, path)          # atomic within the same directory
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.chmod(parent, _STATE_DIR_MODE)
    except OSError:
        pass
