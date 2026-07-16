# 核心原则

本文记录 AI Workflow / Agent OS 项目最需要长期保留的设计观点。后续无论实现形态如何变化，都应优先保护这些原则。

## AI 是平台，Agent 是插件

不要把能力绑定到某一个具体 Agent、模型或 IDE。Claude Code、Codex、Gemini、OpenHands 或未来内部 Agent，都应被视为可替换的运行时。

平台真正要沉淀的是统一的上下文、知识、工具、流程、权限和评估能力。

## 公司资产是 Context、Knowledge、Tool、Workflow、Memory

模型会变化，Agent 会变化，IDE 也会变化。企业长期可复用的资产应该是：

- `Context`：任务所需的最小有效上下文。
- `Knowledge`：架构、规范、设计文档、ADR、FAQ、经验沉淀。
- `Tool`：Git、构建、测试、CI、引擎、资产、Issue 等受控工具能力。
- `Workflow`：从需求、分析、生成、验证、评审到报告的可审计流程。
- `Memory`：开发者、团队、项目和任务层面的长期偏好与约束。

## 游戏公司优先建设游戏研发知识图谱

通用 AI Coding 能力不是游戏公司的核心差异。游戏公司更应该优先建设：

- 引擎相关知识：UE Reflection、Blueprint、Unity 组件和工程结构。
- 资产相关知识：材质、贴图、Prefab、Addressable、Asset 依赖。
- Crash 相关知识：Crash Symbol、堆栈、最近提交、相关源码。
- Build 相关知识：UBT、UAT、BuildGraph、Jenkins、打包、Cook、Pak。
- 性能相关知识：RenderDoc、Unreal Insights、Unity Profiler、热点路径。

这些知识比“换一个更强模型”更能形成长期竞争力。

## 先做单体内核 MVP，再服务化

当前阶段应优先把模块边界、数据结构、运行产物和测试闭环做清楚。不要过早拆微服务，也不要过早引入 K8S、消息总线、对象存储或复杂运维体系。

当接口稳定、团队协作需求变强、运行规模变大后，再把 Context、Search、Tool、Workflow、Permission、Evaluation 等能力拆成独立服务。

## 先做深 Context 和 Search，再谈复杂 Agent 编排

Agent 编排的上限取决于上下文质量。当前优先级应该是：

1. 让系统知道任务真正需要哪些信息。
2. 让系统能从代码、文档、符号、图谱、Git、Crash、Build 中找到这些信息。
3. 让系统能排序、压缩并解释为什么选择这些上下文。
4. 在此基础上再引入多 Agent、DAG、自动 PR、IDE 插件和企业级工具治理。
