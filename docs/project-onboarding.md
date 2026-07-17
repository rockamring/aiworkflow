# 工程接入方式

本文记录如何把 AI Workflow / Agent OS 应用到实际工程，尤其是游戏工程。这个能力是项目最终目标之一：让多个真实研发工程都能接入统一 AI 研发平台，而不是只服务当前工具仓库本身。

## 基本定位

`aiworkflow` 应作为外部 Agent OS 平台内核使用，不直接塞进目标游戏工程里。

目标游戏工程负责提供代码、文档、规则和构建命令；`aiworkflow` 负责索引、组装上下文、生成 Agent Prompt 和机器可读 Context Pack。后续 Tool、Permission、Agent Adapter 会继续接入同一平台边界。

默认边界：

- 不直接修改目标工程。
- 不自动提交代码。
- 不自动创建 PR。
- 只生成可审阅的上下文任务包和报告。

## 单工程接入流程

假设目标游戏工程在：

```powershell
G:\games\MyGame
```

推荐先在目标工程中补充 AI 可读文档：

```text
MyGame/
├── AGENTS.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── coding-standard.md
│   ├── build.md
│   ├── renderer.md
│   ├── network.md
│   └── gameplay.md
```

这些文档应优先说明：

- 项目模块划分。
- 编码规范。
- 构建命令。
- 测试命令。
- UE / Unity 特殊约束。
- 哪些目录不能动。
- 哪些模块不能相互依赖。

## 配置扫描和验证

当前工具读取 `config/workflow.yaml`。游戏工程接入时，应配置适合游戏项目的扫描范围：

```yaml
repo:
  include:
    - "**/*.cpp"
    - "**/*.h"
    - "**/*.hpp"
    - "**/*.cs"
    - "**/*.lua"
    - "**/*.md"
    - "**/*.json"
    - "**/*.yaml"
    - "**/*.uasset"
  exclude:
    - ".git/**"
    - "Binaries/**"
    - "Intermediate/**"
    - "Saved/**"
    - "DerivedDataCache/**"
    - "Library/**"
    - "Temp/**"
    - "Build/**"
    - "runs/**"

knowledge:
  docs_paths:
    - "docs"
    - "AGENTS.md"
    - "README.md"

context:
  budget_chars: 18000
  search_limit: 8

agent:
  default: "codex"

verification:
  commands:
    - name: "tests"
      command: "python -m pytest"
```

UE / Unity 工程初期不要直接接完整 Cook、Pak 或大规模构建。应先接轻量检查、单元测试、脚本验证或模块级构建。

## 典型命令

启动 Neo4j：

```powershell
docker compose up -d neo4j
```

检查环境：

```powershell
aiworkflow doctor
```

索引目标工程：

```powershell
aiworkflow ingest --repo G:\games\MyGame
```

生成给 Agent 使用的 Context Pack：

```powershell
aiworkflow prepare --repo G:\games\MyGame --query "分析 Renderer 模块中阴影异常的问题" --agent codex
```

把 `agent_prompt.md` 交给 Codex / Claude Code 后，再由 Agent 执行实际修改：

```powershell
aiworkflow prepare --repo G:\games\MyGame --query "修复角色技能冷却 UI 没有刷新的问题" --agent codex
```

## 运行产物

每次运行会生成：

```text
runs/<run_id>/
├── agent_prompt.md
├── context.md
├── manifest.json
├── state.json
└── final_report.md
```

重点查看：

- `agent_prompt.md`：直接交给 Agent 的完整任务 Prompt。
- `context.md`：Agent 将优先使用哪些上下文。
- `manifest.json`：机器可读 Context Pack。
- `state.json`：完整过程记录。

## 多工程支持现状

当前已经能基础支持多个工程：

- `aiworkflow ingest --repo <工程路径>` 可以分别索引不同工程。
- `aiworkflow ingest --project <项目名>` 可以通过 Project Registry 使用项目别名。
- 每个工程会生成独立 `repo_id`。
- Neo4j 中的 `File / Symbol / Document / Rule` 都带 `repo_id`。
- `aiworkflow prepare --repo <工程路径>` 或 `aiworkflow prepare --project <项目名>` 会按对应工程检索上下文并生成 Context Pack。
- `clear_repo(repo_id)` 只清理单个工程索引，不影响其他工程。

示例：

```powershell
aiworkflow ingest --repo G:\games\ProjectA
aiworkflow ingest --repo G:\games\ProjectB

aiworkflow prepare --repo G:\games\ProjectA --query "修复战斗技能冷却问题"
aiworkflow prepare --repo G:\games\ProjectB --query "分析 Renderer crash"
```

## 多工程当前不足

当前多工程支持仍偏手动：

- 只有一个全局 `config/workflow.yaml`。
- 不同工程的验证命令、排除目录、知识目录、Prompt 偏好还不能独立管理。
- Project Registry 当前只绑定 repo、agent、output_dir，尚未做项目级配置深度合并。
- 没有多团队权限、ACL、审计隔离。
- 没有增量索引，大工程反复 ingest 成本较高。

## Project Registry

多工程长期使用时，应配置项目注册表，例如：

```yaml
projects:
  project_a:
    repo: G:\games\ProjectA
    agent: codex
    output_dir: runs/project_a
  project_b:
    repo: G:\games\ProjectB
    agent: claude-code
```

然后支持：

```powershell
aiworkflow ingest --project project_a
aiworkflow prepare --project project_a --query "修复登录失败"
```

为什么这样做：项目别名是后续权限、审计、Run Store 和团队策略的锚点。裸路径适合个人试用，但企业平台需要知道“这是哪个项目、默认走哪个 Agent、产物落到哪里”。

项目级配置后续还应逐步支持：

- 独立 `include / exclude`。
- 独立 `docs_paths`。
- 独立 `verification.commands`。
- 独立 Prompt 和规则文档。
- 产物目录 `runs/<project>/<run_id>/`。
- 项目级权限、团队和分支策略。

## 推荐落地顺序

1. 先选择一个小模块试点，例如 Gameplay、UI 或 Renderer 子模块。
2. 补齐 `AGENTS.md`、`README.md` 和模块文档。
3. 跑通 ingest / prepare / report。
4. 把 `agent_prompt.md` 交给 Codex / Claude Code 试点真实任务。
5. 接轻量验证命令，让它们进入 Context Pack。
6. 扩展到完整工程。
7. 扩展 Project Registry 的项目级配置合并。
8. 最后接 Build、Crash、Profiler、Perforce、Jenkins、UE / Unity 工具链。
