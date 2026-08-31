"""API 接口测试。用内存库 + mock 模型，全程离线。"""

import pytest

from backend.core.providers import MockLLMProvider

LINEAR = {
    "name": "知识点讲解",
    "description": "输入知识点，生成讲解",
    "nodes": [
        {"id": "start_1", "type": "start", "name": "开始",
         "config": {"inputs": {"topic": "冒泡排序"}}},
        {"id": "llm_1", "type": "llm", "name": "生成讲解",
         "config": {"prompt": "请讲解 {{topic}}"}},
        {"id": "end_1", "type": "end", "name": "输出",
         "config": {"output_template": "【{{topic}}】{{llm_1.output}}"}},
    ],
    "edges": [
        {"source": "start_1", "target": "llm_1"},
        {"source": "llm_1", "target": "end_1"},
    ],
}


def create(client, **overrides):
    payload = {**LINEAR, **overrides}
    resp = client.post("/api/workflows", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------- 健康检查

def test_health(client):
    """健康检查要顺带报告数据库与模型 provider 的状态。"""
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["provider"] == "mock"


# ---------------------------------------------------------------- 工作流 CRUD

def test_create_workflow(client):
    data = create(client)
    assert data["id"]
    assert data["name"] == "知识点讲解"
    assert data["node_count"] == 3
    assert data["edge_count"] == 2
    assert data["version"] == 1


def test_create_rejects_missing_end_node(client):
    resp = client.post("/api/workflows", json={
        "name": "没有出口",
        "nodes": [{"id": "start_1", "type": "start", "name": "开始", "config": {}}],
        "edges": [],
    })
    assert resp.status_code == 422
    assert "工作流结构校验失败" in resp.json()["detail"]


def test_create_rejects_cycle(client):
    resp = client.post("/api/workflows", json={
        "name": "带环",
        "nodes": [
            {"id": "start_1", "type": "start", "name": "开始", "config": {}},
            {"id": "llm_1", "type": "llm", "name": "A", "config": {"prompt": "a"}},
            {"id": "llm_2", "type": "llm", "name": "B", "config": {"prompt": "b"}},
            {"id": "end_1", "type": "end", "name": "结束", "config": {}},
        ],
        "edges": [
            {"source": "start_1", "target": "llm_1"},
            {"source": "llm_1", "target": "llm_2"},
            {"source": "llm_2", "target": "llm_1"},
            {"source": "llm_2", "target": "end_1"},
        ],
    })
    assert resp.status_code == 422
    assert any("环" in str(e.get("msg", "")) for e in resp.json()["errors"])


def test_list_workflows(client):
    create(client, name="流程A")
    create(client, name="流程B")
    data = client.get("/api/workflows").json()
    assert data["total"] == 2
    assert {w["name"] for w in data["items"]} == {"流程A", "流程B"}


def test_get_workflow_returns_full_graph(client):
    wf = create(client)
    data = client.get(f"/api/workflows/{wf['id']}").json()
    assert len(data["nodes"]) == 3
    assert data["nodes"][1]["config"]["prompt"] == "请讲解 {{topic}}"
    assert len(data["edges"]) == 2


def test_get_missing_workflow_returns_404(client):
    resp = client.get("/api/workflows/nonexistent")
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


def test_update_bumps_version(client):
    wf = create(client)
    updated = client.put(f"/api/workflows/{wf['id']}", json={
        "name": "改了名字",
        "nodes": LINEAR["nodes"],
        "edges": LINEAR["edges"],
    }).json()
    assert updated["name"] == "改了名字"
    assert updated["version"] == wf["version"] + 1


def test_delete_workflow(client):
    wf = create(client)
    assert client.delete(f"/api/workflows/{wf['id']}").status_code == 204
    assert client.get(f"/api/workflows/{wf['id']}").status_code == 404


def test_delete_missing_workflow_returns_404(client):
    assert client.delete("/api/workflows/nonexistent").status_code == 404


def test_definition_survives_roundtrip(client):
    """存进数据库再取出来，图结构必须完全一致，否则画布会莫名丢节点。"""
    wf = create(client)
    data = client.get(f"/api/workflows/{wf['id']}").json()
    assert sorted(n["id"] for n in data["nodes"]) == ["end_1", "llm_1", "start_1"]
    assert sorted(e["source"] for e in data["edges"]) == ["llm_1", "start_1"]


# ---------------------------------------------------------------- 执行

def test_run_workflow(client):
    wf = create(client)
    data = client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}}).json()
    assert data["status"] == "success"
    assert "冒泡排序" in data["final_output"]
    assert len(data["node_results"]) == 3
    assert all(r["status"] == "success" for r in data["node_results"])


def test_run_with_runtime_inputs(client):
    wf = create(client)
    data = client.post(f"/api/workflows/{wf['id']}/run",
                       json={"inputs": {"topic": "快速排序"}}).json()
    assert "快速排序" in data["final_output"]


def test_run_missing_workflow_returns_404(client):
    resp = client.post("/api/workflows/nonexistent/run", json={"inputs": {}})
    assert resp.status_code == 404


def test_execution_is_persisted(client):
    wf = create(client)
    run = client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}}).json()
    detail = client.get(f"/api/executions/{run['id']}").json()
    assert detail["workflow_id"] == wf["id"]
    assert detail["workflow_name"] == "知识点讲解"
    assert len(detail["node_results"]) == 3
    assert detail["duration_ms"] >= 0


def test_execution_history_for_workflow(client):
    wf = create(client)
    for _ in range(3):
        client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    other = create(client, name="另一条流程")
    client.post(f"/api/workflows/{other['id']}/run", json={"inputs": {}})

    data = client.get(f"/api/workflows/{wf['id']}/executions").json()
    assert data["total"] == 3
    assert all(e["workflow_id"] == wf["id"] for e in data["items"])

    all_runs = client.get("/api/executions").json()
    assert all_runs["total"] == 4


def test_execution_stats(client):
    wf = create(client)
    client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    stats = client.get(f"/api/workflows/{wf['id']}/stats").json()
    assert stats["total"] == 2
    assert stats["success"] == 2
    assert stats["failed"] == 0


def test_failed_execution_is_recorded(client):
    from backend.core.providers import LLMProvider

    class BoomProvider(LLMProvider):
        name = "boom"

        async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
            raise RuntimeError("模型服务不可用")

    wf = create(client)
    client.app.state.llm_provider = BoomProvider()
    run = client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}}).json()
    assert run["status"] == "failed"
    assert run["error"]

    stats = client.get(f"/api/workflows/{wf['id']}/stats").json()
    assert stats["failed"] == 1


def test_filter_global_executions_by_workflow(client):
    """全局执行历史要能按工作流过滤，否则工作一多就没法看。"""
    wf_a = create(client, name="流程A")
    wf_b = create(client, name="流程B")
    for _ in range(2):
        client.post(f"/api/workflows/{wf_a['id']}/run", json={"inputs": {}})
    client.post(f"/api/workflows/{wf_b['id']}/run", json={"inputs": {}})

    data = client.get("/api/executions", params={"workflow_id": wf_a["id"]}).json()
    assert data["total"] == 2
    assert all(e["workflow_id"] == wf_a["id"] for e in data["items"])

    everything = client.get("/api/executions").json()
    assert everything["total"] == 3


def test_filter_executions_by_status(client):
    from backend.core.providers import LLMProvider

    class BoomProvider(LLMProvider):
        name = "boom"

        async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024):
            raise RuntimeError("boom")

    wf = create(client)
    client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    client.app.state.llm_provider = BoomProvider()
    client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})

    failed = client.get("/api/executions", params={"status": "failed"}).json()
    assert failed["total"] == 1


# ---------------------------------------------------------------- 节点元数据

def test_node_types_expose_config_schema(client):
    data = client.get("/api/node-types").json()
    types = {t["type"] for t in data}
    assert types == {
        "start", "llm", "http", "condition", "end",
        "question", "grading", "analytics",
    }
    llm = next(t for t in data if t["type"] == "llm")
    assert "prompt" in llm["config_schema"]["properties"]
    assert llm["config_schema"]["properties"]["temperature"]["default"] == 0.7


def test_teaching_node_types_are_exposed(client):
    """教学专用节点要和通用节点一样出现在元数据里，前端才能自动渲染表单。"""
    data = client.get("/api/node-types").json()
    question = next(t for t in data if t["type"] == "question")
    properties = question["config_schema"]["properties"]
    assert {"knowledge_point", "difficulty", "question_type", "count"} <= set(properties)
    assert properties["difficulty"]["enum"] == ["easy", "medium", "hard"]

    grading = next(t for t in data if t["type"] == "grading")
    assert "rubric" in grading["config_schema"]["properties"]

    analytics = next(t for t in data if t["type"] == "analytics")
    assert "records" in analytics["config_schema"]["properties"]


def test_node_type_schema_marks_extra_forbidden(client):
    """extra=forbid 要体现在 schema 里，前端才能据此拦截多余字段。"""
    data = client.get("/api/node-types").json()
    llm = next(t for t in data if t["type"] == "llm")
    assert llm["config_schema"].get("additionalProperties") is False
