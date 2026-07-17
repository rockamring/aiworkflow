# Prepare 执行链路

一次 `aiworkflow prepare` 会把开发者请求转成可直接交给 Codex / Claude Code 的 Context Pack。默认行为是不调用模型、不执行验证命令、不修改目标仓库。

为什么这样做：`prepare` 的核心价值是先解决“Agent 开始工作前应该知道什么”。把它设计成无副作用流程，可以让团队安全地反复调试检索、Prompt 和上下文预算，而不担心误改目标仓库或触发昂贵构建。

## 命令入口

```powershell
aiworkflow prepare --repo G:\path\to\repo --query "修复 Renderer crash" --agent codex
```

运行时会创建一个 `run_id`，并把所有产物写入 `runs/<run_id>/`。

如需显式启动 Agent runtime，可在 prepare 完成后执行：

```powershell
aiworkflow agent run <run_id>
```

这个命令会读取 `manifest.json` 还原 Context Pack，再交给配置中的 Agent Adapter；它是独立的副作用入口，不属于 prepare 默认链路。

## 节点顺序

```text
classify
  -> retrieve
  -> build_context
  -> render_agent_prompt
  -> build_context_pack
  -> write_outputs
```

这个顺序刻意把 `build_context` 放在 `render_agent_prompt` 前面，因为 Prompt 应该消费已经预算化、可审阅的上下文，而不是在渲染阶段临时搜索。`build_context_pack` 在 Prompt 之后生成，是为了让机器契约和人工可读 Prompt 使用同一批上下文与验证命令，避免两者漂移。

## 节点职责

- `classify`：根据用户请求判断任务类型，例如 crash_fix、performance、feature、review、refactor、general。
- `retrieve`：通过 Search Service 检索相关 `Document`、`Rule`、`File`、`Symbol`。
- `build_context`：按上下文预算组装 `context.md`。
- `render_agent_prompt`：根据 Agent Profile 中的 Prompt 字段、任务指导、验证命令和上下文生成 `agent_prompt.md`；Profile 中的 adapter、command、I/O 模式和权限字段保留给后续 Agent Adapter 使用。
- `build_context_pack`：生成机器可读 `manifest.json`。
- `write_outputs`：写出全部运行产物和 `state.json`。

为什么拆成这些节点：分类、检索、上下文预算、Prompt 渲染和产物落盘各自代表不同的可优化边界。后续要替换分类器、升级搜索、调整 Prompt 风格或接入 Agent Adapter 时，可以只替换对应节点，而不重写整条链路。

## 运行产物

- `agent_prompt.md`：直接交给 Agent 的完整任务 Prompt。
- `context.md`：被选中的上下文片段。
- `manifest.json`：机器可读 Context Pack。
- `state.json`：完整 prepare 状态快照。
- `final_report.md`：面向人的最终运行报告。
- `runs/index.jsonl`：Run Store 摘要索引，记录本次 prepare 的 run_id、project、repo、agent、状态和产物路径。
- `runs/events.jsonl`：Run Store 事件日志，记录本次 prepare 的 `prepare.finished` 平台事件。

为什么同时保留人类和机器产物：`agent_prompt.md` 面向 Agent 和开发者即时使用，`manifest.json` 面向后续 Adapter / API / Dashboard，`state.json` 用于审计和复现。三者分离可以避免把所有信息塞进一个 Markdown，导致机器难解析、人也难审阅。

## 安全边界

- prepare 默认不调用模型。
- prepare 默认不应用 patch。
- prepare 默认不提交代码。
- prepare 默认不执行验证命令。
- `agent run` 是显式 runtime 入口，可能启动外部 Agent 并修改目标仓库。
- 验证命令必须来自配置文件；只有独立 `verify` 命令会执行它们。
- 目标仓库源码目录不会混入运行产物。

为什么默认边界这么保守：当前项目正在搭 Agent OS 的平台地基，Context Pack 的质量和可审计性比自动执行更重要。执行模型、工具权限和审批链路会在 Agent Adapter / Tool Service / Permission Service 中逐步引入，而不是提前混进 prepare。
