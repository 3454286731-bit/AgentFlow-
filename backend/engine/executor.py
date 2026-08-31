"""
工作流执行器。

调度策略：
1. 先用 dag.layered_batches 把图切成批次，同批次内节点互不依赖
2. 逐批次推进，批次内 asyncio.gather 并发，用信号量控制并发上限
3. 只有执行成功的节点才会激活它的出边；分支未命中的下游自动标记 SKIPPED
   —— 这个设计让「节点失败后下游跳过」变成自然结果，不需要额外的传播逻辑
4. 节点超时用 asyncio.wait_for 兜底，避免单个慢节点拖死整条工作流

失败策略：
- on_error="abort"（默认）：任一节点失败立即停止后续批次
- on_error="continue"：记录失败并继续，失败节点的下游因为没有激活边自动跳过
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

from backend.core.expr import evaluate
from backend.core.graph import layered_batches
from backend.core.logging import get_logger
from backend.core.models import (
    Context,
    ExecutionRecord,
    Node,
    NodeResult,
    NodeStatus,
    NodeType,
    Workflow,
    WorkflowStatus,
)
from backend.core.providers import LLMProvider, MockLLMProvider
from backend.nodes.base import get_handler
from backend.nodes import builtins  # noqa: F401  导入即完成节点注册

logger = get_logger("agentflow.engine")


class WorkflowExecutionError(RuntimeError):
    """工作流执行失败，携带完整执行记录供排查。"""

    def __init__(self, record: ExecutionRecord):
        self.record = record
        super().__init__(record.error or "工作流执行失败")


class Executor:
    def __init__(
        self,
        workflow: Workflow,
        *,
        llm_provider: LLMProvider | None = None,
        http_client: Any | None = None,
        max_concurrency: int = 4,
        node_timeout: float | None = 60.0,
        on_error: Literal["abort", "continue"] = "abort",
    ):
        self.workflow = workflow
        self.llm_provider = llm_provider or MockLLMProvider()
        self.http_client = http_client
        self.max_concurrency = max_concurrency
        self.node_timeout = node_timeout
        self.on_error = on_error

    # ------------------------------------------------------------ 主入口

    async def run(self, inputs: dict[str, Any] | None = None) -> ExecutionRecord:
        wf = self.workflow
        start = wf.start_node
        record = ExecutionRecord(workflow_id=wf.id, inputs=inputs or {})

        ctx = Context(
            inputs=dict(inputs or {}),
            services={"llm_provider": self.llm_provider, "http_client": self.http_client},
        )

        batches = layered_batches(wf.to_adjacency(), root=start.id)
        logger.info(
            "工作流开始执行 id=%s 名称=%s 节点=%d 批次=%d",
            wf.id, wf.name, len(wf.nodes), len(batches),
        )
        activated_edges: set[str] = set()
        semaphore = asyncio.Semaphore(self.max_concurrency)
        aborted = False

        for batch in batches:
            runnable: list[str] = []
            for node_id in batch:
                if aborted:
                    record.node_results.append(self._skipped(node_id))
                    continue
                if node_id == start.id:
                    runnable.append(node_id)
                    continue
                inbound = wf.incoming(node_id)
                if any(e.id in activated_edges for e in inbound):
                    runnable.append(node_id)
                else:
                    record.node_results.append(self._skipped(node_id))

            if not runnable:
                continue

            tasks = [self._run_node(wf.get_node(nid), ctx, semaphore) for nid in runnable]
            results = await asyncio.gather(*tasks)

            for node_id, result in zip(runnable, results):
                record.node_results.append(result)
                if result.status == NodeStatus.SUCCESS:
                    self._activate_outgoing(node_id, ctx, activated_edges)
                    logger.info(
                        "节点完成 %s(%s) 耗时 %dms",
                        node_id, result.node_type.value, result.duration_ms,
                    )
                elif result.status == NodeStatus.FAILED:
                    logger.error("节点失败 %s: %s", node_id, result.error)
                    if self.on_error == "abort":
                        aborted = True
                        record.error = f"节点 {node_id} 失败，已中止后续执行"

        # 收尾：取第一个成功执行的 end 节点输出作为最终结果
        for result in record.node_results:
            if result.node_type == NodeType.END and result.status == NodeStatus.SUCCESS:
                record.final_output = result.output
                break

        record.status = (
            WorkflowStatus.SUCCESS
            if not any(r.status == NodeStatus.FAILED for r in record.node_results)
            else WorkflowStatus.FAILED
        )
        record.finished_at = datetime.now()
        if record.status == WorkflowStatus.SUCCESS:
            logger.info(
                "工作流执行成功 id=%s 总耗时 %dms 节点 %d",
                record.id, record.duration_ms, len(record.node_results),
            )
        else:
            logger.warning(
                "工作流执行结束但存在失败节点 id=%s 原因=%s",
                record.id, record.error or "节点失败",
            )
        return record

    def run_sync(self, inputs: dict[str, Any] | None = None) -> ExecutionRecord:
        """同步入口，方便 CLI、脚本和测试里直接调用。"""
        return asyncio.run(self.run(inputs))

    # ------------------------------------------------------------ 内部方法

    async def _run_node(
        self, node: Node, ctx: Context, semaphore: asyncio.Semaphore
    ) -> NodeResult:
        result = NodeResult(
            node_id=node.id,
            node_type=node.type,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(),
        )
        try:
            handler = get_handler(node.type)
            async with semaphore:
                coro = handler.run(node, ctx)
                if self.node_timeout:
                    output = await asyncio.wait_for(coro, timeout=self.node_timeout)
                else:
                    output = await coro
            ctx.set_output(node.id, output)
            result.output = output.get("output") if isinstance(output, dict) else output
            result.status = NodeStatus.SUCCESS
        except asyncio.TimeoutError:
            result.status = NodeStatus.FAILED
            result.error = f"节点执行超时（{self.node_timeout}s）"
        except Exception as exc:
            result.status = NodeStatus.FAILED
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.finished_at = datetime.now()
        return result

    def _activate_outgoing(self, node_id: str, ctx: Context, activated: set[str]) -> None:
        """把该节点的出边标记为激活，下游才有权执行。"""
        wf = self.workflow
        node = wf.get_node(node_id)
        branch: str | None = None
        if node.type == NodeType.CONDITION:
            branch = ctx.get_output(node_id).get("branch")

        for edge in wf.outgoing(node_id):
            # 条件节点：只有命中的那个出口能通
            if node.type == NodeType.CONDITION and edge.source_handle != branch:
                continue
            # 边级条件：表达式为真才通
            if edge.condition:
                try:
                    if not evaluate(ctx.render_expression(edge.condition)):
                        continue
                except Exception:
                    continue
            activated.add(edge.id)

    def _skipped(self, node_id: str) -> NodeResult:
        node_type = (
            self.workflow.get_node(node_id).type
            if self.workflow.has_node(node_id)
            else NodeType.LLM
        )
        return NodeResult(
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.SKIPPED,
            error="分支未命中或上游未激活",
        )


def execute(
    workflow: Workflow,
    inputs: dict[str, Any] | None = None,
    **kwargs,
) -> ExecutionRecord:
    """一步到位的便捷入口。"""
    return Executor(workflow, **kwargs).run_sync(inputs)
