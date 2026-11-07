"""Create synthetic, isolated records for the read-only evaluation questions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "skills/memory-l/scripts/memory.py"


def seed(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Evaluation fixtures require a new empty workspace")
    def cli(*args, data=None):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(root), *args],
            input=json.dumps(data, ensure_ascii=False) if data is not None else None,
            capture_output=True, text=True, encoding="utf-8", check=True, timeout=60)
        return json.loads(result.stdout)
    cli("init", "--name", "DemoAgent", "--owner", "ExampleOwner")
    def save(kind, title, body, operation):
        return cli("save", "--input", "-", data={"kind": kind, "body": body, "operation_id": operation,
                   "metadata": {"title": title, "carrier": "synthetic-evaluation"}})
    def decide(record, action, operation, actor="joint", **extra):
        return cli("decide", "--input", "-", data={"id": record["id"], "expected_revision": record["revision"],
            "action": action, "operation_id": operation, "actor": actor, "reason": "Synthetic evaluation decision",
            "evidence": ["synthetic:fixture"], **extra})
    agreed = {"owner": "Synthetic owner viewpoint", "companion": "Synthetic companion viewpoint", "boundary": "Synthetic evaluation only"}
    active = save("framework", "灯塔方案的正式选择", "灯塔方案经过核对后采用的策略名称是：原文回读。旧备选策略名为全量蒸馏。", "active")
    active = decide(active, "adopt", "adopt-active", joint_review=agreed)
    daily = save("diary", "观察本的记录", "合成的未晋升日记，迁移保全与人格采用分开处理。", "diary")
    revised = save("fact", "蓝色仓库的箱数", "箱数是 5。", "boxes")
    revised = cli("revise", "--input", "-", data={"id": revised["id"], "body": "复核后的箱数是 7。", "operation_id": "correct-boxes",
                  "expected_revision": revised["revision"], "reason": "Synthetic correction"})
    rejected = save("framework", "红色方案的待用假设", "该方案的代号是赤砂。", "rejected")
    rejected = decide(rejected, "reject", "reject-red")
    changed = save("reflection", "后来修改的成长理解", "第一版合成理解。", "changed")
    changed = decide(changed, "adopt", "adopt-before-change", joint_review=agreed)
    changed = cli("revise", "--input", "-", data={"id": changed["id"], "body": "修改后的合成理解需要重新观察。", "operation_id": "change-understanding",
                  "expected_revision": changed["revision"], "reason": "Synthetic substantive change"})
    incoming = root / ".memory-sources/input.md"
    incoming.parent.mkdir()
    incoming.write_text("外部材料的合成词 zzfixture736", encoding="utf-8")
    source = cli("ingest-markdown", str(incoming), "--carrier", "synthetic-port", "--source-id", "external-one", "--scope", "private")
    source = decide(source, "confirm", "confirm-source", actor="owner")
    selected_file = incoming.parent / "selected.md"
    selected_file.write_text("已选择的合成材料 zzselected846", encoding="utf-8")
    selected = cli("ingest-markdown", str(selected_file), "--carrier", "synthetic-port", "--source-id", "external-two", "--scope", "private")
    selected = decide(selected, "select_learning", "select-source", actor="owner")
    prepared = cli("reflect-prepare", "--tier", "deep", "--operation-id", "derive", "--query", "zzselected846")
    derived = cli("reflect-commit", "--input", "-", data={"session_id": prepared["session_id"], "operation_id": "commit-derived",
        "outputs": [{"kind": "reflection", "title": "由选择材料形成的草稿", "body": "派生合成理解 zzderived846"}]})
    selected = decide(selected, "deselect_learning", "withdraw-selection", actor="owner")
    lesson = save("lesson", "保存前核验的顺序", "经过实际问题复核，先读原文，再检查版本，最后保存决定。", "lesson")
    cli("manifest")
    # This map contains only synthetic IDs; answers are stable semantic values.
    return {"active": active["id"], "diary": daily["id"], "boxes": revised["id"], "rejected": rejected["id"],
            "changed": changed["id"], "unselected": source["id"], "withdrawn_source": selected["id"],
            "derived": derived["outputs"][0], "lesson": lesson["id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    print(json.dumps(seed(parser.parse_args().workspace), ensure_ascii=False, indent=2))
