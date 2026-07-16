from __future__ import annotations

from .context import ContextService
from .model_gateway import ModelClient
from .state import DevWorkflowState


def run_review(state: DevWorkflowState, context: ContextService, model: ModelClient) -> str:
    if not state.ai_diff.strip():
        return "未生成 patch，跳过评审。"
    prompt = context.build_review_prompt(state)
    response = model.complete(
        "你是严格的软件工程评审 Agent。请返回简洁、可执行的评审意见。",
        prompt,
    )
    state.workflow_steps.append({"node": "review", "model": response.model, "chars": len(response.content)})
    return response.content
