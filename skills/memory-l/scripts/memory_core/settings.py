"""Runtime paths come only from the explicitly chosen workspace."""
import json
import os
from pathlib import Path, PurePosixPath

CORE_NAMES = ("MEMORY.md", "SEED.md", "PROFILE.md", "USER.md", "TIMELINE.md", "SOUL.md", "SELF-NOTES.md")


def relative_markdown(value):
    if not isinstance(value, str) or not value or any(ch in value for ch in "\\:\r\n\0"):
        raise ValueError("Use a portable relative Markdown path with forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} or part.startswith(".") for part in value.split("/")) or path.suffix.lower() != ".md":
        raise ValueError("Use a non-hidden Markdown path inside the memory directory")
    if any(part.casefold() == "records" for part in path.parts):
        raise ValueError("Versioned record stores need their own schema-aware migration; do not copy them as plain Markdown")
    return path.as_posix()


def core_mapping(value=None):
    mapping = {name: name for name in CORE_NAMES} if value is None else value
    if not isinstance(mapping, dict) or set(mapping) != set(CORE_NAMES):
        raise ValueError("Core mapping must cover every named core file")
    result = {name: relative_markdown(path) for name, path in mapping.items()}
    if len({path.casefold() for path in result.values()}) != len(CORE_NAMES):
        raise ValueError("Give each core role a distinct original file")
    return result


def workspace():
    return Path(os.environ.get("MEMORY_L_WORKSPACE", str(Path.cwd()))).resolve()


def configuration(project=None):
    root = Path(project).resolve() if project is not None else workspace()
    path = root / ".memory/config.json"
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Configuration leaves the selected workspace")
    if not path.is_file():
        raise ValueError("Memory is not initialized. Run memory.py --workspace <folder> init --name <name> --owner <owner>.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not value.get("namespace"):
        raise ValueError("Unsupported or incomplete memory configuration")
    core_mapping(value.get("core_files"))
    return value


def core_path(name, project=None):
    if name not in CORE_NAMES:
        raise ValueError("Unknown core role")
    root = Path(project).resolve() if project is not None else workspace()
    relative = core_mapping(configuration(root).get("core_files"))[name]
    directory = core_directory(root)
    path = directory / relative
    if path.is_symlink() or not path.resolve().is_relative_to(directory):
        raise ValueError("Core file leaves the workspace")
    return path


def core_directory(project=None):
    root = Path(project).resolve() if project is not None else workspace()
    relative = configuration(root).get("core_root", ".memory")
    if not isinstance(relative, str) or not relative or any(ch in relative for ch in "\\:\r\n\0"):
        raise ValueError("Core root must be a portable workspace-relative directory")
    if PurePosixPath(relative).is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("Core root leaves the workspace")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Core root leaves the workspace")
    return path


def namespace():
    return configuration()["namespace"]


def source_days():
    days = configuration().get("source_default_days", 30)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 36500:
        raise ValueError("source_default_days must be an integer from 1 to 36500")
    return days
