# 核心模块说明

本文记录当前 Agent OS 单体内核中的主要模块职责。模块边界优先服务后续演进，不代表当前已经是微服务。

## CLI 与配置

- `aiworkflow/cli.py` 提供 `doctor`、`ingest`、`verify`、`run` 四个命令入口。
- `aiworkflow/config.py` 负责读取 `.env`、`AIWORKFLOW_CONFIG`、`config/workflow.yaml` 和示例配置。
- `config/workflow.example.yaml` 定义仓库扫描范围、知识文档路径、Neo4j、模型、验证命令和工作流参数。

## Workflow

- `aiworkflow/workflow.py` 是节点化工作流编排入口。
- 当前节点包括 `classify`、`retrieve`、`build_prompt`、`generate`、`verify`、`prepare_retry`、`review`、`evaluate`、`report`。
- `NODE_REGISTRY` 是进程内节点注册表，先替代复杂 DAG 引擎。
- 工作流会写出 `context.md`、`change.patch`、`review_report.md`、`verify_report.json`、`state.json` 和 `final_report.md`。

## Context / Search / Prompt

- `aiworkflow/context.py` 负责任务分类、知识标签、检索调用、上下文预算和 Prompt 组装。
- `aiworkflow/search.py` 定义 `SearchService`、`SearchRequest`、`SearchResponse`，底层暂时复用 `GraphStore.search()`。
- `aiworkflow/prompt.py` 从 `prompts/` 目录加载系统 Prompt、任务 Prompt 和 Review Prompt。
- `prompts/tasks/` 按任务类型存放指导文本，例如 crash_fix、performance、feature、review、refactor。

## Knowledge Index

- `aiworkflow/ingest.py` 负责扫描目标仓库、读取文档、提取符号并写入图谱。
- `aiworkflow/graph.py` 定义 `GraphStore` 协议，以及 `Neo4jGraphStore` 和 `InMemoryGraphStore`。
- 当前图谱对象包括 `File`、`Symbol`、`Document`、`Rule`。
- 当前轻量支持 Python、C++、C#、Lua、Markdown、YAML、JSON 等文件。

## Permission / Verification / Review

- `aiworkflow/policy.py` 定义 `CommandPolicy`，用于判断命令是否允许执行。
- `aiworkflow/verify.py` 读取验证命令并执行，通过 `CommandPolicy` 拒绝明显破坏性命令。
- `aiworkflow/review.py` 在生成 patch 后执行独立 review pass。
- `aiworkflow/state.py` 记录工作流状态、检索统计、上下文摘要、验证结果、评审结果和 evaluation 指标。

## Model Gateway

- `aiworkflow/model_gateway.py` 提供 `ModelClient` 抽象。
- `MockModelClient` 用于离线测试和本地闭环。
- `OpenAICompatibleModelClient` 用于对接 OpenAI-compatible / LiteLLM 风格接口。
