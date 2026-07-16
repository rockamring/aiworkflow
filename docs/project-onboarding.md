# 工程接入方式

本文记录如何把 AI Workflow 应用到实际工程，尤其是游戏工程。这个能力是项目最终目标之一：让多个真实研发工程都能接入统一 AI 流水线，而不是只服务当前工具仓库本身。

## 基本定位

`aiworkflow` 应作为外部 AI 工程流水线工具使用，不直接塞进目标游戏工程里。

目标游戏工程负责提供代码、文档、规则和构建命令；`aiworkflow` 负责索引、组装上下文、调用模型、执行验证、生成可审阅产物。

默认边界：

- 不直接修改目标工程。
- 不自动提交代码。
- 不自动创建 PR。
- 只生成可审阅的 patch、报告和验证结果。

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

先用 mock 模型跑通流程：

```powershell
aiworkflow run --repo G:\games\MyGame --query "分析 Renderer 模块中阴影异常的问题" --mock-model
```

接真实模型后：

```powershell
aiworkflow run --repo G:\games\MyGame --query "修复角色技能冷却 UI 没有刷新的问题"
```

## 运行产物

每次运行会生成：

```text
runs/<run_id>/
├── context.md
├── change.patch
├── review_report.md
├── verify_report.json
├── state.json
└── final_report.md
```

重点查看：

- `context.md`：AI 拿到了哪些上下文。
- `change.patch`：AI 建议怎么改。
- `review_report.md`：AI 对输出的独立评审。
- `verify_report.json`：验证命令是否通过。
- `state.json`：完整过程记录。

## 多工程支持现状

当前已经能基础支持多个工程：

- `aiworkflow ingest --repo <工程路径>` 可以分别索引不同工程。
- 每个工程会生成独立 `repo_id`。
- Neo4j 中的 `File / Symbol / Document / Rule` 都带 `repo_id`。
- `aiworkflow run --repo <工程路径>` 会按对应工程检索上下文。
- `clear_repo(repo_id)` 只清理单个工程索引，不影响其他工程。

示例：

```powershell
aiworkflow ingest --repo G:\games\ProjectA
aiworkflow ingest --repo G:\games\ProjectB

aiworkflow run --repo G:\games\ProjectA --query "修复战斗技能冷却问题"
aiworkflow run --repo G:\games\ProjectB --query "分析 Renderer crash"
```

## 多工程当前不足

当前多工程支持仍偏手动：

- 只有一个全局 `config/workflow.yaml`。
- 不同工程的验证命令、排除目录、知识目录、Prompt 偏好还不能独立管理。
- `runs/<run_id>/` 没有按项目分目录。
- 没有项目注册表。
- 没有项目别名，只能使用 `--repo` 路径。
- 没有多团队权限、ACL、审计隔离。
- 没有增量索引，大工程反复 ingest 成本较高。

## 推荐下一步：Project Registry

多工程长期使用时，应增加项目注册表，例如：

```yaml
projects:
  project_a:
    repo: G:\games\ProjectA
    config: config/projects/project_a.yaml
    prompts: prompts/projects/project_a
  project_b:
    repo: G:\games\ProjectB
    config: config/projects/project_b.yaml
    prompts: prompts/projects/project_b
```

然后支持：

```powershell
aiworkflow ingest --project project_a
aiworkflow run --project project_a --query "修复登录失败"
```

项目级配置应逐步支持：

- 独立 `include / exclude`。
- 独立 `docs_paths`。
- 独立 `verification.commands`。
- 独立 Prompt 和规则文档。
- 产物目录 `runs/<project>/<run_id>/`。
- 项目级权限、团队和分支策略。

## 推荐落地顺序

1. 先选择一个小模块试点，例如 Gameplay、UI 或 Renderer 子模块。
2. 补齐 `AGENTS.md`、`README.md` 和模块文档。
3. 用 mock 模型跑通 ingest / run / report。
4. 接真实模型，只做分析和 patch 建议。
5. 接轻量验证命令。
6. 扩展到完整工程。
7. 再接入多工程 Project Registry。
8. 最后接 Build、Crash、Profiler、Perforce、Jenkins、UE / Unity 工具链。
