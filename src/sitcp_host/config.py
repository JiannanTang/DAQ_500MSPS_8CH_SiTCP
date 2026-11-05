"""Shared configuration and runtime path helpers."""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_base_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_capture_directory() -> Path:
    return runtime_base_dir() / "captures"


def default_config_path() -> Path:
    """Return an editable register catalog suitable for source or frozen runs."""

    override = os.environ.get("SITCP_CONFIG")
    if override:
        return Path(override).expanduser()

    candidates = []
    if is_frozen():
        candidates.append(runtime_base_dir() / "config" / "registers.toml")
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidates.append(Path(bundle_root) / "config" / "registers.toml")
    else:
        candidates.extend(
            (
                Path.cwd() / "config" / "registers.toml",
                runtime_base_dir() / "config" / "registers.toml",
            )
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else runtime_base_dir() / "config" / "registers.toml"

