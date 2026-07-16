# 演进路线图

当前工程已经从单纯 AI workflow demo 进入 Agent OS 单体内核 MVP 阶段。后续演进应继续保持小步、可测试、可审阅。

## 短期

- 强化 Context 选择逻辑，提升检索片段排序和上下文预算控制。
- 完善 Prompt 模板体系，让不同任务类型拥有更明确的生成和评审规则。
- 增加更多 C++ / C# / Lua 索引测试样例。
- 让 `final_report.md` 更适合人类审阅，并保持 `state.json` 适合机器分析。
- 继续保证 mock 模式离线可跑通。

## 中期

- 建设 Hybrid Search：关键词、符号、文档、图谱、Recent、Embedding 共同排序。
- 支持增量索引，避免每次 ingest 全量重建目标仓库知识。
- 将 Review 拆成更细的评审维度，例如架构、性能、测试、线程、安全。
- 扩展 `CommandPolicy`，记录更完整的命令审计信息。
- 为 Tool Service / MCP 执行入口预留统一权限策略。

## 长期

- 建设 Tool Service，将 Git、Perforce、Jenkins、UE、Unity、Jira 等工具统一纳入权限和审计。
- 建设 Agent Adapter，统一 Claude Code、Codex、OpenHands、Gemini 和内部 Agent 的运行接口。
- 接入 IDE Layer，让 VSCode、Rider、Visual Studio、CLion 等只作为入口，而不是平台核心。
- 建设游戏引擎专属知识图谱，包括 UE Reflection、Blueprint Graph、Asset Graph、Shader Include、Crash Symbol、Profiler 数据。
- 在接口稳定后再考虑服务化拆分、队列、Dashboard 和企业级部署。

## 暂不投入

- 暂不拆分 Go / ASP.NET Core 微服务。
- 暂不上 K8S、NATS、Kafka、MinIO、Grafana 等平台设施。
- 暂不引入 Milvus / OpenSearch 作为默认依赖。
- 暂不直接接 Jenkins / Jira / Perforce / UE / Unity MCP。
- 暂不训练自有 Coding Model。
- 暂不把 Agent 能力绑定到某一个具体 IDE 或具体模型。

## 判断标准

每次演进都应回答三个问题：

- 是否提升了 Agent 可获得的有效 Context？
- 是否让 Tool / Verification 更受控、更可审计？
- 是否保持了本地 MVP 的可运行性和 mock 测试闭环？
