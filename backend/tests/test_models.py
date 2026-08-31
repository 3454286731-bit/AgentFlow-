"""工作流数据模型的校验测试。第一周先把地基钉死，后面才敢往上盖。"""

import pytest
from pydantic import ValidationError

from backend.core.models import (
    Context,
    Edge,
    Node,
    NodeStatus,
    NodeType,
    Workflow,
)


# ---------------------------------------------------------------- 工具函数

def build_linear_workflow(**overrides) -> Workflow:
    """构造一条最简可用链路：start -> llm -> end。"""
    payload = {
        "name": "测试流程",
        "nodes": [
            {"id": "start_1", "type": "start", "name": "开始",
             "config": {"inputs": {"topic": "冒泡排序"}}},
            {"id": "llm_1", "type": "llm", "name": "生成",
             "config": {"prompt": "讲讲 {{topic}}"}},
            {"id": "end_1", "type": "end", "name": "结束",
             "config": {"output_template": "{{llm_1.output}}"}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
        ],
    }
    payload.update(overrides)
    return Workflow(**payload)


# ---------------------------------------------------------------- 正常路径

def test_linear_workflow_is_valid():
    wf = build_linear_workflow()
    assert len(wf.nodes) == 3
    assert wf.start_node.id == "start_1"
    assert wf.to_adjacency() == {
        "start_1": ["llm_1"],
        "llm_1": ["end_1"],
        "end_1": [],
    }


def test_config_is_parsed_into_typed_model():
    """config 存的是字典，但要能按节点类型转成强类型模型。"""
    node = Node(id="llm_1", type=NodeType.LLM, name="生成",
                config={"prompt": "hi"})
    assert node.config_model.model == "gpt-4o-mini"
    assert node.config_model.temperature == 0.7


def test_graph_query_helpers():
    wf = build_linear_workflow()
    assert len(wf.outgoing("start_1")) == 1
    assert len(wf.incoming("start_1")) == 0
    assert wf.get_node("llm_1").name == "生成"
    with pytest.raises(KeyError):
        wf.get_node("not_exist")


# ---------------------------------------------------------------- 结构校验

def test_duplicate_node_id_rejected():
    with pytest.raises(ValueError, match="节点 id 重复"):
        build_linear_workflow(nodes=[
            {"id": "start_1", "type": "start", "name": "A", "config": {}},
            {"id": "start_1", "type": "end", "name": "B", "config": {}},
        ], edges=[])


def test_edge_with_unknown_endpoint_rejected():
    with pytest.raises(ValueError, match="target 不存在"):
        build_linear_workflow(edges=[
            {"source": "start_1", "target": "ghost"},
        ])


def test_missing_start_node_rejected():
    with pytest.raises(ValueError, match="start 节点"):
        build_linear_workflow(nodes=[
            {"id": "llm_1", "type": "llm", "name": "生成", "config": {"prompt": "x"}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {}},
        ], edges=[{"source": "llm_1", "target": "end_1"}])


def test_start_node_cannot_have_incoming_edge():
    with pytest.raises(ValueError, match="start 节点不能有入边"):
        build_linear_workflow(edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "start_1"},
        ])


def test_end_node_cannot_have_outgoing_edge():
    with pytest.raises(ValueError, match="end 节点不能有出边"):
        build_linear_workflow(edges=[
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "end_1"},
            {"source": "end_1", "target": "llm_1"},
        ])


def test_cycle_is_rejected_at_save_time():
    """环检测属于结构校验，保存时就该拦下，不能拖到执行时。"""
    with pytest.raises(ValueError, match="存在环"):
        Workflow(
            name="带环的流程",
            nodes=[
                {"id": "start_1", "type": "start", "name": "开始", "config": {}},
                {"id": "llm_1", "type": "llm", "name": "A", "config": {"prompt": "a"}},
                {"id": "llm_2", "type": "llm", "name": "B", "config": {"prompt": "b"}},
                {"id": "end_1", "type": "end", "name": "结束", "config": {}},
            ],
            edges=[
                {"source": "start_1", "target": "llm_1"},
                {"source": "llm_1", "target": "llm_2"},
                {"source": "llm_2", "target": "llm_1"},
                {"source": "llm_2", "target": "end_1"},
            ],
        )


def test_invalid_node_config_rejected():
    """extra=forbid：前端传了不存在的字段要直接报错，不能静默忽略。"""
    with pytest.raises(ValueError, match="配置不合法"):
        build_linear_workflow(nodes=[
            {"id": "start_1", "type": "start", "name": "开始", "config": {}},
            {"id": "llm_1", "type": "llm", "name": "生成",
             "config": {"prompt": "hi", "unknown_field": 1}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {}},
        ])


def test_temperature_range_enforced():
    """config 在 Node 里是字典，转成类型模型时才做字段级校验。"""
    node = Node(id="llm_1", type=NodeType.LLM, name="生成",
                config={"prompt": "hi", "temperature": 5.0})
    with pytest.raises(ValidationError):
        node.config_model


# ---------------------------------------------------------------- 变量渲染

def test_context_renders_node_output():
    ctx = Context(inputs={"topic": "冒泡排序"})
    ctx.set_output("llm_1", "讲完了")
    assert ctx.render("结果：{{llm_1.output}}") == "结果：讲完了"


def test_context_renders_global_input():
    ctx = Context(inputs={"topic": "冒泡排序"})
    assert ctx.render("主题：{{topic}}") == "主题：冒泡排序"


def test_context_renders_nested_path():
    ctx = Context()
    ctx.set_output("http_1", {"data": {"title": "标题"}})
    assert ctx.render("{{http_1.data.title}}") == "标题"


def test_context_raises_on_undefined_variable():
    ctx = Context()
    with pytest.raises(KeyError, match="变量未定义"):
        ctx.render("{{missing}}")


def test_context_render_value_recurses():
    ctx = Context(inputs={"topic": "AI"})
    ctx.set_output("llm_1", "正文")
    rendered = ctx.render_value({
        "title": "{{topic}}",
        "items": ["{{llm_1.output}}", 42],
    })
    assert rendered == {"title": "AI", "items": ["正文", 42]}


# ---------------------------------------------------------------- 执行结果

def test_node_result_duration():
    from datetime import datetime, timedelta

    from backend.core.models import NodeResult

    start = datetime(2026, 1, 1, 12, 0, 0)
    result = NodeResult(
        node_id="llm_1",
        node_type=NodeType.LLM,
        status=NodeStatus.SUCCESS,
        started_at=start,
        finished_at=start + timedelta(milliseconds=1500),
    )
    assert result.duration_ms == 1500
