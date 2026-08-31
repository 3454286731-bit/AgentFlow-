"""执行器端到端测试。用 mock provider，全程离线、不花钱、不依赖网络。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.core.models import (
    Context,
    Edge,
    Node,
    NodeStatus,
    NodeType,
    Workflow,
    WorkflowStatus,
)
from backend.core.providers import LLMProvider, LLMResponse, MockLLMProvider
from backend.engine.executor import Executor


# ---------------------------------------------------------------- 测试替身

class BoomProvider(LLMProvider):
    """每次调用都抛错，用来验证失败传播。"""

    name = "boom"

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
        raise RuntimeError("模型服务不可用")


class TrackingProvider(LLMProvider):
    """记录并发峰值，用来验证同批次节点真的在并发跑。"""

    name = "tracking"

    def __init__(self):
        self.concurrent = 0
        self.peak = 0
        self.calls = 0

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
        self.calls += 1
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        await asyncio.sleep(0.05)
        self.concurrent -= 1
        return LLMResponse(text="ok")


class SlowProvider(LLMProvider):
    """慢到一定超时，用来验证超时保护。"""

    name = "slow"

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
        await asyncio.sleep(5)
        return LLMResponse(text="too late")


def wf(nodes: list[dict], edges: list[dict], name: str = "测试流程") -> Workflow:
    return Workflow(
        name=name,
        nodes=[Node(**n) for n in nodes],
        edges=[Edge(**e) for e in edges],
    )


LINEAR = dict(
    nodes=[
        {"id": "start_1", "type": "start", "name": "开始",
         "config": {"inputs": {"topic": "冒泡排序"}}},
        {"id": "llm_1", "type": "llm", "name": "生成",
         "config": {"prompt": "请讲解 {{topic}}"}},
        {"id": "end_1", "type": "end", "name": "结束",
         "config": {"output_template": "结果：{{llm_1.output}}｜主题：{{topic}}"}},
    ],
    edges=[
        {"id": "e1", "source": "start_1", "target": "llm_1"},
        {"id": "e2", "source": "llm_1", "target": "end_1"},
    ],
)


# ---------------------------------------------------------------- 线性流程

def test_linear_workflow_runs_to_completion():
    record = Executor(wf(**LINEAR)).run_sync()
    assert record.status == WorkflowStatus.SUCCESS
    assert len(record.node_results) == 3
    assert all(r.status == NodeStatus.SUCCESS for r in record.node_results)
    assert record.final_output.startswith("结果：")
    assert "冒泡排序" in record.final_output


def test_prompt_is_rendered_before_calling_model():
    provider = MockLLMProvider()
    Executor(wf(**LINEAR), llm_provider=provider).run_sync()
    assert provider.calls[0]["prompt"] == "请讲解 冒泡排序"


def test_runtime_inputs_override_defaults():
    record = Executor(wf(**LINEAR)).run_sync({"topic": "快速排序"})
    assert "快速排序" in record.final_output


def test_mock_provider_can_return_keyed_response():
    provider = MockLLMProvider(responses={"讲解": "冒泡排序就是两两比较"})
    record = Executor(wf(**LINEAR), llm_provider=provider).run_sync()
    assert "冒泡排序就是两两比较" in record.final_output


def test_record_has_duration():
    record = Executor(wf(**LINEAR)).run_sync()
    assert record.duration_ms >= 0
    assert record.finished_at is not None


# ---------------------------------------------------------------- 条件分支

COND = dict(
    nodes=[
        {"id": "start_1", "type": "start", "name": "开始", "config": {}},
        {"id": "llm_1", "type": "llm", "name": "生成", "config": {"prompt": "写一句话"}},
        {"id": "cond_1", "type": "condition", "name": "长度判断",
         "config": {"branches": [
             {"handle": "too_long", "label": "太长",
              "expression": "len({{llm_1.output}}) > 10"}],
             "default_handle": "ok"}},
        {"id": "end_long", "type": "end", "name": "太长分支",
         "config": {"output_template": "命中太长分支"}},
        {"id": "end_ok", "type": "end", "name": "正常分支",
         "config": {"output_template": "命中正常分支"}},
    ],
    edges=[
        {"id": "e1", "source": "start_1", "target": "llm_1"},
        {"id": "e2", "source": "llm_1", "target": "cond_1"},
        {"id": "e3", "source": "cond_1", "target": "end_long", "source_handle": "too_long"},
        {"id": "e4", "source": "cond_1", "target": "end_ok", "source_handle": "ok"},
    ],
)


def test_condition_matching_branch_executes():
    provider = MockLLMProvider(default="这是一段明显超过十个字的回复内容")
    record = Executor(wf(**COND), llm_provider=provider).run_sync()
    statuses = {r.node_id: r.status for r in record.node_results}
    assert statuses["end_long"] == NodeStatus.SUCCESS
    assert statuses["end_ok"] == NodeStatus.SKIPPED
    assert record.final_output == "命中太长分支"


def test_condition_falls_back_to_default():
    provider = MockLLMProvider(default="短")
    record = Executor(wf(**COND), llm_provider=provider).run_sync()
    statuses = {r.node_id: r.status for r in record.node_results}
    assert statuses["end_ok"] == NodeStatus.SUCCESS
    assert statuses["end_long"] == NodeStatus.SKIPPED
    assert record.final_output == "命中正常分支"


# ---------------------------------------------------------------- 失败处理

def test_failure_aborts_downstream_by_default():
    record = Executor(wf(**LINEAR), llm_provider=BoomProvider()).run_sync()
    assert record.status == WorkflowStatus.FAILED
    statuses = {r.node_id: r.status for r in record.node_results}
    assert statuses["llm_1"] == NodeStatus.FAILED
    assert statuses["end_1"] == NodeStatus.SKIPPED
    assert "模型服务不可用" in record.node_results[1].error
    assert record.error


def test_continue_mode_keeps_going():
    record = Executor(wf(**LINEAR), llm_provider=BoomProvider(),
                      on_error="continue").run_sync()
    assert record.status == WorkflowStatus.FAILED
    assert not record.error
    statuses = {r.node_id: r.status for r in record.node_results}
    assert statuses["llm_1"] == NodeStatus.FAILED
    assert statuses["end_1"] == NodeStatus.SKIPPED


def test_node_timeout_is_enforced():
    record = Executor(wf(**LINEAR), llm_provider=SlowProvider(),
                      node_timeout=0.1).run_sync()
    assert record.status == WorkflowStatus.FAILED
    assert "超时" in record.node_results[1].error


# ---------------------------------------------------------------- 并发

DIAMOND = dict(
    nodes=[
        {"id": "start_1", "type": "start", "name": "开始", "config": {}},
        {"id": "llm_a", "type": "llm", "name": "分支A", "config": {"prompt": "A"}},
        {"id": "llm_b", "type": "llm", "name": "分支B", "config": {"prompt": "B"}},
        {"id": "end_1", "type": "end", "name": "结束",
         "config": {"output_template": "{{llm_a.output}}-{{llm_b.output}}"}},
    ],
    edges=[
        {"id": "e1", "source": "start_1", "target": "llm_a"},
        {"id": "e2", "source": "start_1", "target": "llm_b"},
        {"id": "e3", "source": "llm_a", "target": "end_1"},
        {"id": "e4", "source": "llm_b", "target": "end_1"},
    ],
)


def test_parallel_nodes_run_concurrently():
    provider = TrackingProvider()
    record = Executor(wf(**DIAMOND), llm_provider=provider).run_sync()
    assert record.status == WorkflowStatus.SUCCESS
    assert provider.calls == 2
    assert provider.peak == 2, "两个互不依赖的 LLM 节点应该并发执行"
    assert record.final_output == "ok-ok"


def test_concurrency_limit_is_respected():
    provider = TrackingProvider()
    Executor(wf(**DIAMOND), llm_provider=provider, max_concurrency=1).run_sync()
    assert provider.peak == 1


# ---------------------------------------------------------------- HTTP 节点

def test_http_node_with_injected_client():
    client = AsyncMock()
    client.request.return_value = type(
        "Resp", (), {"status_code": 200, "json": lambda self: {"title": "来自接口"}}
    )()

    workflow = wf(
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"uid": "42"}}},
            {"id": "http_1", "type": "http", "name": "查用户",
             "config": {"method": "GET", "url": "https://api.example.com/u/{{uid}}"}},
            {"id": "end_1", "type": "end", "name": "结束",
             "config": {"output_template": "{{http_1.output.title}}"}},
        ],
        edges=[
            {"source": "start_1", "target": "http_1"},
            {"source": "http_1", "target": "end_1"},
        ],
    )
    record = Executor(workflow, http_client=client).run_sync()
    assert record.status == WorkflowStatus.SUCCESS
    assert record.final_output == "来自接口"
    args, kwargs = client.request.call_args
    assert args == ("GET", "https://api.example.com/u/42")


# ---------------------------------------------------------------- 孤立节点

def test_orphan_nodes_are_not_executed():
    workflow = wf(
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始", "config": {}},
            {"id": "llm_1", "type": "llm", "name": "生成", "config": {"prompt": "x"}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {}},
            {"id": "orphan", "type": "llm", "name": "没连线的节点", "config": {"prompt": "y"}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    record = Executor(workflow).run_sync()
    executed = {r.node_id for r in record.node_results}
    assert "orphan" not in executed
