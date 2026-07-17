# AI Workflow 文档索引

这个目录是 AI Workflow / Agent OS 自身的项目知识库。它面向后续 Agent 检索、团队协作和架构演进记录，不是营销介绍，也不是完整用户手册。

当前工程定位是一个 CLI-first 的 AI Workflow / Agent OS 单体内核 MVP：先把 Context、Search、Prompt Pack、Permission、Knowledge Index 和 Context Pack 契约立住，再逐步演进到 Agent Adapter、Tool Service、Permission Service 和企业级平台。

## 推荐阅读顺序

1. [architecture.md](architecture.md)：先理解当前系统分层和边界。
2. [modules.md](modules.md)：再看各核心模块职责。
3. [workflow.md](workflow.md)：理解一次 `aiworkflow prepare` 的执行链路和产物。
4. [knowledge-index.md](knowledge-index.md)：了解代码、文档和规则如何进入知识索引。
5. [core-principles.md](core-principles.md)：记录必须长期保留的核心设计原则。
6. [project-onboarding.md](project-onboarding.md)：说明如何接入实际工程和多个工程。
7. [roadmap.md](roadmap.md)：查看下一阶段演进方向和暂不投入的范围。

## 写作约定

- 文档默认使用中文。
- 代码标识符、模块名、命令、协议名保持英文。
- 内容以可检索、可审阅、可演进为优先。
- 记录模块时必须同时回答“是什么”和“为什么这么做”：不要只列 API、文件和功能，也要说明它解决的架构问题、避免的耦合、保留的演进空间。
- 记录流程时必须说明设计取舍：为什么当前阶段这样排节点、为什么某些能力暂不做、为什么默认边界如此收缩。
- 记录 TODO / roadmap 时必须写清触发条件：什么情况下才值得推进，避免后续把“可做”误读成“现在就该做”。
- 当实现发生变化时，应同步更新对应文档，避免知识库和代码脱节。
