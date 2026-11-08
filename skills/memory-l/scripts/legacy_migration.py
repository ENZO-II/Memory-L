"""Explicit, original-byte migration of a legacy Markdown blueprint."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from memory_core.files import atomic_write, file_lock
from memory_core.settings import CORE_NAMES, core_mapping, relative_markdown, workspace

RESERVED = {"manifest.md", "loader.md", "migration.md", "kit-integration.md"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_name(value):
    if not isinstance(value, str) or not value or any(ch in value for ch in "\\:\r\n\0"):
        raise ValueError("Source selections must be portable relative paths")
    if PurePosixPath(value).is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("Source selection leaves its root")
    return value


def source_file(root, relative):
    path = root / source_name(relative)
    if not path.resolve().is_relative_to(root) or any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and parent.is_relative_to(root)):
        raise ValueError("Migration source contains a symlink or leaves its root")
    if not path.is_file():
        raise ValueError("Missing selected Markdown: " + relative)
    return path


def inventory(root):
    names = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Review symlinked migration sources separately")
        if path.is_file() and path.suffix.lower() == ".md":
            names.append(path.relative_to(root).as_posix())
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Source filenames collide on case-insensitive filesystems")
    return sorted(names)


def make_plan(recipe):
    if not isinstance(recipe, dict) or set(recipe) != {"source_root", "name", "owner", "core_files", "formal_files", "exclude", "entry_files"}:
        raise ValueError("Recipe requires source_root, name, owner, core_files, formal_files, exclude and entry_files")
    for key in ("name", "owner"):
        value = recipe[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ch in value for ch in "\r\n\0"):
            raise ValueError("Provide the existing companion and owner names")
    if not isinstance(recipe["source_root"], str):
        raise ValueError("source_root must be an absolute directory path")
    root = Path(recipe["source_root"])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("source_root must be an existing absolute directory")
    root = root.resolve()
    existing_config = root / "config.json"
    if existing_config.is_file():
        configured = json.loads(existing_config.read_text(encoding="utf-8-sig"))
        if isinstance(configured, dict) and configured.get("kit_version") and configured.get("namespace"):
            raise ValueError("This is an existing Memory-L workspace; use a reviewed runtime upgrade, not the plain Markdown blueprint importer")
    target = workspace()
    if root.is_relative_to(target) or target.is_relative_to(root):
        raise ValueError("Source and new target must be separate, non-overlapping directories")
    mapping = core_mapping(recipe["core_files"])
    extra = recipe["formal_files"]
    excluded_rules = recipe["exclude"]
    if not isinstance(extra, list) or not isinstance(excluded_rules, dict):
        raise ValueError("formal_files must be a list; exclude maps paths or directory prefixes to reasons")
    selected = set(mapping.values())
    for value in extra:
        value = relative_markdown(value)
        if value in selected:
            raise ValueError("Duplicate core/formal selection: " + value)
        selected.add(value)
    if len({name.casefold() for name in selected}) != len(selected):
        raise ValueError("Selected target paths collide")
    for name in selected:
        if name.casefold() in RESERVED or name.split("/")[0].casefold() == "previous-entries":
            raise ValueError("Selected source collides with kit migration metadata: " + name)
    exclusions = {}
    for rule, reason in excluded_rules.items():
        if not isinstance(rule, str):
            raise ValueError("Exclusion paths must be strings")
        source_name(rule[:-1] if rule.endswith("/") else rule)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Every excluded path or prefix needs an actual reason")
        exclusions[rule] = reason
    all_names = inventory(root)
    missing = selected - set(all_names)
    if missing:
        raise ValueError("Selected Markdown is missing: " + ", ".join(sorted(missing)))
    excluded, unclassified, entries, warnings = [], [], [], []
    from integrity import CREDENTIAL
    for name in all_names:
        reasons = [reason for rule, reason in exclusions.items() if name == rule or (rule.endswith("/") and name.startswith(rule))]
        if name in selected:
            if reasons:
                raise ValueError("A selected file is also excluded: " + name)
            path = source_file(root, name)
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            if not text.strip() or "<!-- md-memory-template -->" in text or CREDENTIAL.search(raw):
                raise ValueError("Empty/template/credential-like source needs review: " + name)
            if re.search(r"<!--[^\n]*memory v1 -->\s*```json", text[:400]):
                raise ValueError("Versioned records need schema-aware migration, not plain-document admission: " + name)
            if re.search(r"[A-Za-z]:[\\/]|(?<!\w)/(?:home|Users|mnt|opt)/", text):
                warnings.append({"file": name, "kind": "machine_specific_paths_review_required"})
            entries.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        elif reasons:
            excluded.append({"path": name, "reason": "; ".join(reasons)})
        else:
            unclassified.append(name)
    entry_files = recipe["entry_files"]
    if not isinstance(entry_files, dict) or set(entry_files) - {"AGENTS.md", "CLAUDE.md"}:
        raise ValueError("entry_files explicitly maps old AGENTS.md / CLAUDE.md roles to their absolute source files")
    entry_rows, normalized_entries = [], {}
    for role, value in entry_files.items():
        if not isinstance(value, str):
            raise ValueError("Old entry paths must be absolute filenames")
        path = Path(value)
        if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.resolve().is_relative_to(target):
            raise ValueError("Old entry path is missing, unsafe or inside the new target")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        if not text.strip() or CREDENTIAL.search(raw):
            raise ValueError("Old entry is empty or contains a credential-like literal: " + role)
        normalized_entries[role] = str(path.resolve())
        entry_rows.append({"path": "previous-entries/" + role, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        if re.search(r"[A-Za-z]:[\\/]|(?<!\w)/(?:home|Users|mnt|opt)/", text):
            warnings.append({"file": "previous-entries/" + role, "kind": "machine_specific_paths_review_required"})
    normalized = {**recipe, "source_root": str(root), "name": recipe["name"].strip(), "owner": recipe["owner"].strip(),
                  "core_files": mapping, "formal_files": sorted(extra), "entry_files": normalized_entries}
    plan = {"schema_version": 1, "kind": "legacy_markdown_blueprint", "target_workspace": str(target),
            "recipe": normalized, "files": entries, "entry_files": sorted(entry_rows, key=lambda row: row["path"]), "source_inventory": all_names,
            "excluded": excluded, "unclassified": unclassified, "warnings": warnings}
    plan["plan_digest"] = digest(plan)
    return plan


def prepare(recipe_file, output):
    plan = make_plan(json.loads(Path(recipe_file).read_text(encoding="utf-8-sig")))
    output = Path(output).absolute()
    source = Path(plan["recipe"]["source_root"])
    if output.is_symlink() or output.resolve().is_relative_to(source) or output.resolve().is_relative_to(workspace()):
        raise ValueError("Save the plan outside both source memory and the new target")
    encoded = (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode()
    if output.exists() and output.read_bytes() != encoded:
        raise ValueError("Plan output already differs; select a new plan filename")
    atomic_write(output, encoded)
    return {"plan_file": str(output), "plan_digest": plan["plan_digest"], "formal_files": len(plan["files"]),
            "excluded_files": len(plan["excluded"]), "unclassified": plan["unclassified"], "warnings": plan["warnings"],
            "old_entry_files": len(plan["entry_files"]), "ready_to_apply": not plan["unclassified"], "source_modified": False, "target_created": False}


def verify(project=None):
    from integrity import read_payload, verify_assets
    from memory_core.settings import configuration
    root = Path(project).resolve() if project is not None else workspace()
    receipt = read_payload(root / ".memory/MIGRATION.md")
    config = configuration(root)
    if receipt.get("schema_version") != 1 or config.get("migration_plan") != receipt.get("plan_digest") or config.get("core_files") != receipt.get("core_files"):
        raise ValueError("Migration receipt and active core mapping differ")
    for entry in receipt["files"]:
        path = source_file(root / ".memory", relative_markdown(entry["path"]))
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Migrated original differs from its initial snapshot: " + entry["path"])
    assets = verify_assets(root)
    return {"status": "migration_originals_verified", "files": len(receipt["files"]),
            "manifest_files": len(assets["files"]), "core_files": receipt["core_files"],
            "new_internalization_decisions": 0, "source_directory_required": False,
            "actual_new_session_review_required": True, "warnings": receipt["warnings"]}


def apply(plan_file):
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8-sig"))
    expected = make_plan(plan["recipe"])
    if plan != expected or plan["target_workspace"] != str(workspace()):
        raise ValueError("Plan, source bytes, inventory or target changed; regenerate and review the plan")
    if plan["unclassified"]:
        raise ValueError("Classify every source Markdown before applying: " + ", ".join(plan["unclassified"][:5]))
    root, target = Path(plan["recipe"]["source_root"]), workspace()
    if target.exists():
        raise ValueError("Migration target already exists; use a new path or verify the previously migrated workspace")
    documents = {entry["path"]: source_file(root, entry["path"]).read_bytes() for entry in plan["files"]}
    for role, filename in plan["recipe"]["entry_files"].items():
        documents["previous-entries/" + role] = Path(filename).read_bytes()
    receipt = {key: plan[key] for key in ("schema_version", "kind", "plan_digest", "files", "excluded", "warnings")}
    receipt["files"] = plan["files"] + plan["entry_files"]
    receipt["core_files"] = plan["recipe"]["core_files"]
    from integrity import markdown_payload
    documents["MIGRATION.md"] = markdown_payload("Original Markdown migration receipt", receipt)
    import kit
    from string import Template
    protocol = Template((kit.template_root() / "MEMORY.md").read_text(encoding="utf-8")).substitute(
        name=plan["recipe"]["name"], owner=plan["recipe"]["owner"])
    routing = "\n".join("- `" + name + "` → `.memory/" + path + "`" for name, path in receipt["core_files"].items())
    introduction = ("# 既有身份接续：先读此页\n\n原有 MEMORY、种子、人格与成长正文完整保留。以下映射给出当前工作区的实际文件；"
                    "按原有加载次序全文读取它们，不用新模板重建身份。旧正文中的原机器绝对路径与旧插件命令须按本次路径核对，"
                    "不要据此启用另一套写入。当前工具入口为 `.memory-tools/memory.py`。\n\n" + routing +
                    "\n\n原有采用、观察与来源状态不因迁移而重新分级。本次没有创建内化决定。已有治理与本工具流程有冲突时，"
                    "保留双方实际规则并先共同澄清，不用通用模板覆盖旧有共建决定。下方是当前工具协议，结合原有规则使用。"
                    "使用 core-file 时传职责名，工具会按映射读取原文件；发布日记、成长与校准也写入相应原文件。\n\n")
    if plan["entry_files"]:
        introduction += "## 旧门牌中的身份与共建规则也需全文读取\n\n"
        for role in sorted(plan["recipe"]["entry_files"]):
            introduction += "- `.memory/previous-entries/" + role + "`，也可用 core-file PREVIOUS-" + role + " 回读。\n"
        introduction += "\n先保留并理解这些原有身份与加载规则，再按本页当前路径加载核心。旧路径与旧插件命令不能据此自动恢复运行；平台配置按实际目标另行核对。\n\n"
    documents["KIT-INTEGRATION.md"] = (introduction + protocol).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / ("." + target.name + ".migration.lock")
    if lock.is_symlink():
        raise ValueError("Migration lock may not be a symlink")
    with file_lock(lock, timeout=30):
        if target.exists():
            raise ValueError("Target appeared while preparing migration; preserve it and choose a new path")
        staging = Path(tempfile.mkdtemp(prefix=".memory-l-migrate-", dir=target.parent)).resolve()
        previous = os.environ.get("MEMORY_L_WORKSPACE")
        try:
            os.environ["MEMORY_L_WORKSPACE"] = str(staging)
            kit.initialize(plan["recipe"]["name"], plan["recipe"]["owner"], migration={
                "core_files": receipt["core_files"], "documents": documents, "plan_digest": plan["plan_digest"],
                "legacy_entries": sorted(plan["recipe"]["entry_files"])})
            verify(staging)
            os.environ["MEMORY_L_WORKSPACE"] = str(target)
            if make_plan(plan["recipe"]) != plan:
                raise ValueError("Sources changed during migration; preserve originals and prepare a fresh plan")
            if target.exists():
                raise ValueError("Target appeared during migration")
            os.rename(staging, target)
        finally:
            if previous is None:
                os.environ.pop("MEMORY_L_WORKSPACE", None)
            else:
                os.environ["MEMORY_L_WORKSPACE"] = previous
            if staging.exists():
                # Only remove the exact private staging directory created above.
                if staging.parent != target.parent.resolve() or not staging.name.startswith(".memory-l-migrate-") or staging.is_symlink():
                    raise ValueError("Staging cleanup target differs from the owned migration directory")
                shutil.rmtree(staging)
    return verify(target)
