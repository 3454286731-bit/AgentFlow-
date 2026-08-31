"""
API 冒烟测试：对着真跑起来的服务打一遍接口。

先启动服务：
    uvicorn backend.api.main:app --port 8000

再跑：
    python examples/smoke_api.py
    python examples/smoke_api.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys

import httpx

WORKFLOW = {
    "name": "知识点讲解生成",
    "description": "输入知识点，生成讲解并按长度分流",
    "nodes": [
        {"id": "start_1", "type": "start", "name": "开始",
         "config": {"inputs": {"topic": "冒泡排序"}}},
        {"id": "llm_1", "type": "llm", "name": "生成讲解",
         "config": {"prompt": "请用通俗语言讲解：{{topic}}"}},
        {"id": "cond_1", "type": "condition", "name": "长度判断",
         "config": {"branches": [
             {"handle": "too_short", "label": "太短",
              "expression": "len({{llm_1.output}}) < 10"}],
             "default_handle": "ok"}},
        {"id": "end_short", "type": "end", "name": "太短·转人工",
         "config": {"output_template": "回答过短：{{llm_1.output}}"}},
        {"id": "end_ok", "type": "end", "name": "正常·输出",
         "config": {"output_template": "【{{topic}}】{{llm_1.output}}"}},
    ],
    "edges": [
        {"source": "start_1", "target": "llm_1"},
        {"source": "llm_1", "target": "cond_1"},
        {"source": "cond_1", "target": "end_short", "source_handle": "too_short"},
        {"source": "cond_1", "target": "end_ok", "source_handle": "ok"},
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=30) as c:
        print("1. 健康检查")
        print("   ", c.get("/api/health").json())

        print("2. 节点类型元数据")
        types = c.get("/api/node-types").json()
        print("   ", [t["type"] for t in types])

        print("3. 创建工作流")
        wf = c.post("/api/workflows", json=WORKFLOW).json()
        print(f"    id={wf['id']} 节点={wf['node_count']} 连线={wf['edge_count']}")

        print("4. 创建非法工作流（连成环）应被拒绝")
        cyclic = {
            "name": "带环的流程",
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
        }
        resp = c.post("/api/workflows", json=cyclic)
        print(f"    HTTP {resp.status_code}: {resp.json()['detail']}")
        for err in resp.json()["errors"]:
            print(f"      - {err['msg']}")

        print("5. 执行工作流")
        run = c.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}}).json()
        print(f"    状态={run['status']} 耗时={run['duration_ms']}ms")
        print(f"    输出={run['final_output']}")
        for r in run["node_results"]:
            print(f"      [{r['status']}] {r['node_id']:<10} {r['node_type']:<10} {r['duration_ms']}ms")

        print("6. 再跑一次，换输入")
        run2 = c.post(f"/api/workflows/{wf['id']}/run",
                      json={"inputs": {"topic": "快速排序"}}).json()
        print(f"    输出={run2['final_output']}")

        print("7. 执行历史")
        history = c.get(f"/api/workflows/{wf['id']}/executions").json()
        print(f"    共 {history['total']} 条")

        print("8. 执行统计")
        print("   ", c.get(f"/api/workflows/{wf['id']}/stats").json())

        print("9. 查询不存在的工作流应返回 404")
        resp = c.get("/api/workflows/ghost")
        print(f"    HTTP {resp.status_code}: {resp.json()['detail']}")

        print("10. 删除工作流")
        resp = c.delete(f"/api/workflows/{wf['id']}")
        print(f"    HTTP {resp.status_code}")

    print("\n冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
