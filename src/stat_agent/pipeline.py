"""LangGraph controller with per-node timing and durable run artifacts."""
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from . import __version__
from .agents import KnowledgeAgent, ProfileValidationAgent, RelationsAgent, StructureAgent, TaskUnderstandingAgent
from .execution import execute
from .io import read_table
from .retrieval import LexicalEncoder, retrieve
from .storage import save_run


class AgentState(TypedDict, total=False):
    frame: Any
    source: Any
    task: Any
    variables: Any
    relations: Any
    profile: Any
    knowledge: Any
    retrieval: Any
    execution: Any


def dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build_graph(input_path, goal, roles, sheet, encoder, events, task_agent=None, knowledge_library='seed'):
    validator = ProfileValidationAgent()

    def load(state):
        frame, source = read_table(input_path, sheet)
        return {"frame": frame, "source": source}

    def task(state):
        task_profile = (task_agent.run(goal, columns=list(state['frame'].columns), **roles)
                        if task_agent else TaskUnderstandingAgent().run(goal, **roles))
        validator.validate_roles(state["frame"], task_profile)
        return {"task": task_profile}

    nodes = [
        ("read_table", load),
        ("task_understanding", task),
        ("data_structure", lambda s: {"variables": StructureAgent().run(s["frame"], s["source"])}),
        ("distribution_quality_relations", lambda s: {"relations": RelationsAgent().run(s["frame"], s["task"])}),
        ("profile_validation", lambda s: {"profile": validator.run(s["frame"], s["source"], s["task"], s["variables"], s["relations"])}),
        ("statistical_knowledge", lambda s: {"knowledge": KnowledgeAgent().run(knowledge_library)}),
        ("retrieve", lambda s: {"retrieval": retrieve(s["task"], s["profile"], s["knowledge"], encoder)}),
        ("execute_validate", lambda s: {"execution": execute(s["frame"], s["task"], s["retrieval"])}),
    ]

    def instrument(name, node):
        def run(state):
            start = time.perf_counter()
            event = {"node": name, "status": "success"}
            try:
                update = node(state)
                if "execution" in update:
                    event["outcome"] = update["execution"].status
                return update
            except Exception as exc:
                event.update(status="error", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                event["seconds"] = time.perf_counter() - start
                events.append(event)
        return run

    graph = StateGraph(AgentState)
    previous = START
    for name, node in nodes:
        graph.add_node(name, instrument(name, node))
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()


def report_preview(value, limit=10):
    """Keep reports readable; full arrays remain in execution.json."""
    if isinstance(value, dict):
        return {key: report_preview(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        items = [report_preview(item, limit) for item in value[:limit]]
        return {"preview": items, "total_items": len(value), "truncated": True} if len(value) > limit else items
    return value


def render_report(payload: dict) -> str:
    task, profile = payload["task"], payload["profile"]
    ranking, execution = payload["retrieval"], payload["execution"]
    lines = ["# 统计分析基线报告", "", f"研究目标：{task['research_goal']}", "",
             f"任务：{task['task_type']}；样本：{profile['structure']['n']}；变量：{profile['structure']['p']}。",
             f"数据 SHA256：`{profile['source']['sha256']}`", "",
             f"检索后端：`{ranking['encoder']}`；状态：`{ranking['status']}`。", "",
             "| 方法 | 余弦分数 | 软惩罚 | 最终分数 |", "|---|---:|---:|---:|"]
    for candidate in ranking["ranked"]:
        lines.append(f"| {candidate['knowledge_id']} | {candidate['cosine']:.4f} | {candidate['penalty_total']:.4f} | {candidate['score']:.4f} |")
    lines.extend(["", "### 约束依据", ""])
    for candidate in ranking["ranked"]:
        lines.append(f"- [{candidate['knowledge_id']}]({candidate['source_url']})")
        for penalty in candidate["penalties"]:
            lines.append(f"  - {penalty['name']}: {penalty['severity']:.3f} × {penalty['weight']:.3f}；{penalty['reason']}")
    lines.extend(["", "## 执行与数值验证", "", f"状态：`{execution['status']}`；数值校验通过：`{execution['validation_passed']}`。",
                  execution["message"], "", "数组最多预览 10 项，完整数值保存在 execution.json。", "",
                  "```json", json.dumps(report_preview(execution["metrics"]), ensure_ascii=False, indent=2), "```",
                  "", "## 限制与待确认条件", ""])
    warnings = list(task["unknowns"]) + list(profile["unknowns"]) + execution["limitations"]
    for candidate in ranking["ranked"]:
        warnings.extend(candidate["unknowns"])
    lines.extend(f"- {warning}" for warning in dict.fromkeys(warnings))
    lines.extend(["", "## 被排除的方法", ""])
    for candidate in ranking["excluded"]:
        lines.append(f"- {candidate['knowledge_id']}: {'; '.join(candidate['hard_failures'])}")
    lines.extend(["", f"任务理解：{payload['configuration']['task_agent']}。统计数值由确定性工具计算；数值校验不等于统计假设成立。完整证据与诊断见 JSON 文件。", ""])
    return "\n".join(lines)


def run_pipeline(input_path: Path, goal: str, output_root: Path, *, sheet=0, encoder=None,
                 task_agent=None, knowledge_library='seed', **roles) -> Path:
    run_id = uuid4().hex
    folder = Path(output_root) / run_id
    folder.mkdir(parents=True, exist_ok=False)
    events = []
    start = time.perf_counter()
    encoder = encoder or LexicalEncoder()
    usage_before = dict(task_agent.client.usage) if task_agent else {}
    receipts_before = len(task_agent.client.receipts) if task_agent else 0
    payload = {"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
               "application_version": __version__,
               "status": "running", "events": events, "python": platform.python_version(),
               "versions": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "pydantic", "langgraph", "scikit-learn", "openpyxl"]},
               "configuration": {"goal": goal, "roles": roles, "sheet": sheet, "encoder": encoder.name,
                                 "knowledge_library": knowledge_library,
                                 "task_agent": task_agent.name if task_agent else 'rules',
                                 "alpha": 1.0, "penalty_lambda": 0.5, "mode": "C"},
               "usage": {"llm_calls": 0, "api_calls": 0, "tokens": 0, "api_cost_usd": 0,
                         "retries": 0, "note": "No API calls. Local model compute/download costs are not measured."}}
    try:
        state = build_graph(Path(input_path), goal, roles, sheet, encoder, events, task_agent, knowledge_library).invoke({})
        for name in ["task", "profile", "retrieval", "execution"]:
            payload[name] = state[name].model_dump(mode="json")
            dump(folder / f"{name}.json", payload[name])
        knowledge = [k.model_dump(mode="json") for k in state["knowledge"]]
        dump(folder / "knowledge.json", knowledge)
        payload["knowledge_sha256"] = hashlib.sha256(json.dumps(knowledge, sort_keys=True).encode()).hexdigest()
        payload["status"] = state["execution"].status
        (folder / "report.md").write_text(render_report(payload), encoding="utf-8")
    except Exception as exc:
        payload.update(status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if task_agent:
            payload['usage'] = {key: value - usage_before.get(key, 0) for key, value in task_agent.client.usage.items()}
            payload['usage'].update(api_cost_usd=None, note='Actual provider token counters; monetary cost not estimated without pinned pricing.')
            payload['llm'] = task_agent.client.metadata()
            payload['llm']['receipts'] = payload['llm']['receipts'][receipts_before:]
        if hasattr(encoder, 'model_metadata'):
            payload['embedding_model'] = encoder.model_metadata
        payload["elapsed_seconds"] = time.perf_counter() - start
        dump(folder / "run.json", payload)
        save_run(Path(output_root) / "profiles.sqlite3", run_id, payload)
    return folder
