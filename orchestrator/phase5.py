"""Generate the evidence-backed report from a finished phase-4 run. The source run is never modified."""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI

from core.runtime import ROOT, error_summary, require_capabilities, settings, write_json
from core.usage import UsageRecorder
from report.agent import build_report, investigate, verify_report
from report.evidence import EvidenceStore
from report.render import render


def fingerprint(source):
    """Hash every file the report reads, so a mid-run change to the source is detected."""
    return {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob("*")) if path.is_file() and path.suffix in {".db", ".json", ".jsonl"}
            and not path.name.endswith(("-wal", "-shm"))}


async def execute(source, root, capability_dir, use_model):
    source, root = Path(source).resolve(), Path(root).resolve()
    if not (source / "phase4_result.json").is_file():
        raise ValueError("Source must be a phase-4 run directory")
    if root.exists():
        raise ValueError("Use a fresh phase5 directory")
    before = fingerprint(source)
    store = EvidenceStore(source)
    root.mkdir(parents=True)
    claims, trace, notes = {}, [], []
    if use_model:
        config = settings()
        capability = require_capabilities(capability_dir, config)
        async with AsyncOpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=120, max_retries=0) as client:
            with UsageRecorder(config, root):
                try:
                    step, trace = await investigate(client, config, capability, store)
                except Exception as error:
                    write_json(root / "phase5_result.json", {"passed": False, "error": error_summary(error, root)})
                    raise
        claims = {"issues": step.issues, "highlights": step.highlights}
        notes.append(f"问题与亮点由 {config['provider']} / {config['model']} 在证据门禁下撰写。")
    else:
        notes.append("未调用模型：问题清单与亮点为空，其余章节来自完整记录。")
    report = build_report(store, claims, notes)
    errors = verify_report(report, store)
    if fingerprint(source) != before:
        errors.append("来源运行目录在生成期间发生变化")
    context = json.loads((source / "run_context.json").read_text(encoding="utf-8"))
    model_path = Path(context["source_run"]) / "product_model.json"
    product = json.loads(model_path.read_text(encoding="utf-8"))["metadata"]["name"] if model_path.is_file() else "产品"
    write_json(root / "report.json", report)
    (root / "report.md").write_text(render(report, source, root, product), encoding="utf-8")
    write_json(root / "agent_trace.json", trace)
    write_json(root / "evidence_index.json", {ref: {key: value for key, value in record.items() if key != "data"}
                                              for ref, record in store.records.items()})
    result = {"passed": not errors and (not use_model or bool(report["sections"]["issues"] or report["sections"]["highlights"])),
              "errors": errors, "model_used": use_model, "source_run": str(source), "source_context_sha256": hashlib.sha256(
                  (source / "run_context.json").read_bytes()).hexdigest(), "source_files_unchanged": fingerprint(source) == before,
              "issues": len(report["sections"]["issues"]), "highlights": len(report["sections"]["highlights"]),
              "rejected_claims": len(report["rejected_claims"]), "silence_signals": len(report["silence_signals"]),
              "source_provider": context["configuration"]["provider"]}
    write_json(root / "phase5_result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run", type=Path, help="完成的阶段 4 运行目录")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--capability-run", type=Path, help="含 capability_profile.json 且与当前模型配置匹配的目录")
    parser.add_argument("--no-model", action="store_true", help="只生成不需要模型的章节")
    args = parser.parse_args()
    if not args.no_model and not args.capability_run:
        parser.error("使用模型时必须指定 --capability-run（能力文件需与当前提供商、模型、协议匹配）")
    root = args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase5-%Y%m%dT%H%M%S%fZ")
    result = asyncio.run(execute(args.source_run, root, args.capability_run, not args.no_model))
    print(f"阶段 5：{'PASS' if result['passed'] else 'FAIL'}；{Path(root).resolve() / 'phase5_result.json'}")
    for error in result["errors"]:
        print("  -", error)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
