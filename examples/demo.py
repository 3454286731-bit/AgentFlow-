"""
端到端演示：把五种典型工作流都跑一遍。

全程使用 MockLLMProvider，不联网、不花钱、不需要 API Key。

运行：
    python examples/demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from backend.core.graph import layered_batches
from backend.core.models import Edge, Node, NodeStatus, Workflow
from backend.core.providers import LLMProvider, LLMResponse, MockLLMProvider
from backend.engine.executor import Executor


class BoomProvider(LLMProvider):
    name = "boom"

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
        raise RuntimeError("模型服务不可用")


STATUS_ICON = {
    NodeStatus.SUCCESS: "成功",
    NodeStatus.FAILED: "失败",
    NodeStatus.SKIPPED: "跳过",
    NodeStatus.PENDING: "等待",
    NodeStatus.RUNNING: "运行中",
}


def build(nodes: list[dict], edges: list[dict], name: str, description: str = "") -> Workflow:
    return Workflow(
        name=name,
        description=description,
        nodes=[Node(**n) for n in nodes],
        edges=[Edge(**e) for e in edges],
    )


def report(workflow: Workflow, record) -> None:
    print(f"\n  分层批次：{layered_batches(workflow.to_adjacency(), root=workflow.start_node.id)}")
    print(f"  执行轨迹：")
    for r in record.node_results:
        icon = STATUS_ICON[r.status]
        line = f"    [{icon}] {r.node_id:<10} {r.node_type.value:<10} {r.duration_ms:>4}ms"
        if r.error:
            line += f"  ← {r.error}"
        print(line)
    print(f"  整体耗时：{record.duration_ms}ms，状态：{record.status.value}")
    if record.final_output is not None:
        print(f"  最终输出：{record.final_output}")


def demo_linear() -> None:
    print("\n" + "=" * 68)
    print("场景 1 · 线性流程：知识点讲解生成")
    print("=" * 68)
    wf = build(
        name="知识点讲解生成",
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"topic": "冒泡排序"}}},
            {"id": "llm_1", "type": "llm", "name": "生成讲解",
             "config": {"model": "gpt-4o-mini", "prompt": "请用通俗语言讲解：{{topic}}"}},
            {"id": "end_1", "type": "end", "name": "输出结果",
             "config": {"output_template": "【{{topic}}】{{llm_1.output}}"}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    provider = MockLLMProvider(responses={"讲解": "相邻元素两两比较，大的往后挪，一轮下来最大的沉底。"})
    report(wf, Executor(wf, llm_provider=provider).run_sync({"topic": "快速排序"}))


def demo_condition() -> None:
    print("\n" + "=" * 68)
    print("场景 2 · 条件分支：按生成长度走不同处理路径")
    print("=" * 68)
    wf = build(
        name="答案质量分流",
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"question": "什么是过拟合"}}},
            {"id": "llm_1", "type": "llm", "name": "作答",
             "config": {"prompt": "回答：{{question}}"}},
            {"id": "cond_1", "type": "condition", "name": "长度判断",
             "config": {"branches": [
                 {"handle": "too_short", "label": "回答太短",
                  "expression": "len({{llm_1.output}}) < 20"},
                 {"handle": "too_long", "label": "回答太长",
                  "expression": "len({{llm_1.output}}) > 40"}],
                 "default_handle": "just_right"}},
            {"id": "end_short", "type": "end", "name": "太短·重新生成",
             "config": {"output_template": "回答过短，已转人工补充"}},
            {"id": "end_long", "type": "end", "name": "太长·摘要",
             "config": {"output_template": "回答过长（{{llm_1.output}}），需压缩"}},
            {"id": "end_ok", "type": "end", "name": "正常·直接返回",
             "config": {"output_template": "合格答案：{{llm_1.output}}"}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "cond_1"},
            {"source": "cond_1", "target": "end_short", "source_handle": "too_short"},
            {"source": "cond_1", "target": "end_long", "source_handle": "too_long"},
            {"source": "cond_1", "target": "end_ok", "source_handle": "just_right"},
        ],
    )
    print("\n  [case A] 模型回答很短 → 应命中 too_short")
    report(wf, Executor(wf, llm_provider=MockLLMProvider(default="过拟合")).run_sync())
    print("\n  [case B] 模型回答很长 → 应命中 too_long")
    long_text = "过拟合是指模型在训练集上表现极好但在测试集上表现很差的现象，通常因为模型复杂度过高或训练数据不足导致。"
    report(wf, Executor(wf, llm_provider=MockLLMProvider(default=long_text)).run_sync())
    print("\n  [case C] 模型回答长度适中 → 应走默认出口")
    report(wf, Executor(wf, llm_provider=MockLLMProvider(default="模型记住了训练集的噪声，导致泛化能力下降。")).run_sync())


def demo_parallel() -> None:
    print("\n" + "=" * 68)
    print("场景 3 · 并发执行：两个互不依赖的模型节点同时跑")
    print("=" * 68)
    wf = build(
        name="双语讲解",
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"topic": "递归"}}},
            {"id": "llm_cn", "type": "llm", "name": "中文讲解",
             "config": {"prompt": "中文讲解 {{topic}}"}},
            {"id": "llm_en", "type": "llm", "name": "英文讲解",
             "config": {"prompt": "Explain {{topic}} in English"}},
            {"id": "end_1", "type": "end", "name": "合并输出",
             "config": {"output_template": "中文：{{llm_cn.output}}｜英文：{{llm_en.output}}"}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_cn"},
            {"source": "start_1", "target": "llm_en"},
            {"source": "llm_cn", "target": "end_1"},
            {"source": "llm_en", "target": "end_1"},
        ],
    )
    report(wf, Executor(wf, llm_provider=MockLLMProvider(default="递归就是函数调用自身")).run_sync())


def demo_failure() -> None:
    print("\n" + "=" * 68)
    print("场景 4 · 失败处理：abort 模式 vs continue 模式")
    print("=" * 68)
    wf = build(
        name="失败传播演示",
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始", "config": {}},
            {"id": "llm_1", "type": "llm", "name": "调用模型", "config": {"prompt": "hi"}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {"output_template": "ok"}},
        ],
        edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    )
    print("\n  [abort 模式] 节点失败后立即中止")
    report(wf, Executor(wf, llm_provider=BoomProvider(), on_error="abort").run_sync())
    print("\n  [continue 模式] 记录失败并继续，下游因无激活入边自动跳过")
    report(wf, Executor(wf, llm_provider=BoomProvider(), on_error="continue").run_sync())


def demo_cycle() -> None:
    print("\n" + "=" * 68)
    print("场景 5 · 环检测：MVP 不支持循环，必须报错并指出环路径")
    print("=" * 68)
    try:
        wf = build(
            name="带环的流程",
            nodes=[
                {"id": "start_1", "type": "start", "name": "开始", "config": {}},
                {"id": "llm_1", "type": "llm", "name": "生成", "config": {"prompt": "a"}},
                {"id": "llm_2", "type": "llm", "name": "优化", "config": {"prompt": "b"}},
                {"id": "end_1", "type": "end", "name": "结束", "config": {}},
            ],
            edges=[
                {"source": "start_1", "target": "llm_1"},
                {"source": "llm_1", "target": "llm_2"},
                {"source": "llm_2", "target": "llm_1"},
                {"source": "llm_2", "target": "end_1"},
            ],
        )
        print("  意外：带环的工作流没有被拦下")
    except ValidationError as exc:
        for err in exc.errors():
            print(f"  已拦截：{err['msg']}")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) if sys.platform == "win32" else None
    demo_linear()
    demo_condition()
    demo_parallel()
    demo_failure()
    demo_cycle()
    print("\n" + "=" * 68)
    print("全部场景执行完毕")
    print("=" * 68)
