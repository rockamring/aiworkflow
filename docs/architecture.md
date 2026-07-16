# 当前工程架构

当前工程是一个 CLI-first Agent OS 单体内核 MVP。它不是 Cursor、Claude Code 这类交互式 IDE Agent，也不是已经拆分好的企业微服务平台；它的目标是在本地命令行里跑通一条可审阅、可验证、可扩展的 AI 软件工程流水线。

## 架构定位

系统围绕两件事展开：

- 给 Agent 提供更准确的 Context。
- 给 Agent 提供受控的 Tool / Verification 能力。

现阶段所有核心能力都在一个 Python 包内实现，通过清晰模块边界模拟未来服务边界。后续可以把稳定接口拆分为独立服务，但当前不急于引入微服务、K8S、消息总线或 IDE 插件。

## 当前分层

```text
CLI Layer
  aiworkflow doctor / ingest / verify / run

Workflow Layer
  节点化执行链路、重试、产物落盘

Context Layer
  任务分类、知识标签、检索编排、上下文预算、Prompt 组装

Search / Knowledge Layer
  GraphStore 抽象、Neo4j / InMemory、File / Symbol / Document / Rule

Prompt / Review Layer
  prompts/ 模板、任务指导、独立 review pass

Permission / Verification Layer
  CommandPolicy、安全策略、验证命令、验证报告

Model Gateway Layer
  mock 模型、OpenAI-compatible 模型接口
```

## 当前不是哪些东西

- 不是完整的 Agent Runtime Adapter 平台，目前没有统一接入 Claude Code、Codex、OpenHands 等运行时。
- 不是 IDE 插件，目前入口是 CLI。
- 不是企业级 Tool Service，目前只对 verification command 做受控执行。
- 不是完整 GraphRAG 系统，目前是最小 Neo4j 图谱和轻量搜索抽象。
- 不是游戏引擎深度索引系统，目前只做 C++ / C# / Lua 的轻量符号提取，尚未解析 UE Reflection、Blueprint、Unity Asset 或 Perforce 图谱。

## 设计原则

- 保持 mock 模式离线可运行。
- 默认只生成可审阅产物，不直接修改目标仓库。
- 工作流产物统一写入 `runs/<run_id>/`。
- 验证命令从配置读取，并通过安全策略过滤。
- 文档、规则、Prompt 和运行状态都应可被审阅和索引。
