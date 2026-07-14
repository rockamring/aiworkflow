from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import AppConfig, load_config
from .errors import AIWorkflowError
from .graph import Neo4jGraphStore
from .ingest import ingest_repo
from .model_gateway import make_model_client
from .verify import run_verification, verification_summary
from .workflow import run_workflow


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
    parser = argparse.ArgumentParser(prog="aiworkflow", description="AI 编程工作流 MVP")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径，默认读取 AIWORKFLOW_CONFIG 或 config/workflow.yaml")
    sub = parser.add_subparsers(required=True)

    doctor = sub.add_parser("doctor", help="检查本机运行环境")
    doctor.set_defaults(func=cmd_doctor)

    ingest = sub.add_parser("ingest", help="索引目标仓库到 Neo4j 图谱")
    ingest.add_argument("--repo", type=Path, required=True)
    ingest.add_argument("--no-clear", action="store_true", help="不清空该仓库旧索引")
    ingest.set_defaults(func=cmd_ingest)

    verify = sub.add_parser("verify", help="执行配置中的校验命令")
    verify.add_argument("--repo", type=Path, required=True)
    verify.set_defaults(func=cmd_verify)

    run = sub.add_parser("run", help="执行完整 AI 工作流")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--query", required=True)
    run.add_argument("--mock-model", action="store_true", help="强制使用 mock 模型，不访问模型网关")
    run.set_defaults(func=cmd_run)
    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print("AI Workflow Doctor")
    print(f"- Python: {sys.version.split()[0]}")
    docker = shutil.which("docker")
    print(f"- Docker: {docker or '未找到'}")
    print(f"- Neo4j URI: {config.neo4j.uri}")
    print(f"- Model: {config.model.model}")
    _check_python_dependency("langgraph", "LangGraph")
    _check_python_dependency("llama_index", "LlamaIndex")
    _check_python_dependency("neo4j", "Neo4j Python driver")
    if not Path(".env").exists():
        print("- .env: 未找到，当前会使用环境变量或示例配置")
    _check_model_config(config)
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
    store = Neo4jGraphStore(config.neo4j)
    try:
        store.ping()
        report = ingest_repo(args.repo, config, store, clear=not args.no_clear)
    finally:
        store.close()
    print(f"索引完成: repo_id={report.repo_id}")
    print(f"- files: {report.files_indexed}")
    print(f"- symbols: {report.symbols_indexed}")
    print(f"- documents: {report.documents_indexed}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    results = run_verification(args.repo, config.verification)
    summary = verification_summary(results)
    for item in results:
        print(f"[{'PASS' if item.passed else 'FAIL'}] {item.name} ({item.exit_code})")
    return 0 if summary["passed"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    store = Neo4jGraphStore(config.neo4j)
    model = make_model_client(config.model, force_mock=args.mock_model)
    try:
        store.ping()
        state = run_workflow(args.repo, args.query, config, store, model)
    finally:
        store.close()
    print(state.final_report)
    print(f"\n运行产物: {state.repo_meta['output_dir']}")
    return 0 if state.verify_report.get("passed") else 1


def _check_model_config(config: AppConfig) -> None:
    if config.model.model.lower().startswith("mock"):
        print("- Model gateway: mock 模式")
        return
    missing = []
    if not config.model.base_url:
        missing.append("MODEL_BASE_URL")
    if not config.model.api_key:
        missing.append("MODEL_API_KEY")
    if missing:
        print(f"- Model gateway: 配置缺失 ({', '.join(missing)})")
    else:
        print(f"- Model gateway: {config.model.base_url}")


def _check_python_dependency(module_name: str, label: str) -> None:
    found = importlib.util.find_spec(module_name) is not None
    print(f"- {label}: {'已安装' if found else '未安装'}")


if __name__ == "__main__":
    raise SystemExit(main())
