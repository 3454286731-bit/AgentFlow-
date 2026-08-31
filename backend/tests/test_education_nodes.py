"""
教学场景专用节点测试：智能出题 / 作业批改 / 学情分析。

重点验证两件事：
1. 模型返回合法 JSON 时能结构化解析，字段可供下游引用
2. 模型返回纯文本或格式不规范时能降级，不让解析失败中断整条流程
"""

import asyncio
import json

import pytest

from backend.core.models import Context, Edge, Node, Workflow
from backend.core.providers import LLMProvider, MockLLMProvider
from backend.engine.executor import Executor
from backend.nodes.base import get_handler


class BoomProvider(LLMProvider):
    name = "boom"

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
        raise RuntimeError("模型不可用")


def run_node(node_type: str, config: dict, provider: LLMProvider,
             inputs: dict | None = None) -> dict:
    """直接跑单个节点，拿到完整输出字典（执行记录里只保留 output 字段）。"""
    node = Node(id="n_1", type=node_type, name="测试节点", config=config)
    ctx = Context(inputs=inputs or {}, services={"llm_provider": provider})
    return asyncio.run(get_handler(node.type).run(node, ctx))


def build_workflow(nodes: list[dict], edges: list[dict]) -> Workflow:
    return Workflow(
        name="教学流程",
        nodes=[Node(**n) for n in nodes],
        edges=[Edge(**e) for e in edges],
    )


# ---------------------------------------------------------------- 智能出题

QUESTION_JSON = json.dumps(
    [
        {"question": "1 + 1 = ?", "answer": "2", "analysis": "基础加法运算"},
        {"question": "2 + 3 = ?", "answer": "5", "analysis": "进位加法"},
    ],
    ensure_ascii=False,
)


def test_question_node_parses_structured_output():
    result = run_node(
        "question",
        {"knowledge_point": "加法运算", "count": 2},
        MockLLMProvider(default=QUESTION_JSON),
    )
    assert len(result["questions"]) == 2
    assert result["questions"][0]["answer"] == "2"
    assert result["count"] == 2
    assert "1. 1 + 1 = ?" in result["output"]
    assert "答案：2" in result["output"]
    assert result["knowledge_point"] == "加法运算"


def test_question_node_falls_back_to_plain_text():
    result = run_node(
        "question",
        {"knowledge_point": "加法"},
        MockLLMProvider(default="这是纯文本形式的题目"),
    )
    assert result["questions"] == []
    assert result["output"] == "这是纯文本形式的题目"


def test_question_node_handles_markdown_code_block():
    """模型常把 JSON 裹在代码块里，要能正确剥离。"""
    wrapped = f"```json\n{QUESTION_JSON}\n```"
    result = run_node("question", {"knowledge_point": "加法"},
                      MockLLMProvider(default=wrapped))
    assert len(result["questions"]) == 2


def test_question_node_supports_wrapped_object():
    """有些模型返回 {"questions": [...]} 而不是裸数组。"""
    payload = json.dumps({"questions": [{"question": "Q", "answer": "A"}]},
                         ensure_ascii=False)
    result = run_node("question", {"knowledge_point": "x"},
                      MockLLMProvider(default=payload))
    assert len(result["questions"]) == 1


def test_question_node_renders_variables():
    result = run_node(
        "question",
        {"knowledge_point": "请针对 {{topic}} 出题"},
        MockLLMProvider(default="纯文本"),
        inputs={"topic": "二次函数"},
    )
    assert result["knowledge_point"] == "请针对 二次函数 出题"


def test_question_config_rejects_bad_difficulty():
    """config 是字典，构造节点时不校验，必须转成类型模型才触发。"""
    node = Node(id="q", type="question", name="出题",
                config={"knowledge_point": "x", "difficulty": "超难"})
    with pytest.raises(ValueError):
        node.config_model


# ---------------------------------------------------------------- 作业批改

GRADING_JSON = json.dumps(
    {"score": 85, "comment": "概念理解正确，步骤略有跳跃",
     "suggestions": ["补充中间推导", "注意单位"]},
    ensure_ascii=False,
)


def test_grading_node_extracts_score():
    result = run_node(
        "grading",
        {"answer": "学生作答内容", "rubric": "概念 40 分，步骤 60 分", "max_score": 100},
        MockLLMProvider(default=GRADING_JSON),
    )
    assert result["score"] == 85
    assert result["rate"] == 0.85
    assert result["passed"] is True
    assert result["output"] == "概念理解正确，步骤略有跳跃"
    assert result["suggestions"] == ["补充中间推导", "注意单位"]


def test_grading_node_passed_threshold():
    result = run_node(
        "grading",
        {"answer": "x", "rubric": "y", "max_score": 100},
        MockLLMProvider(default=json.dumps({"score": 50, "comment": "不及格"})),
    )
    assert result["passed"] is False
    assert result["rate"] == 0.5


def test_grading_node_falls_back_when_not_json():
    result = run_node(
        "grading",
        {"answer": "x", "rubric": "y"},
        MockLLMProvider(default="这篇作业整体不错，但不是 JSON"),
    )
    assert result["score"] is None
    assert result["passed"] is None
    assert result["output"] == "这篇作业整体不错，但不是 JSON"


def test_grading_node_default_temperature_is_low():
    """批改要稳定，默认温度应该比生成类节点低。"""
    node = Node(id="g", type="grading", name="批改",
                config={"answer": "x", "rubric": "y"})
    assert node.config_model.temperature == 0.2


# ---------------------------------------------------------------- 学情分析

ANALYTICS_JSON = json.dumps(
    {
        "summary": "该生计算能力较好，函数部分偏弱",
        "weak_points": [
            {"name": "二次函数", "mastery": 0.35, "reason": "顶点式掌握不牢"},
            {"name": "不等式", "mastery": 0.5, "reason": "分类讨论遗漏"},
        ],
        "advice": "重点补函数图像与性质",
    },
    ensure_ascii=False,
)


def test_analytics_node_extracts_weak_points():
    result = run_node(
        "analytics",
        {"records": "近五次测验记录...", "top_n": 2},
        MockLLMProvider(default=ANALYTICS_JSON),
    )
    assert len(result["weak_points"]) == 2
    assert result["weak_points"][0]["name"] == "二次函数"
    assert result["summary"] == "该生计算能力较好，函数部分偏弱"
    assert result["advice"] == "重点补函数图像与性质"
    assert "二次函数" in result["output"]
    assert "建议：重点补函数图像与性质" in result["output"]


def test_analytics_node_falls_back_to_summary():
    result = run_node(
        "analytics",
        {"records": "记录"},
        MockLLMProvider(default="整体稳定，继续巩固"),
    )
    assert result["weak_points"] == []
    assert result["output"] == "整体稳定，继续巩固"


def test_analytics_node_rejects_bad_dimension():
    node = Node(id="a", type="analytics", name="分析",
                config={"records": "x", "dimension": "随便"})
    with pytest.raises(ValueError):
        node.config_model


# ---------------------------------------------------------------- 端到端

def test_teaching_pipeline_runs_end_to_end():
    """出题 → 批改 → 分析 串成一条完整的教学闭环。"""
    workflow = build_workflow(
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"topic": "二次函数"}}},
            {"id": "q_1", "type": "question", "name": "出题",
             "config": {"knowledge_point": "{{topic}}", "count": 1,
                        "question_type": "choice"}},
            {"id": "g_1", "type": "grading", "name": "批改",
             "config": {"answer": "{{q_1.output}}", "rubric": "答案正确 100 分",
                        "max_score": 100}},
            {"id": "a_1", "type": "analytics", "name": "学情分析",
             "config": {"records": "{{g_1.output}}", "top_n": 2}},
            {"id": "end_1", "type": "end", "name": "输出",
             "config": {"output_template": "分析报告：{{a_1.output}}"}},
        ],
        edges=[
            {"source": "start_1", "target": "q_1"},
            {"source": "q_1", "target": "g_1"},
            {"source": "g_1", "target": "a_1"},
            {"source": "a_1", "target": "end_1"},
        ],
    )

    provider = MockLLMProvider(
        responses={
            "出题": QUESTION_JSON,
            "批改": GRADING_JSON,
            "分析": ANALYTICS_JSON,
        },
        default="兜底文本",
    )
    record = Executor(workflow, llm_provider=provider).run_sync()

    assert record.status.value == "success"
    assert len(record.node_results) == 5
    assert record.final_output.startswith("分析报告：")
    assert "该生计算能力较好" in record.final_output


def test_teaching_node_failure_propagates():
    workflow = build_workflow(
        nodes=[
            {"id": "start_1", "type": "start", "name": "开始", "config": {}},
            {"id": "q_1", "type": "question", "name": "出题",
             "config": {"knowledge_point": "x"}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {}},
        ],
        edges=[
            {"source": "start_1", "target": "q_1"},
            {"source": "q_1", "target": "end_1"},
        ],
    )
    record = Executor(workflow, llm_provider=BoomProvider()).run_sync()
    assert record.status.value == "failed"
    statuses = {r.node_id: r.status.value for r in record.node_results}
    assert statuses["q_1"] == "failed"
    assert statuses["end_1"] == "skipped"
