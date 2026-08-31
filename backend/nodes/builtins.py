"""
内置节点：五个通用节点 + 三个教学场景专用节点。

通用：start / llm / http / condition / end
教学：question（智能出题） / grading（作业批改） / analytics（学情分析）

共同约定：
- run() 返回值统一是 dict，且至少含 output 字段
- 提示词、URL、表达式里都能写 {{变量}}，由节点自己负责渲染
- 外部依赖（模型、HTTP）从 ctx.services 取，不在这里创建连接

教学节点都对模型输出做结构化解析：解析成功就给出结构化字段供下游引用，
解析失败降级为纯文本，保证离线演示和模型不稳定时流程依然能跑通。
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.expr import evaluate
from backend.core.models import (
    AnalyticsConfig,
    ConditionConfig,
    Context,
    EndConfig,
    GradingConfig,
    HTTPConfig,
    LLMConfig,
    Node,
    QuestionConfig,
    StartConfig,
)
from backend.core.providers import LLMProvider
from backend.nodes.base import NodeExecutionError, NodeType, BaseNode, register


@register
class StartNode(BaseNode):
    """入口节点：把配置里的默认值和运行时传入的输入合并成全局变量。"""

    node_type = NodeType.START

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: StartConfig = node.config_model
        merged = {**cfg.inputs, **ctx.inputs}
        ctx.inputs = merged
        return {"output": merged}


@register
class LLMNode(BaseNode):
    """大模型节点：渲染提示词 -> 调适配层 -> 输出文本与用量。"""

    node_type = NodeType.LLM

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: LLMConfig = node.config_model
        provider: LLMProvider | None = ctx.services.get("llm_provider")
        if provider is None:
            raise NodeExecutionError(node.id, "未注入 llm_provider")

        prompt = ctx.render(cfg.prompt)
        response = await provider.complete(
            model=cfg.model,
            prompt=prompt,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )

        text = response.text
        if cfg.output_format == "json":
            try:
                text = json.loads(text)
            except json.JSONDecodeError as exc:
                raise NodeExecutionError(node.id, f"模型返回的不是合法 JSON: {exc}") from exc

        return {"output": text, "usage": response.usage, "prompt": prompt}


@register
class HTTPNode(BaseNode):
    """HTTP 工具节点：让工作流能调用外部系统。"""

    node_type = NodeType.HTTP

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: HTTPConfig = node.config_model
        url = ctx.render(cfg.url)
        headers = {k: ctx.render(v) for k, v in cfg.headers.items()}
        body = ctx.render(cfg.body) if cfg.body else None

        client = ctx.services.get("http_client")
        if client is None:
            try:
                import httpx
            except ImportError as exc:
                raise NodeExecutionError(node.id, "请先安装 httpx: pip install httpx") from exc
            client = httpx.AsyncClient(timeout=cfg.timeout)

        kwargs: dict[str, Any] = {"headers": headers}
        if cfg.method == "GET":
            kwargs["params"] = json.loads(body) if body else None
        else:
            kwargs["content"] = body

        try:
            response = await client.request(cfg.method, url, **kwargs)
        except Exception as exc:
            raise NodeExecutionError(node.id, f"HTTP 请求失败: {exc}") from exc

        try:
            data = response.json()
        except Exception:
            data = getattr(response, "text", "")

        return {"output": data, "status_code": getattr(response, "status_code", None), "url": url}


@register
class ConditionNode(BaseNode):
    """
    条件分支节点：按顺序匹配分支表达式，命中即返回该出口 handle，全不中走 default。

    注意这里用的是 render_expression 而不是 render —— 字符串要带引号
    才能拼成合法表达式，交给安全求值器处理。
    """

    node_type = NodeType.CONDITION

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: ConditionConfig = node.config_model
        for branch in cfg.branches:
            expression = ctx.render_expression(branch.expression)
            try:
                matched = evaluate(expression)
            except Exception as exc:
                raise NodeExecutionError(
                    node.id, f"分支 [{branch.handle}] 表达式求值失败: {exc}"
                ) from exc
            if matched:
                return {"output": branch.handle, "branch": branch.handle,
                        "matched_expression": expression}

        return {"output": cfg.default_handle, "branch": cfg.default_handle,
                "matched_expression": None}


@register
class EndNode(BaseNode):
    """出口节点：渲染最终输出模板。"""

    node_type = NodeType.END

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: EndConfig = node.config_model
        text = ctx.render(cfg.output_template) if cfg.output_template else ""
        return {"output": text}


# ---------------------------------------------------------------- 教学节点

DIFFICULTY_TEXT = {"easy": "基础", "medium": "中等", "hard": "较难"}
QUESTION_TYPE_TEXT = {
    "choice": "单项选择题",
    "fill": "填空题",
    "short": "简答题",
    "program": "编程题",
}
DIMENSION_TEXT = {"knowledge": "知识点掌握", "skill": "能力维度", "progress": "学习进度"}


async def _call_model(
    node: Node, ctx: Context, model: str, prompt: str, temperature: float
) -> tuple[str, Any]:
    """
    调一次模型，返回（原始文本，结构化解析结果或 None）。

    模型输出经常裹在 ```json 代码块里，这里统一处理后再解析；
    解析不了就返回 None，由调用方决定怎么降级，不让解析失败中断整条流程。
    """
    provider: LLMProvider | None = ctx.services.get("llm_provider")
    if provider is None:
        raise NodeExecutionError(node.id, "未注入 llm_provider")

    response = await provider.complete(
        model=model,
        prompt=prompt,
        temperature=temperature,
        max_tokens=2048,
    )
    return response.text, _parse_json(response.text)


def _parse_json(text: str) -> Any | None:
    """
    从模型输出里尽量提取 JSON，提取不到返回 None。

    三步：先剥代码块，再整体解析，最后按最外层括号截取。
    截取时不能只认花括号——数组输出 [{"a":1}] 按 { } 定位会截成
    {"a":1} 之外的残缺片段，所以方括号和花括号要一起参与定位。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    starts = [pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos != -1]
    ends = [pos for pos in (cleaned.rfind("}"), cleaned.rfind("]")) if pos != -1]
    if not starts or not ends:
        return None

    start, end = min(starts), max(ends)
    if end <= start:
        return None

    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


@register
class QuestionNode(BaseNode):
    """智能出题：按知识点、难度、题型生成题目，附答案与解析。"""

    node_type = NodeType.QUESTION

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: QuestionConfig = node.config_model
        knowledge_point = ctx.render(cfg.knowledge_point)
        extra = f"\n补充要求：{ctx.render(cfg.requirements)}" if cfg.requirements else ""

        prompt = (
            "你是资深教师，请按下列要求出题。\n"
            f"知识点：{knowledge_point}\n"
            f"难度：{DIFFICULTY_TEXT[cfg.difficulty]}\n"
            f"题型：{QUESTION_TYPE_TEXT[cfg.question_type]}\n"
            f"数量：{cfg.count} 道{extra}\n\n"
            "请以 JSON 数组返回，每题包含 question、answer、analysis 三个字段，"
            "不要输出任何多余内容。"
        )

        text, parsed = await _call_model(node, ctx, cfg.model, prompt, cfg.temperature)

        questions: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            questions = [q for q in parsed if isinstance(q, dict)]
        elif isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
            questions = [q for q in parsed["questions"] if isinstance(q, dict)]

        # 结构化成功就拼成易读文本，失败则原样透出模型输出
        if questions:
            readable = "\n".join(
                f"{i}. {q.get('question', '')}\n"
                f"   答案：{q.get('answer', '')}\n"
                f"   解析：{q.get('analysis', '')}"
                for i, q in enumerate(questions, start=1)
            )
        else:
            readable = text

        return {
            "output": readable,
            "questions": questions,
            "count": len(questions) or cfg.count,
            "knowledge_point": knowledge_point,
            "difficulty": cfg.difficulty,
            "question_type": cfg.question_type,
        }


@register
class GradingNode(BaseNode):
    """作业批改：按评分细则打分，给出总评与改进建议。"""

    node_type = NodeType.GRADING

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: GradingConfig = node.config_model
        answer = ctx.render(cfg.answer)
        reference = f"\n参考答案：{ctx.render(cfg.reference)}" if cfg.reference else ""

        prompt = (
            "你是阅卷老师，请严格按评分细则批改学生作答。\n"
            f"【评分细则】{ctx.render(cfg.rubric)}\n"
            f"{reference}\n"
            f"【学生作答】{answer}\n"
            f"满分：{cfg.max_score} 分\n\n"
            '请以 JSON 返回：{"score": 得分数字, "comment": "总评", '
            '"suggestions": ["改进建议"]}，不要输出多余内容。'
        )

        text, parsed = await _call_model(node, ctx, cfg.model, prompt, cfg.temperature)

        score: float | None = None
        comment = text
        suggestions: list[str] = []

        if isinstance(parsed, dict):
            raw_score = parsed.get("score")
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
            if isinstance(parsed.get("comment"), str):
                comment = parsed["comment"]
            if isinstance(parsed.get("suggestions"), list):
                suggestions = [str(s) for s in parsed["suggestions"]]

        return {
            "output": comment,
            "score": score,
            "rate": round(score / cfg.max_score, 4) if score is not None else None,
            "max_score": cfg.max_score,
            "suggestions": suggestions,
            "passed": (score / cfg.max_score >= 0.6) if score is not None else None,
        }


@register
class AnalyticsNode(BaseNode):
    """学情分析：从学习记录里提炼薄弱点与改进建议。"""

    node_type = NodeType.ANALYTICS

    async def run(self, node: Node, ctx: Context) -> dict[str, Any]:
        cfg: AnalyticsConfig = node.config_model
        records = ctx.render(cfg.records)

        prompt = (
            "你是学情分析师，请基于下列学习记录做"
            f"「{DIMENSION_TEXT[cfg.dimension]}」维度的分析。\n"
            f"【学习记录】\n{records}\n\n"
            f"请至少列出 {cfg.top_n} 个薄弱点，并以 JSON 返回："
            '{"summary": "总体情况", "weak_points": '
            '[{"name": "知识点", "mastery": 0.4, "reason": "原因"}], '
            '"advice": "改进建议"}，不要输出多余内容。'
        )

        text, parsed = await _call_model(node, ctx, cfg.model, prompt, cfg.temperature)

        weak_points: list[dict[str, Any]] = []
        summary = text
        advice = ""

        if isinstance(parsed, dict):
            if isinstance(parsed.get("summary"), str):
                summary = parsed["summary"]
            if isinstance(parsed.get("weak_points"), list):
                weak_points = [w for w in parsed["weak_points"] if isinstance(w, dict)]
            if isinstance(parsed.get("advice"), str):
                advice = parsed["advice"]

        if weak_points:
            readable = summary + "\n薄弱点：\n" + "\n".join(
                f"- {w.get('name', '')}（掌握度 {w.get('mastery', '')}）"
                f"{'：' + w['reason'] if w.get('reason') else ''}"
                for w in weak_points
            )
            if advice:
                readable += f"\n建议：{advice}"
        else:
            readable = summary

        return {
            "output": readable,
            "weak_points": weak_points,
            "summary": summary,
            "advice": advice,
            "dimension": cfg.dimension,
        }


__all__ = [
    "AnalyticsNode",
    "ConditionNode",
    "EndNode",
    "GradingNode",
    "HTTPNode",
    "LLMNode",
    "QuestionNode",
    "StartNode",
]
