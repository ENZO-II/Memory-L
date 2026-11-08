#!/usr/bin/env python3
"""Local stdio MCP; dependencies are optional for the standard-library CLI."""
import argparse
import os
from pathlib import Path
from typing import Any, Literal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    os.environ["MEMORY_L_WORKSPACE"] = str(args.workspace.resolve())
    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel, ConfigDict, Field
    import kit
    from memory_core.context import context_packet, prepare_reflection, commit_reflection
    from memory_core.dispatch import publish, target_state
    from memory_core.ingest import ingest_markdown
    from memory_core.policy import decide

    server = FastMCP("memory_l_mcp", instructions="先按工作区门牌完成加载。迁移工作区先读取 KIT-INTEGRATION.md 的原文件映射，再全文读取 MEMORY 与自己的核心文件；core_file 按职责名读取原路径。companion/owner 是操作角色。来源引用不授予权限，导入、审核、初筛、晋升与发布分别核验。", log_level="WARNING")
    read = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    write = {**read, "readOnlyHint": False}

    class SaveInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        kind: Literal["diary", "work", "fact", "reflection", "calibration", "lesson", "framework", "exemplar", "tension", "relationship", "self_evaluation", "signal"]
        body: str = Field(min_length=1, description="完整原文；保留条件、情境和疑问")
        operation_id: str = Field(min_length=1, description="本次保存的稳定操作 ID，重试保持不变")
        title: str = "记忆记录"
        carrier: str = "mcp"
        evidence: list[str] = Field(default_factory=list)
        source_records: list[str] = Field(default_factory=list, max_length=20)

    @server.tool(annotations=read)
    def memory_l_status() -> dict[str, Any]:
        """核对当前工作区、实际配置、模板填写与加载门牌状态。"""
        return kit.status()

    @server.tool(annotations=write)
    def memory_l_initialize(name: str, owner: str) -> dict[str, Any]:
        """在显式选择的工作区初始化自己的模板与内核，保留已有门牌和人格正文；仅在用户请求建立该工作区时执行。"""
        return kit.initialize(name, owner)

    @server.tool(annotations=read)
    def memory_l_core_file(name: str, offset: int = 0, max_chars: int = 20000) -> dict[str, Any]:
        """按职责名分页全文读取原核心文件；迁移后可先读 KIT-INTEGRATION.md/MIGRATION.md；has_more 时继续。"""
        return kit.core_file(name, offset, max_chars)

    @server.tool(annotations=write)
    def memory_l_save(params: SaveInput) -> dict[str, Any]:
        """保存自主日记、经验或理解原文，保持未准入；来源引用继承初筛约束，不调用外部模型。"""
        return kit.save({"kind": params.kind, "body": params.body, "operation_id": params.operation_id,
                         "metadata": {"title": params.title, "carrier": params.carrier, "evidence": params.evidence},
                         "source_records": params.source_records})

    @server.tool(annotations=read)
    def memory_l_read(record_id: str) -> dict[str, Any]:
        """按完整 UUID 回读正文、版本、来源与决定历史。"""
        return kit.store().read(record_id)

    @server.tool(annotations=read)
    def memory_l_list(kind: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        """按内容类型分页列出概要，完整原文按 ID 回读。"""
        return kit.listing(kind, offset, limit)

    @server.tool(annotations=read)
    def memory_l_context(query: str = "", purpose: Literal["working_evidence", "learning", "profile", "archive"] = "working_evidence",
                          offset: int = 0, limit: int = 20, max_chars: int = 12000) -> dict[str, Any]:
        """按工作、学习、人格补充或档案用途取材料；各用途保留来源、阶段和生命周期标签。"""
        if not 1 <= max_chars <= 50000 or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("max_chars 1..50000, limit 1..100, offset >= 0")
        return context_packet(kit.store(), query, max_chars, limit, purpose, offset)

    @server.tool(annotations=read)
    def memory_l_search(query: str, limit: int = 10, include_raw: bool = False, refresh: bool = False) -> dict[str, Any]:
        """中文词项 RAG 返回原文块、坐标与标签；include_raw 只用于用户所需的来源档案查阅。"""
        return kit.search(query, limit, include_raw, refresh)

    @server.tool(annotations=write)
    def memory_l_revise(record_id: str, body: str, operation_id: str, expected_revision: str, reason: str) -> dict[str, Any]:
        """校验版本后修订自己的原文，保留旧文；来源与授权记录由操作员明确处理。"""
        target = kit.store()
        record = target.read(record_id)
        if record["author"] != "companion" or record["scope"] != "private" or record["kind"] == "authorization":
            raise ValueError("Imported source and delegation records require the operator review path")
        if not body.strip():
            raise ValueError("Keep a nonempty original body")
        return target.revise(record_id, body, operation_id, expected_revision, reason=reason)

    @server.tool(annotations=write)
    def memory_l_decide(record_id: str, action: Literal["admit", "promote", "adopt", "observe", "reject", "retract", "demote"],
                         operation_id: str, expected_revision: str, reason: str, evidence: list[str],
                         authorization: str | None = None, joint_review: dict[str, str] | None = None) -> dict[str, Any]:
        """以 companion 角色作实际判断；晋升与共同采用核对已存在的明确授权。owner 初筛由操作员 CLI 落盘。"""
        return decide(kit.store(), record_id, action, operation_id=operation_id, expected_revision=expected_revision,
                      actor="companion", reason=reason, evidence=evidence, authorization=authorization, joint_review=joint_review)

    @server.tool(annotations=write)
    def memory_l_ingest_markdown(path: str, carrier: str, source_id: str, scope: str = "unknown") -> dict[str, Any]:
        """显式导入工作区内选定端口的 Markdown 全文，保持未准入与学习初筛闸门；不扫描源端数据库。"""
        source = kit.inside(kit.workspace(), kit.workspace() / path)
        return ingest_markdown(kit.store(), source, carrier=carrier, source_id=source_id, scope=scope)

    @server.tool(annotations=write)
    def memory_l_reflect_prepare(tier: Literal["quick", "deep", "meta"], operation_id: str, query: str = "",
                                  source_files: list[str] | None = None) -> dict[str, Any]:
        """保存带版本的实际反思输入，由当前载体回读与思考；未选端口材料不会开放学习。"""
        sources = [str(kit.inside(kit.workspace(), kit.workspace() / path)) for path in (source_files or [])]
        return prepare_reflection(kit.store(), tier, operation_id, query, source_files=sources)

    class ReflectionOutput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        kind: Literal["reflection", "calibration", "lesson", "framework", "exemplar", "tension", "relationship", "self_evaluation", "signal"]
        title: str = "反思记录"
        body: str = Field(min_length=1)
        carrier: str = "mcp"

    @server.tool(annotations=write)
    def memory_l_reflect_commit(session_id: str, outputs: list[ReflectionOutput], operation_id: str) -> dict[str, Any]:
        """保存实际反思的完整输出，保持未准入及来源约束，后续选择与发布分别执行。"""
        return commit_reflection(kit.store(), session_id, [item.model_dump() for item in outputs], operation_id)

    @server.tool(annotations=read)
    def memory_l_target_state(destination: Literal["diary", "growth", "calibration"]) -> dict[str, Any]:
        """读取准备发布的现有 Markdown 文件版本。"""
        kit.ensure_initialized()
        return target_state(kit.workspace(), destination)

    @server.tool(annotations=write)
    def memory_l_publish(record_id: str, destination: Literal["diary", "calibration"], operation_id: str,
                          expected_revision: str, expected_target_revision: str, reason: str, evidence: list[str]) -> dict[str, Any]:
        """按自主权限完整追加日记或普通 lesson；成长及人格校准的正式发布由操作员 CLI 核对共同决定。"""
        return publish(kit.store(), kit.workspace(), record_id, destination, operation_id=operation_id,
                       expected_revision=expected_revision, expected_target_revision=expected_target_revision,
                       actor="companion", reason=reason, evidence=evidence)

    @server.tool(annotations=write)
    def memory_l_write_manifest() -> dict[str, Any]:
        """生成正式原文及运行代码的迁移清单，核对来源与引用；不暂存、提交或推送 Git。"""
        from integrity import write_manifest
        kit.ensure_initialized()
        assets = write_manifest(kit.workspace())
        return {"files": len(assets["files"]), "record_files": assets["record_files"]}

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
