# 工作流执行链路

一次 `aiworkflow run` 会把开发者请求转成可审阅产物，并通过配置中的验证命令形成闭环。默认行为是不直接修改目标仓库。

## 命令入口

```powershell
aiworkflow run --repo G:\path\to\repo --query "修复 Renderer crash" --mock-model
```

运行时会创建一个 `run_id`，并把所有产物写入 `runs/<run_id>/`。

## 节点顺序

```text
classify
  -> retrieve
  -> build_prompt
  -> generate
  -> verify
  -> prepare_retry
  -> review
  -> evaluate
  -> report
```

其中 `prepare_retry` 只在验证失败且未超过最大重试次数时执行。

## 节点职责

- `classify`：根据用户请求判断任务类型，例如 crash_fix、performance、feature、review、refactor、general。
- `retrieve`：通过 Search Service 检索相关 `Document`、`Rule`、`File`、`Symbol`。
- `build_prompt`：按上下文预算组装 Prompt，并写出 `context.md`。
- `generate`：调用模型生成可审阅 patch，并写出 `change.patch`。
- `verify`：运行配置中的验证命令，写出 `verify_report.json`。
- `prepare_retry`：把失败日志放回上下文，准备下一轮生成。
- `review`：对生成 patch 执行独立评审，写出 `review_report.md`。
- `evaluate`：记录检索数量、上下文字符数、验证耗时、重试次数、模型名等指标。
- `report`：写出最终 `final_report.md` 和完整 `state.json`。

## 运行产物

- `context.md`：组装后的模型上下文。
- `change.patch`：模型生成的可审阅 patch。
- `review_report.md`：独立 review pass 的输出。
- `verify_report.json`：验证命令结果、耗时和安全策略决策。
- `state.json`：完整工作流状态快照。
- `final_report.md`：面向人的最终运行报告。

## 安全边界

- 工作流默认不应用 patch。
- 工作流默认不提交代码。
- 验证命令必须来自配置文件。
- 明显破坏性命令会被 `CommandPolicy` 拒绝。
- 目标仓库源码目录不会混入运行产物。
