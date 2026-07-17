"""独立评审节点。

Review 作为生成 patch 后的独立 pass 存在，避免把生成和评审混成一个
Prompt。后续可以继续拆分为架构、性能、测试、安全等多个 review agent。
"""

from __future__ import annotations

from .context import ContextService
from .model_gateway import ModelClient
from .state import DevWorkflowState


def run_review(state: DevWorkflowState, context: ContextService, model: ModelClient) -> str:
    """基于当前 patch 和上下文摘要执行一次模型评审。"""

    if not state.ai_diff.strip():
        return "未生成 patch，跳过评审。"
    prompt = context.build_review_prompt(state)
    response = model.complete(
        "你是严格的软件工程评审 Agent。请返回简洁、可执行的评审意见。",
        prompt,
    )
    state.workflow_steps.append({"node": "review", "model": response.model, "chars": len(response.content)})
    return response.content
