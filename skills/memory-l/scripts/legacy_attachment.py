"""Attach tools to an existing blueprint without moving its original memory."""
import base64
import hashlib
import json
from pathlib import Path
import uuid

from memory_core.files import atomic_write, file_lock
from memory_core.settings import configuration, core_directory, core_mapping, relative_markdown, workspace
from legacy_migration import digest, inventory, make_plan, source_file

ROOT_FILES = ("AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes")
MARKER = "<!-- memory-l existing-workspace attachment -->"


def encoded(raw):
    return base64.b64encode(raw).decode() if raw is not None else None


def decoded(value):
    return base64.b64decode(value, validate=True) if value is not None else None


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def checked(root, relative):
    import kit
    path = kit.inside(root, root / relative)
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and parent.is_relative_to(root)):
        raise ValueError("Review symlinked attachment paths separately")
    return path


def validate_plain(path, allow_empty=False):
    import re
    from integrity import CREDENTIAL
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if (not text.strip() and not allow_empty) or CREDENTIAL.search(raw) or "<!-- md-memory-template -->" in text:
        raise ValueError("Empty, template or credential-like document needs review")
    if re.search(r"<!--[^\n]*memory v1 -->\s*```json", text[:400]):
        raise ValueError("Versioned records must not be registered as plain formal documents")
    return raw


def root_after(role, before, memory_root, exclusions):
    import kit
    prefix = before or b""
    if role in {"AGENTS.md", "CLAUDE.md"}:
        other = "CLAUDE.md" if role == "AGENTS.md" else "AGENTS.md"
        block = ("\n\n" + MARKER + "\n## Memory-L 接入\n\n"
                 "继续完整加载本文件既有的身份与共建规则。另全文读取 `.memory/ATTACHMENT.md`，"
                 "按其中当前映射使用原记忆目录 `" + memory_root + "`；原文与已有决定继续接续。\n"
                 "若 `" + other + "` 存在且尚未读取，回读其中原有身份和项目规则；已读过的门牌不要递归重复展开。\n"
                 "<!-- /memory-l existing-workspace attachment -->\n")
    elif role == ".gitignore":
        block = kit.IGNORE_BLOCK
        for rule in sorted(exclusions):
            pattern = "/" + memory_root + "/" + rule
            block += "".join("\\" + char if char in "\\*?[]#! " else char for char in pattern) + "\n"
    else:
        pattern = json.dumps("/" + memory_root + "/**", ensure_ascii=False)
        block = kit.ATTR_BLOCK + pattern + " -text\n"
    return prefix + block.encode()


def runtime_hashes():
    import kit
    return {name: hashlib.sha256(raw).hexdigest() for name, raw in kit.runtime_payload().items()}


def make_attachment_plan(recipe):
    import kit
    root = workspace()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Choose the already existing workspace")
    if (root / ".claude-plugin/plugin.json").is_file() and (root / "skills/memory-l/SKILL.md").is_file():
        raise ValueError("Do not attach a private identity inside the public plugin repository")
    for relative in (".memory", ".memory-tools", ".memory-cache/memory-l"):
        if checked(root, relative).exists():
            raise ValueError("Reserved attachment path already exists; preserve it and review separately: " + relative)
    base = make_plan(recipe, attachment=True)
    source = Path(base["recipe"]["source_root"])
    relative_root = source.relative_to(root).as_posix()
    if source.parts[len(root.parts)] in {".memory", ".memory-tools", ".memory-cache", ".memory-sources"}:
        raise ValueError("The existing memory directory conflicts with kit metadata/cache slots")
    entries = {name for name in ("AGENTS.md", "CLAUDE.md") if (root / name).exists()}
    if set(base["recipe"]["entry_files"]) != entries:
        raise ValueError("Explicitly select every existing root AGENTS.md / CLAUDE.md in entry_files")
    roots = {}
    for role in ROOT_FILES:
        path = checked(root, role)
        before = validate_plain(path, allow_empty=role in {".gitignore", ".gitattributes"}) if path.exists() else None
        if before and (MARKER.encode() in before or b"# memory-l " in before):
            raise ValueError("An existing Memory-L fragment needs review before attachment")
        roots[role] = {"before": encoded(before), "after": encoded(root_after(role, before, relative_root, base["recipe"]["exclude"]))}
    plan = {"schema_version": 1, "kind": "existing_workspace_attachment", "base_plan": base,
            "core_root": relative_root, "root_files": roots, "runtime_version": kit.VERSION,
            "runtime_hashes": runtime_hashes()}
    plan["plan_digest"] = digest(plan)
    return plan


def prepare(recipe_file, output):
    plan = make_attachment_plan(json.loads(Path(recipe_file).read_text(encoding="utf-8-sig")))
    output = Path(output).absolute()
    if output.is_symlink() or output.resolve().is_relative_to(workspace()):
        raise ValueError("Save the review plan outside the existing workspace")
    raw = json_bytes(plan)
    if output.exists() and output.read_bytes() != raw:
        raise ValueError("Plan file differs; use a new filename")
    atomic_write(output, raw)
    return {"plan_file": str(output), "plan_digest": plan["plan_digest"], "mode": "existing_workspace",
            "formal_files": len(plan["base_plan"]["files"]), "unclassified": plan["base_plan"]["unclassified"],
            "warnings": plan["base_plan"]["warnings"], "root_files_to_append": list(ROOT_FILES),
            "source_memory_modified": False, "ready_to_apply": not plan["base_plan"]["unclassified"]}


def guards(root, roots):
    if set(roots) != set(ROOT_FILES):
        raise ValueError("Unexpected managed root-file set")
    for role, pair in roots.items():
        path = checked(root, role)
        if path.exists() and not path.is_file():
            raise ValueError("A managed root-file path is now a directory")
        current = path.read_bytes() if path.is_file() else None
        if current not in (decoded(pair["before"]), decoded(pair["after"])):
            raise ValueError("Existing project entry/config changed; preserve it and review: " + role)


def verify_plan(plan):
    import kit
    original = {key: value for key, value in plan.items() if key != "plan_digest"}
    if plan.get("kind") != "existing_workspace_attachment" or digest(original) != plan.get("plan_digest"):
        raise ValueError("Attachment plan was changed")
    if plan["base_plan"]["target_workspace"] != str(workspace()) or plan["runtime_version"] != kit.VERSION or plan["runtime_hashes"] != runtime_hashes():
        raise ValueError("Workspace or runtime changed; prepare a fresh plan")
    guards(workspace(), plan["root_files"])
    recipe = plan["base_plan"]["recipe"]
    entries = {role: decoded(plan["root_files"][role]["before"]) for role in recipe["entry_files"]}
    if make_plan(recipe, attachment=True, entry_bytes=entries) != plan["base_plan"]:
        raise ValueError("Original memory or source inventory changed; prepare a fresh plan")
    if plan["base_plan"]["unclassified"]:
        raise ValueError("Classify every original Markdown before attachment")
    source = Path(recipe["source_root"])
    if source.relative_to(workspace()).as_posix() != plan["core_root"]:
        raise ValueError("Core root differs from the selected original directory")
    for role, pair in plan["root_files"].items():
        if decoded(pair["after"]) != root_after(role, decoded(pair["before"]), plan["core_root"], recipe["exclude"]):
            raise ValueError("Planned root-file update differs from the append-only operation")


def receipt(root=None):
    root = Path(root).resolve() if root is not None else workspace()
    return json.loads(checked(root, ".memory/attachment.json").read_text(encoding="utf-8"))


def formal_paths(project, check_inventory=True):
    root = Path(project).resolve()
    config = configuration(root)
    attached = config["attachment"]
    source = core_directory(root)
    names = attached["formal_files"]
    if not isinstance(names, list) or len(set(names)) != len(names):
        raise ValueError("Invalid attached formal-file registry")
    required = set(core_mapping(config.get("core_files")).values())
    if not required.issubset(names):
        raise ValueError("The formal registry omits a core role")
    paths = [source_file(source, relative_markdown(name)) for name in names]
    if check_inventory:
        unknown = [name for name in inventory(source) if name not in names and not any(
            name == rule or (rule.endswith("/") and name.startswith(rule)) for rule in attached["exclude"])]
        if unknown:
            raise ValueError("New original-directory Markdown needs classification; use attach-register for actual formal memory: " + ", ".join(unknown[:5]))
    return paths


def write_owned(path, raw):
    if path.exists():
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("Attachment file already differs; preserve it for review: " + str(path))
    else:
        atomic_write(path, raw)


def check_reserved_trees(root, plan):
    allowed_metadata = {"config.json", "attachment.json", "ATTACHMENT.md", "MANIFEST.md", "records/.locks/writer.lock"}
    allowed_runtime = set(plan["runtime_hashes"]) | {"runtime-files.json"}
    for directory, allowed in ((".memory", allowed_metadata), (".memory-tools", allowed_runtime)):
        base = checked(root, directory)
        if base.exists() and not base.is_dir():
            raise ValueError("Reserved path is not a directory")
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Reserved attachment slot contains a symlink")
                relative = path.relative_to(base)
                if path.is_file() and relative.as_posix() not in allowed and not (directory == ".memory-tools" and "__pycache__" in relative.parts and path.suffix == ".pyc"):
                    raise ValueError("Reserved attachment slot contains unrelated or newly authored data: " + str(relative))


def apply(plan_file):
    import kit
    from integrity import write_manifest
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8-sig"))
    root = workspace()
    config_path = checked(root, ".memory/config.json")
    if config_path.exists():
        current = configuration(root)
        if current.get("attachment", {}).get("plan_digest") != plan.get("plan_digest"):
            raise ValueError("Existing memory metadata belongs to a different installation")
        if current["attachment"].get("phase") == "complete":
            return {"status": "already_attached", "workspace": str(root), "source_memory_modified": False}
    verify_plan(plan)
    cache = checked(root, ".memory-cache/memory-l")
    journal = cache / "attachment-transaction.json"
    if cache.exists():
        if not journal.is_file() or json.loads(journal.read_text()).get("plan_digest") != plan["plan_digest"]:
            raise ValueError("Cache slot contains unrelated files")
    else:
        if (root / ".memory").exists() or (root / ".memory-tools").exists():
            raise ValueError("A reserved path appeared after planning; preserve it and review before attaching")
        cache.mkdir(parents=True)
        atomic_write(journal, json_bytes({"plan_digest": plan["plan_digest"]}))
    with file_lock(cache / "attach.lock"):
        verify_plan(plan)
        check_reserved_trees(root, plan)
        base = plan["base_plan"]
        source_names = [entry["path"] for entry in base["files"]]
        config = {"schema_version": 1, "kit_version": kit.VERSION,
            "namespace": str(uuid.uuid5(uuid.NAMESPACE_URL, "memory-l-attachment:" + plan["plan_digest"])),
            "companion_name": base["recipe"]["name"], "owner_name": base["recipe"]["owner"],
            "source_default_days": 30, "core_root": plan["core_root"], "core_files": base["recipe"]["core_files"],
            "attachment": {"plan_digest": plan["plan_digest"], "phase": "pending", "formal_files": source_names,
                           "exclude": base["recipe"]["exclude"]}}
        stored = {"schema_version": 1, "plan_digest": plan["plan_digest"], "files": base["files"],
                  "root_files": plan["root_files"], "core_root": plan["core_root"], "warnings": base["warnings"]}
        mapping = "\n".join("- `" + role + "` → `" + plan["core_root"] + "/" + name + "`"
                            for role, name in config["core_files"].items())
        guide = ("# 原工作区接入 Memory-L\n\n继续完整加载 AGENTS.md / CLAUDE.md 中的原规则及原 MEMORY；已读门牌不递归展开。"
            "以下路径仍是唯一原文，工具没有建立第二份人格。已有采用与观察按原文接续，没有创建新的内化决定。\n\n" + mapping +
            "\n\n当前工具入口 `.memory-tools/memory.py`；core-file 与发布按职责映射直接读写这些原文件。"
            "新增自主记录保存在 `.memory/records/`，运行配置与接入记录保存在 `.memory/`，缓存位于 `.memory-cache/memory-l/`。"
            "原目录的其他正式 Markdown 需要显式登记；未初筛来源仍按原规则处理，不自动进入检索或 Git。"
            "\n\n新宿主需核对实际配置和旧自动写入者，避免同时重复采集或发布；本工具不自动修改宿主和全局设置。"
            "旧门牌与旧规则中的机器路径、工具命令逐项核对，有规则冲突时共同澄清。"
            "\n\n接入前根门牌/配置的完整字节保存在 attachment.json 的回退快照中。attach-rollback 可在这些文件未另行修改时"
            "恢复其接入前状态；原记忆与新增记录都保留。\n")
        try:
            for directory in (".memory", ".memory-tools"):
                path = checked(root, directory)
                if path.exists() and not journal.is_file():
                    raise ValueError("Existing attachment slot is not owned by this transaction")
                path.mkdir(exist_ok=True)
            if config_path.exists():
                previous = configuration(root)
                previous["attachment"]["phase"] = "pending"
                if previous != config:
                    raise ValueError("Pending attachment metadata changed")
            atomic_write(config_path, json_bytes(config))
            write_owned(checked(root, ".memory/attachment.json"), json_bytes(stored))
            write_owned(checked(root, ".memory/ATTACHMENT.md"), guide.encode())
            payload = kit.runtime_payload()
            for name, raw in payload.items():
                write_owned(checked(root, ".memory-tools/" + name), raw)
            write_owned(checked(root, ".memory-tools/runtime-files.json"), json_bytes({"version": kit.VERSION, "files": sorted(payload)}))
            verify_plan(plan)
            for role, pair in plan["root_files"].items():
                atomic_write(checked(root, role), decoded(pair["after"]))
            config["attachment"]["phase"] = "complete"
            atomic_write(config_path, json_bytes(config))
            write_manifest(root)
        except Exception:
            if (root / ".memory/attachment.json").is_file():
                try:
                    failed = configuration(root)
                    if failed.get("attachment", {}).get("plan_digest") == plan["plan_digest"]:
                        failed["attachment"]["phase"] = "needs_review"
                        atomic_write(config_path, json_bytes(failed))
                    rollback()
                except (ValueError, OSError):
                    # Preserve concurrent changes; explicit recovery can inspect the snapshot.
                    pass
            raise
    return verify()


def verify():
    from integrity import verify_assets
    root = workspace()
    config = configuration(root)
    if config.get("attachment", {}).get("phase") != "complete":
        raise ValueError("Attachment is not complete")
    saved = receipt(root)
    source = core_directory(root)
    for entry in saved["files"]:
        raw = source_file(source, relative_markdown(entry["path"])).read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Original differs from its initial attachment snapshot: " + entry["path"])
    guards(root, saved["root_files"])
    assets = verify_assets(root)
    return {"status": "attached_originals_verified", "core_root": config["core_root"],
            "formal_files": len(saved["files"]), "manifest_files": len(assets["files"]),
            "source_files_copied": 0, "new_internalization_decisions": 0,
            "actual_host_and_old_auto_writers_review_required": True}


def rollback():
    root = workspace()
    with file_lock(checked(root, ".memory-cache/memory-l") / "attach.lock"):
        return _rollback()


def _rollback():
    root = workspace()
    config = configuration(root)
    saved = receipt(root)
    if config.get("attachment", {}).get("plan_digest") != saved["plan_digest"]:
        raise ValueError("Attachment snapshot belongs to a different installation")
    guards(root, saved["root_files"])
    for role, pair in saved["root_files"].items():
        path = checked(root, role)
        before = decoded(pair["before"])
        if before is None:
            if path.exists():
                path.unlink()  # Fixed root path, exact generated bytes verified by guards above.
        else:
            atomic_write(path, before)
    config["attachment"]["phase"] = "rolled_back"
    atomic_write(root / ".memory/config.json", json_bytes(config))
    return {"status": "attachment_rolled_back", "original_memory_preserved": True,
            "new_runtime_metadata_and_records_preserved": True}


def register(path, reason):
    import kit
    kit.ensure_initialized()
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Registration requires the actual formal-document reason")
    root = workspace()
    with file_lock(kit.cache_root() / "attach.lock"):
        config = configuration(root)
        if not config.get("attachment"):
            raise ValueError("This workspace is not an existing-workspace attachment")
        attached = config["attachment"]
        relative = relative_markdown(path)
        if any(relative == rule or (rule.endswith("/") and relative.startswith(rule)) for rule in attached["exclude"]):
            raise ValueError("This path is classified as source material; use source governance instead of formal registration")
        file = source_file(core_directory(root), relative)
        raw = validate_plain(file)
        if relative not in attached["formal_files"]:
            attached["formal_files"].append(relative)
            log = root / ".memory/ATTACHMENT-EVENTS.md"
            before = log.read_bytes() if log.exists() else b"# Original-directory formal registrations\n"
            event = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "reason": reason,
                     "internalization_changed": False}
            atomic_write(log, before + b"\n```json\n" + json_bytes(event) + b"```\n")
            atomic_write(root / ".memory/config.json", json_bytes(config))
    return {"registered": relative, "new_internalization_decisions": 0,
            "next_step": "Run manifest and the usual Git checks after classifying any other new original-directory files"}
