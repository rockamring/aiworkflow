# AI Workflow / Agent OS MVP

这是一个 CLI-first 的 AI Workflow / Agent OS 单体内核 MVP。它的目标不是替代 Codex / Claude Code 写代码，而是把 Codex、Claude Code、OpenHands 等 Agent 视为可替换插件，由平台沉淀统一的 Context、Prompt、Knowledge、Tool、Permission 和 Workflow 能力。

当前第一阶段先落地 **Context Pack / Prompt Pack** 能力：在 Agent 开始工作前，把任务相关的代码、文档、规则、符号和验证命令整理成高质量任务包。

第一版面向通用代码仓库：

- 使用 Neo4j 存储最小代码图谱：`File`、`Symbol`、`Document`、`Rule`。
- 通过 `prepare` 生成 Agent 可直接消费的 Context Pack。
- 默认不修改目标仓库、不调用模型、不执行验证命令。
- 验证命令只从 `config/workflow.yaml` 读取，并写入任务包供 Agent 和人工参考。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
Copy-Item .env.example .env
Copy-Item config\workflow.example.yaml config\workflow.yaml
docker compose up -d neo4j
aiworkflow doctor
```

## CLI

```powershell
aiworkflow doctor
aiworkflow ingest --repo G:\path\to\repo
aiworkflow prepare --repo G:\path\to\repo --query "修复登录失败时没有错误提示的问题" --agent codex
aiworkflow agent run <run_id> --adapter dry_run
aiworkflow verify --repo G:\path\to\repo
aiworkflow runs list
aiworkflow runs show <run_id>
aiworkflow runs events <run_id>
```

配置 `projects` 后，也可以使用项目别名：

```powershell
aiworkflow ingest --project my_game
aiworkflow prepare --project my_game --query "修复登录失败时没有错误提示的问题"
aiworkflow verify --project my_game
```

`prepare` 完成后会在 `runs/<run_id>/` 生成：

- `agent_prompt.md`：直接交给 Codex / Claude Code 的完整 Prompt。
- `context.md`：被选中的上下文片段。
- `manifest.json`：机器可读 Context Pack。
- `state.json`：分类、检索、预算和输出过程记录。
- `final_report.md`：面向人的运行摘要。

同时会在 `runs/index.jsonl` 追加一条 Run Store 摘要记录，并在 `runs/events.jsonl` 追加一条 `prepare.finished` 事件，便于后续查询、审计和复现。

## 配置

默认读取 `AIWORKFLOW_CONFIG`，其次读取 `config/workflow.yaml`，最后读取 `config/workflow.example.yaml`。

关键配置：

- `repo.include` / `repo.exclude`：索引文件范围。
- `knowledge.docs_paths`：文档、规则、技能模板位置。
- `neo4j.uri/user/password`：Neo4j 连接信息。
- `context.budget_chars`：Context Pack 的字符预算。
- `context.search_limit`：检索片段数量上限。
- `agent.default` / `agent.profiles`：目标 Agent 的结构化 Profile，包括 Prompt 风格、adapter、command、I/O 模式、默认权限和运行限制。
- `verification.commands`：写入任务包的建议验证命令。
- `workflow.output_dir`：运行产物目录。
- `projects.<name>`：项目别名、仓库路径、默认 Agent 和项目级输出目录。

Agent Profile 之所以结构化，是为了让 Codex、Claude Code、OpenHands 等 Agent 作为可替换插件接入时，共用同一个 adapter、命令、I/O、权限和限制配置入口，而不是把这些运行时差异散落到各个 Adapter 实现里。

## 当前边界

这是 Agent OS 的第一阶段 MVP。`prepare` 不会自动应用 patch，也不会自动提交代码；只有显式执行 `aiworkflow agent run <run_id>` 时，才会启动配置中的 Agent Adapter。后续可以继续增强为 Hybrid Search、增量索引、Tool Service、MCP 接入和企业权限审计层。
