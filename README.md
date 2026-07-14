# AI 编程工作流 MVP

这是一个 CLI 优先的 AI 编程流水线骨架，目标是把“需求输入 → 图谱检索 → 上下文组装 → 模型生成 → 校验闭环 → 报告产出”做成可运行的最小版本。

第一版面向通用代码仓库：

- 使用 Neo4j 存储最小代码图谱：`File`、`Symbol`、`Document`、`Rule`。
- 保留 LangGraph/LlamaIndex 依赖入口；当前 MVP 用轻量状态机和 Neo4j 图谱适配器跑通主链路。
- 使用 OpenAI-compatible / LiteLLM 网关调用模型。
- 默认不直接修改目标仓库，只生成可审阅的 `change.patch`。
- 校验命令从 `config/workflow.yaml` 读取，并限制明显破坏性命令。

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

如果暂时没有真实模型网关，把 `.env` 里的 `MODEL_NAME` 保持为 `mock`，或运行时加 `--mock-model`。

## CLI

```powershell
aiworkflow doctor
aiworkflow ingest --repo G:\path\to\repo
aiworkflow verify --repo G:\path\to\repo
aiworkflow run --repo G:\path\to\repo --query "修复登录失败时没有错误提示的问题" --mock-model
```

完整运行后会在 `runs/<run_id>/` 生成：

- `state.json`：完整状态快照
- `context.md`：组装后的模型上下文
- `change.patch`：模型输出的可审阅 patch
- `verify_report.json`：校验命令结果
- `final_report.md`：最终报告

## 配置

默认读取 `AIWORKFLOW_CONFIG`，其次读取 `config/workflow.yaml`，最后读取 `config/workflow.example.yaml`。

关键配置：

- `repo.include` / `repo.exclude`：索引文件范围
- `knowledge.docs_paths`：文档、规则、技能模板位置
- `neo4j.uri/user/password`：Neo4j 连接信息
- `model.base_url/api_key/model`：LiteLLM / OpenAI-compatible 网关
- `verification.commands`：校验命令
- `workflow.max_retries`：校验失败后的自动修复轮数

## 当前边界

这是 MVP，不会自动应用 patch，也不会替你提交代码。图谱检索使用 Neo4j 的最小模型，后续可以继续增强为完整 LlamaIndex GraphRAG、AST 多语言解析、双 Agent 评审和 IDE 插件入口。
