from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .agent_adapter import build_agent_run_request, default_agent_adapter_registry
from .agent_pack import prepare_context_pack
from .config import load_config, resolve_agent_profile
from .errors import AIWorkflowError
from .graph import Neo4jGraphStore
from .ingest import ingest_repo
from .projects import config_for_project, resolve_project
from .run_store import RunEventRecord, RunRecord, RunStore, run_store_root_for_output_dir
from .state import ContextPack
from .verify import run_verification, verification_summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AIWorkflowError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiworkflow", description="AI Workflow / Agent OS MVP")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径，默认读取 AIWORKFLOW_CONFIG 或 config/workflow.yaml")
    sub = parser.add_subparsers(required=True)

    doctor = sub.add_parser("doctor", help="检查本机运行环境")
    doctor.set_defaults(func=cmd_doctor)

    ingest = sub.add_parser("ingest", help="索引目标仓库到 Neo4j 图谱")
    ingest.add_argument("--repo", type=Path, default=None)
    ingest.add_argument("--project", default=None, help="从 Project Registry 读取目标仓库")
    ingest.add_argument("--no-clear", action="store_true", help="不清空该仓库旧索引")
    ingest.set_defaults(func=cmd_ingest)

    verify = sub.add_parser("verify", help="执行配置中的校验命令")
    verify.add_argument("--repo", type=Path, default=None)
    verify.add_argument("--project", default=None, help="从 Project Registry 读取目标仓库")
    verify.set_defaults(func=cmd_verify)

    prepare = sub.add_parser("prepare", help="生成给 Codex/Claude Code 使用的上下文任务包")
    prepare.add_argument("--repo", type=Path, default=None)
    prepare.add_argument("--project", default=None, help="从 Project Registry 读取目标仓库")
    prepare.add_argument("--query", required=True)
    prepare.add_argument("--agent", default=None, help="目标 Agent Profile，默认读取配置中的 agent.default")
    prepare.set_defaults(func=cmd_prepare)

    agent = sub.add_parser("agent", help="实验性 Agent runtime 命令")
    agent_sub = agent.add_subparsers(required=True)
    agent_run = agent_sub.add_parser("run", help="运行已有 Context Pack")
    agent_run.add_argument("run_id")
    agent_run.add_argument("--adapter", default=None, help="覆盖 Agent Profile 中的 adapter")
    agent_run.set_defaults(func=cmd_agent_run)

    runs = sub.add_parser("runs", help="查询 Run Store 运行记录")
    runs_sub = runs.add_subparsers(required=True)
    runs_list = runs_sub.add_parser("list", help="列出运行记录")
    runs_list.add_argument("--project", default="", help="按项目过滤")
    runs_list.add_argument("--limit", type=int, default=None, help="最多显示最近 N 条")
    runs_list.set_defaults(func=cmd_runs_list)

    runs_show = runs_sub.add_parser("show", help="显示单条运行记录")
    runs_show.add_argument("run_id")
    runs_show.set_defaults(func=cmd_runs_show)

    runs_events = runs_sub.add_parser("events", help="显示某次运行的事件记录")
    runs_events.add_argument("run_id")
    runs_events.add_argument("--type", dest="event_type", default="", help="按事件大类过滤")
    runs_events.add_argument("--source", default="", help="按事件来源过滤")
    runs_events.add_argument("--limit", type=int, default=None, help="最多显示最近 N 条")
    runs_events.set_defaults(func=cmd_runs_events)
    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print("AI Workflow Doctor")
    print(f"- Python: {sys.version.split()[0]}")
    docker = shutil.which("docker")
    print(f"- Docker: {docker or '未找到'}")
    print(f"- Neo4j URI: {config.neo4j.uri}")
    print(f"- Context budget: {config.context.budget_chars} chars")
    print(f"- Search limit: {config.context.search_limit}")
    print(f"- Default agent: {config.agent.default}")
    print(f"- Projects: {len(config.projects)}")
    _check_python_dependency("langgraph", "LangGraph")
    _check_python_dependency("llama_index", "LlamaIndex")
    _check_python_dependency("neo4j", "Neo4j Python driver")
    if not Path(".env").exists():
        print("- .env: 未找到，当前会使用环境变量或示例配置")
    try:
        store = Neo4jGraphStore(config.neo4j)
        store.ping()
        store.close()
        print("- Neo4j: 连接成功")
    except Exception as exc:  # noqa: BLE001
        print(f"- Neo4j: 未就绪 ({exc})")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo, config, _agent, _project = _resolve_command_project(args, config)
    store = Neo4jGraphStore(config.neo4j)
    try:
        store.ping()
        report = ingest_repo(repo, config, store, clear=not args.no_clear)
    finally:
        store.close()
    print(f"索引完成: repo_id={report.repo_id}")
    print(f"- files: {report.files_indexed}")
    print(f"- symbols: {report.symbols_indexed}")
    print(f"- documents: {report.documents_indexed}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo, config, _agent, _project = _resolve_command_project(args, config)
    results = run_verification(repo, config.verification)
    summary = verification_summary(results)
    for item in results:
        print(f"[{'PASS' if item.passed else 'FAIL'}] {item.name} ({item.exit_code})")
    return 0 if summary["passed"] else 1


def cmd_prepare(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo, config, agent, project = _resolve_command_project(args, config)
    store = Neo4jGraphStore(config.neo4j)
    try:
        store.ping()
        state = prepare_context_pack(repo, args.query, config, store, agent=args.agent or agent, project=project)
    finally:
        store.close()
    print(state.final_report)
    print(f"\n运行产物: {state.repo_meta['output_dir']}")
    return 0


def cmd_agent_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    run_store = RunStore(run_store_root_for_output_dir(config.workflow.output_dir))
    prepare_record = run_store.find(args.run_id)
    if prepare_record is None:
        raise AIWorkflowError(f"未找到运行记录: {args.run_id}")

    manifest_path = _manifest_path_for_record(prepare_record)
    if manifest_path is None:
        raise AIWorkflowError(f"运行记录缺少 manifest artifact: {args.run_id}")
    if not manifest_path.exists():
        raise AIWorkflowError(f"manifest 文件不存在: {manifest_path}")

    context_pack = ContextPack.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    profile = resolve_agent_profile(config, context_pack.agent)
    request = build_agent_run_request(
        context_pack,
        adapter=args.adapter,
        profile=profile,
        artifacts=prepare_record.artifacts,
    )
    try:
        adapter = default_agent_adapter_registry().resolve(context_pack.agent, adapter=request.adapter)
    except LookupError as exc:
        raise AIWorkflowError(str(exc)) from exc

    result = adapter.run_task(request)
    for event in result.events:
        run_store.append_event(RunEventRecord.from_agent_event(event, source=result.adapter))
    run_store.append(
        RunRecord(
            run_id=result.run_id,
            run_type="agent",
            status=result.status,
            project=prepare_record.project,
            repo_id=prepare_record.repo_id,
            repo_path=context_pack.repo_path,
            query=context_pack.query,
            task_type=context_pack.task_type,
            agent=context_pack.agent,
            output_dir=prepare_record.output_dir,
            artifacts=result.artifacts,
            started_at=result.started_at,
            finished_at=result.finished_at,
            metadata={
                "adapter": result.adapter,
                "summary": result.summary,
                "error": result.error,
            },
        )
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status in {"succeeded", "dry_run"} else 1


def cmd_runs_list(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    run_store = RunStore(run_store_root_for_output_dir(config.workflow.output_dir))
    records = run_store.list(project=args.project, limit=args.limit)
    if not records:
        print("未找到运行记录。")
        return 0
    for record in records:
        project = record.project or "-"
        print(f"{record.run_id}\t{record.status}\t{project}\t{record.agent}\t{record.task_type}\t{record.output_dir}")
    return 0


def cmd_runs_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    run_store = RunStore(run_store_root_for_output_dir(config.workflow.output_dir))
    record = run_store.find(args.run_id)
    if record is None:
        print(f"未找到运行记录: {args.run_id}", file=sys.stderr)
        return 1
    print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_runs_events(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    run_store = RunStore(run_store_root_for_output_dir(config.workflow.output_dir))
    events = run_store.list_events(
        run_id=args.run_id,
        event_type=args.event_type,
        source=args.source,
        limit=args.limit,
    )
    print(json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=2))
    return 0


def _resolve_command_project(args: argparse.Namespace, config):
    if args.project and args.repo:
        raise AIWorkflowError("不能同时提供 --repo 和 --project。")
    if args.project:
        selection = resolve_project(config, args.project)
        return selection.repo, config_for_project(config, selection), selection.agent, selection.name
    if args.repo:
        return args.repo, config, None, ""
    raise AIWorkflowError("必须提供 --repo 或 --project。")


def _manifest_path_for_record(record: RunRecord) -> Path | None:
    for artifact in record.artifacts:
        if artifact.name == "manifest" or artifact.kind == "manifest":
            path = Path(artifact.path)
            if path.exists() or path.is_absolute():
                return path
            output_relative = Path(record.output_dir) / path
            if output_relative.exists():
                return output_relative
            return path
    return None


def _check_python_dependency(module_name: str, label: str) -> None:
    found = importlib.util.find_spec(module_name) is not None
    print(f"- {label}: {'已安装' if found else '未安装'}")


if __name__ == "__main__":
    raise SystemExit(main())
