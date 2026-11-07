"""Runtime paths come only from the explicitly chosen workspace."""
import json
import os
from pathlib import Path


def workspace():
    return Path(os.environ.get("MEMORY_L_WORKSPACE", str(Path.cwd()))).resolve()


def configuration():
    path = workspace() / ".memory/config.json"
    if path.is_symlink() or not path.resolve().is_relative_to(workspace()):
        raise ValueError("Configuration leaves the selected workspace")
    if not path.is_file():
        raise ValueError("Memory is not initialized. Run memory.py --workspace <folder> init --name <name> --owner <owner>.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not value.get("namespace"):
        raise ValueError("Unsupported or incomplete memory configuration")
    return value


def namespace():
    return configuration()["namespace"]


def source_days():
    days = configuration().get("source_default_days", 30)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 36500:
        raise ValueError("source_default_days must be an integer from 1 to 36500")
    return days
