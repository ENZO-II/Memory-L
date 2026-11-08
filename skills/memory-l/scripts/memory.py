#!/usr/bin/env python3
"""Standard-library CLI. Explicit workspace, portable original Markdown."""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Memory-L")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--name", required=True)
    init.add_argument("--owner", required=True)
    migration = commands.add_parser("migrate-plan")
    migration.add_argument("--input", required=True, help="Explicit legacy Markdown mapping JSON")
    migration.add_argument("--output", required=True, type=Path)
    commands.add_parser("migrate-apply").add_argument("--plan", required=True, type=Path)
    commands.add_parser("migrate-verify")
    commands.add_parser("status")
    for name in ("save", "revise", "decide", "authorize", "reflect-commit", "publish"):
        commands.add_parser(name).add_argument("--input", required=True, help="JSON file or - for stdin")
    commands.add_parser("manifest")
    commands.add_parser("stage")
    check = commands.add_parser("check")
    group = check.add_mutually_exclusive_group()
    group.add_argument("--git-index", action="store_true")
    group.add_argument("--git-ref")
    connection = commands.add_parser("connections")
    connection.add_argument("--python")
    read = commands.add_parser("read")
    read.add_argument("id")
    core = commands.add_parser("core-file")
    core.add_argument("name")
    core.add_argument("--offset", type=int, default=0)
    core.add_argument("--max-chars", type=int, default=20000)
    listing = commands.add_parser("list")
    listing.add_argument("kind")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--include-raw", action="store_true")
    search.add_argument("--refresh", action="store_true")
    context = commands.add_parser("context")
    context.add_argument("--query", default="")
    context.add_argument("--purpose", choices=["working_evidence", "learning", "profile", "archive"], default="working_evidence")
    context.add_argument("--offset", type=int, default=0)
    context.add_argument("--limit", type=int, default=20)
    context.add_argument("--max-chars", type=int, default=12000)
    prepare = commands.add_parser("reflect-prepare")
    prepare.add_argument("--tier", choices=["quick", "deep", "meta"], required=True)
    prepare.add_argument("--operation-id", required=True)
    prepare.add_argument("--query", default="")
    prepare.add_argument("--source-file", action="append", default=[])
    prepare.add_argument("--max-chars", type=int, default=12000)
    target = commands.add_parser("target-state")
    target.add_argument("destination", choices=["diary", "growth", "calibration"])
    ingest = commands.add_parser("ingest-markdown")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--carrier", required=True)
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--scope", default="unknown")
    args = parser.parse_args(argv)
    os.environ["MEMORY_L_WORKSPACE"] = str(args.workspace.resolve())
    import kit
    try:
        if args.command == "init":
            result = kit.initialize(args.name, args.owner)
        elif args.command == "status":
            result = kit.status()
        elif args.command == "migrate-plan":
            from legacy_migration import prepare
            result = prepare(args.input, args.output)
        elif args.command == "migrate-apply":
            from legacy_migration import apply
            result = apply(args.plan)
        elif args.command == "migrate-verify":
            from legacy_migration import verify
            result = verify()
        else:
            kit.ensure_initialized()
            if args.command in {"save", "revise", "decide", "authorize", "reflect-commit", "publish"}:
                raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
                document = json.loads(raw)
                if not isinstance(document, dict):
                    raise ValueError("Input must be a JSON object")
                target_store = kit.store()
                if args.command == "save":
                    result = kit.save(document)
                elif args.command == "revise":
                    result = target_store.revise(document["id"], document["body"], document["operation_id"], document["expected_revision"], reason=document["reason"])
                elif args.command == "decide":
                    from memory_core.policy import decide
                    result = decide(target_store, document["id"], document["action"], operation_id=document["operation_id"],
                        expected_revision=document["expected_revision"], actor=document.get("actor", "companion"), reason=document["reason"],
                        evidence=document["evidence"], authorization=document.get("authorization"), joint_review=document.get("joint_review"))
                elif args.command == "authorize":
                    from memory_core.policy import authorize
                    result = authorize(target_store, document["authority"], operation_id=document["operation_id"], actor=document["actor"], reason=document["reason"], evidence=document["evidence"])
                elif args.command == "reflect-commit":
                    from memory_core.context import commit_reflection
                    result = commit_reflection(target_store, document["session_id"], document["outputs"], document["operation_id"])
                else:
                    from memory_core.dispatch import publish
                    result = publish(target_store, kit.workspace(), document["id"], document["destination"], operation_id=document["operation_id"],
                        expected_revision=document["expected_revision"], expected_target_revision=document["expected_target_revision"],
                        actor=document.get("actor", "companion"), reason=document["reason"], evidence=document["evidence"])
            elif args.command == "read":
                result = kit.store().read(args.id)
            elif args.command == "core-file":
                result = kit.core_file(args.name, args.offset, args.max_chars)
            elif args.command == "list":
                result = kit.listing(args.kind, args.offset, args.limit)
            elif args.command == "search":
                result = kit.search(args.query, args.limit, args.include_raw, args.refresh)
            elif args.command == "context":
                from memory_core.context import context_packet
                result = context_packet(kit.store(), args.query, args.max_chars, args.limit, args.purpose, args.offset)
            elif args.command == "reflect-prepare":
                from memory_core.context import prepare_reflection
                result = prepare_reflection(kit.store(), args.tier, args.operation_id, args.query, args.max_chars, args.source_file)
            elif args.command == "target-state":
                from memory_core.dispatch import target_state
                result = target_state(kit.workspace(), args.destination)
            elif args.command == "ingest-markdown":
                from memory_core.ingest import ingest_markdown
                result = ingest_markdown(kit.store(), args.file, carrier=args.carrier, source_id=args.source_id, scope=args.scope)
            elif args.command in {"manifest", "check"}:
                from integrity import write_manifest, verify_assets, verify_git_assets
                assets = (write_manifest if args.command == "manifest" else verify_assets)(kit.workspace())
                result = {"status": "markdown_verified", "files": len(assets["files"]), "record_files": assets["record_files"]}
                if args.command == "check" and (args.git_index or args.git_ref):
                    result["git"] = verify_git_assets(kit.workspace(), assets, index=args.git_index, ref=args.git_ref)
            elif args.command == "stage":
                result = kit.stage_assets()
            elif args.command == "connections":
                result = kit.connections(args.python)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
