# 核心模块说明

本文记录当前 AI Workflow / Agent OS 单体内核中的主要模块职责。模块边界优先服务后续演进，不代表当前已经是微服务。

## CLI 与配置

- `aiworkflow/cli.py` 提供 `doctor`、`ingest`、`prepare`、`verify` 四个命令入口。
- `aiworkflow/config.py` 负责读取 `.env`、`AIWORKFLOW_CONFIG`、`config/workflow.yaml` 和示例配置。
- `config/workflow.example.yaml` 定义仓库扫描范围、知识文档路径、Neo4j、上下文预算、结构化 Agent Profile、验证命令和产物目录。

为什么这样做：CLI 是当前 MVP 最薄、最容易审计的入口，能避免过早引入 HTTP 服务、队列或 IDE 插件。配置集中在 `workflow.yaml`，是为了让目标仓库的扫描范围、验证命令和 Agent 偏好可以被 code review，而不是散落在命令参数或代码常量里。

## Project Registry

- `aiworkflow/projects.py` 负责把 `projects.<name>` 解析成命令可用的项目上下文。
- `ProjectConfig` 当前支持 `repo`、`agent`、`output_dir`，并保留 `config`、`prompts` 字段给后续项目级配置合并使用。
- `ingest`、`prepare`、`verify` 都支持 `--project`，同时保留 `--repo` 作为直接路径入口。
- 使用 `--project` 且未显式配置 `output_dir` 时，运行产物默认写入 `runs/<project>/`。

为什么这样做：Agent OS 不能长期依赖裸 repo 路径。Project Registry 把仓库、默认 Agent、产物目录和未来权限策略绑定到稳定别名上，后续 Run Store、Tool Service 和团队级 ACL 才能按项目审计和治理。

## Agent Profile

- `AgentProfileConfig` 现在同时描述 Prompt 风格和运行时入口。
- `prompt_style`、`extra_instructions` 继续服务 `prepare` 阶段的 Prompt 渲染。
- `adapter`、`command`、`args`、`input_mode`、`output_mode` 描述后续如何把任务交给 Codex CLI、Claude Code 或其他 Agent。
- `default_permissions`、`timeout_seconds`、`env` 为后续权限控制、进程隔离和运行限制预留统一配置入口。
- `resolve_agent_profile()` 是 CLI、prepare 和 Adapter 层共享的解析入口，并兼容旧的字符串 profile 写法。

为什么这样做：如果 Agent Profile 只保存 Prompt 风格，平台后续接入 Codex、Claude Code、OpenHands 时就会把 adapter、命令参数、I/O 模式和默认权限散落到各自模块里。结构化 Profile 先把这些差异收敛到配置契约中，让“选择哪个 Agent”和“如何启动/约束这个 Agent”能被审计、复用和项目化覆盖。

## Prepare / Context Pack

- `aiworkflow/agent_pack.py` 是新主流程入口。
- 当前节点包括 `classify`、`retrieve`、`build_context`、`render_agent_prompt`、`build_context_pack`、`write_outputs`。
- prepare 会写出 `agent_prompt.md`、`context.md`、`manifest.json`、`state.json` 和 `final_report.md`。
- `ContextPack` 是面向 Agent Adapter 的稳定数据契约。
- `ContextPackState` 是一次 prepare 的过程状态和审计轨迹。
- 这只是 Agent OS 的第一阶段能力，后续 Tool、Permission、Agent Adapter 会围绕同一任务包契约扩展。

为什么这样做：先把 Context Pack 做成独立产物，是为了把“给 Agent 喂什么”从“由哪个 Agent 执行”里拆出来。Codex、Claude Code 或内部 Agent 会变化，但任务上下文、规则、验证线索和审计记录是平台资产，应该先稳定下来。

## Runtime Contracts

- `aiworkflow/contracts.py` 定义 Agent / Tool / Permission 层之间的运行时契约。
- `AgentRunRequest`、`AgentRunResult`、`AgentEvent` 为后续 Codex CLI、Claude Code、OpenHands Adapter 提供统一输入输出形状。
- `Artifact` 统一描述 prompt、manifest、日志、patch、报告等产物。
- `Capability`、`ToolRequest`、`ToolResult`、`PermissionDecision` 为后续 Tool Service 和权限审计预留稳定数据结构。

为什么这样做：运行时契约先于具体 Agent 实现，是为了避免 Codex CLI、Claude Code、OpenHands 各自带来一套返回格式和工具调用模型。统一事件、结果和工具请求形状后，后续才能做跨 Agent 的审计、重放、统计和权限控制。

## Agent Adapter

- `aiworkflow/agent_adapter.py` 定义 Agent Adapter 抽象、进程内 registry 和 dry-run 实现。
- `AgentAdapter` 统一 `supports(agent)` 与 `run_task(request)`，后续 Codex CLI / Claude Code / OpenHands 都应作为 adapter 插件接入。
- `DryRunAgentAdapter` 不启动外部进程，只验证 `AgentRunRequest` 到 `AgentRunResult` 的生命周期。
- `CodexCliAdapter` 通过结构化 Agent Profile 中的 command、args、I/O 模式和 timeout 显式启动本地 CLI 进程。
- `build_agent_run_request()` 把 `ContextPack`、`Artifact` 和结构化 Agent Profile 组装成运行时请求，避免具体 adapter 反向依赖 prepare 流程。

为什么这样做：Adapter 层把“平台如何组织任务”和“某个 Agent 如何被启动”隔离开。dry-run adapter 的价值不是功能演示，而是在没有 Codex CLI 的环境里也能测试运行时边界；`CodexCliAdapter` 则证明同一套契约可以接入真实外部进程。真实 Agent 可能修改目标仓库，所以它只通过显式 `agent run` 入口触发，不混入 prepare。

## Run Store

- `aiworkflow/run_store.py` 提供文件版运行账本。
- `RunRecord` 记录 run_id、project、repo、query、agent、status、output_dir 和 artifacts。
- `RunEventRecord` 记录 AgentEvent、ToolRequest、ToolResult、PermissionDecision 和平台事件的统一信封。
- `RunStore` 使用 `index.jsonl` 追加运行摘要，使用 `events.jsonl` 追加运行事件。
- `prepare` 成功后会自动登记一条 `prepared` 摘要记录，并追加一条 `prepare.finished` 事件。
- CLI 提供 `aiworkflow runs list`、`aiworkflow runs show <run_id>` 和 `aiworkflow runs events <run_id>` 查询运行记录。

为什么这样做：运行目录只解决“文件放在哪里”，不能回答“某个项目最近跑过哪些任务、某次任务用了哪个 Agent、产物在哪里、运行过程中发生了哪些事件”。`index.jsonl` 保持轻量，适合快速列 run；`events.jsonl` 单独追加生命周期事件，避免摘要索引越来越重，也给后续 Agent run、Tool call、Permission decision 留下统一账本。第一版用 JSONL 是为了保持 CLI-first、可审阅、无数据库依赖。

## Context / Search / Prompt

- `aiworkflow/context.py` 负责任务分类、知识标签、检索调用和上下文预算，不依赖具体 workflow state。
- `aiworkflow/search.py` 定义 `SearchService`、`SearchRequest`、`SearchResponse`，底层暂时复用 `GraphStore.search()`。
- `aiworkflow/prompt.py` 从 `prompts/` 目录加载任务指导文本。
- `prompts/tasks/` 按任务类型存放指导文本，例如 crash_fix、performance、feature、review、refactor。

为什么这样做：ContextService 不直接读文件、不直接访问 Neo4j，也不持有 workflow state，是为了让检索编排能被 CLI、API、Agent Adapter 或测试共同复用。Prompt 模板放在文件里，是为了让团队能审阅和版本化 Agent 行为，而不是把提示词藏在代码分支里。

## Knowledge Index

- `aiworkflow/ingest.py` 负责扫描目标仓库、读取文档、提取符号并写入图谱。
- `aiworkflow/graph.py` 定义 `GraphStore` 协议，以及 `Neo4jGraphStore` 和 `InMemoryGraphStore`。
- 当前图谱对象包括 `File`、`Symbol`、`Document`、`Rule`。
- 当前轻量支持 Python、C++、C#、Lua、Markdown、YAML、JSON 等文件。

为什么这样做：知识索引是 Agent OS 的长期资产。当前先做最小图谱和轻量符号提取，是为了尽快跑通“代码/文档/规则进入 Context Pack”的闭环；同时保留 `GraphStore` 抽象，后续可以替换为 Hybrid Search、clangd、Roslyn 或远程 Knowledge Service。

## Permission / Verification

- `aiworkflow/policy.py` 定义 `CommandPolicy`，用于判断命令是否允许执行。
- `aiworkflow/verify.py` 读取验证命令并执行，通过 `CommandPolicy` 拒绝明显破坏性命令。
- `prepare` 不执行验证命令，只把配置中的验证命令写入 Context Pack。

为什么这样做：当前阶段把 verification 作为独立 CLI，而不是嵌进 prepare，是为了保持 Context Pack 生成过程无副作用。Agent 运行时真正接入工具后，也应走 Capability / Permission / ToolResult，而不是让 Agent 直接持有 Git、CI 或构建系统权限。
