# 当前工程架构

当前工程是一个 CLI-first AI Workflow / Agent OS 单体内核 MVP。它不是 Cursor、Claude Code 这类交互式 IDE Agent，也不是完整企业微服务平台；它的目标是把 Codex、Claude Code、OpenHands 等 Agent 作为可替换插件，由平台统一沉淀 Context、Prompt、Knowledge、Tool、Permission 和 Workflow 能力。

## 架构定位

当前阶段先围绕两件事展开：

- 给 Agent 提供更准确的 Context。
- 给 Agent 提供明确的 Prompt、规则和验证线索。

后续平台层会继续扩展 Agent Adapter、Tool Service、Permission Service、Memory 和 Evaluation，而不是把项目限制为单纯 Context Engine。

现阶段所有核心能力都在一个 Python 包内实现，通过清晰模块边界模拟未来服务边界。后续可以把稳定接口拆分为独立服务，但当前不急于引入微服务、K8S、消息总线或 IDE 插件。

## 当前分层

```text
CLI Layer
  aiworkflow doctor / ingest / prepare / verify

Prepare Layer
  classify -> retrieve -> build_context_pack -> render_agent_prompt -> write_outputs

Context Layer
  任务分类、知识标签、检索编排、上下文预算

Search / Knowledge Layer
  GraphStore 抽象、Neo4j / InMemory、File / Symbol / Document / Rule

Prompt Pack / Context Pack Layer
  Agent Profile、任务指导、Context Pack manifest、agent_prompt.md

Permission / Verification Layer
  CommandPolicy、安全策略、验证命令声明、独立 verify CLI

Future Platform Layer
  Agent Adapter、Tool Service、Permission Service、Memory、Evaluation
```

## 当前不是哪些东西

- 当前不是模型生成 patch 的闭环系统，第一阶段主线不调用模型。
- 不是完整 Agent Runtime Adapter 平台，目前不直接托管 Codex、Claude Code 或 OpenHands。
- 不是 IDE 插件，目前入口是 CLI。
- 不是企业级 Tool Service，目前只把验证命令作为建议写入任务包，`verify` 仍可独立执行。
- 不是完整 GraphRAG 系统，目前是最小 Neo4j 图谱和轻量搜索抽象。

## 设计原则

- 保持本地离线测试可运行。
- 当前默认只生成可审阅 Context Pack，不直接修改目标仓库。
- 工作流产物统一写入 `runs/<run_id>/`。
- 验证命令从配置读取，并通过安全策略过滤后才可由 `verify` 执行。
- 文档、规则、Prompt 和运行状态都应可被审阅和索引。
