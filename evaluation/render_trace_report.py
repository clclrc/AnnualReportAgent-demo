import json
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")


def render_trace(question_id: str):
    trace_path = os.path.join(DATA_DIR, "workflow", "{}.json".format(question_id))
    if not os.path.exists(trace_path):
        raise FileNotFoundError(trace_path)

    with open(trace_path, "r", encoding="utf-8") as file_obj:
        trace = json.load(file_obj)

    lines = []
    lines.append("# Trace Report")
    lines.append("")
    lines.append("- question_id: {}".format(trace["question_id"]))
    lines.append("- question_type: {}".format(trace["question_type"]))
    lines.append("- route_name: {}".format(trace["route_name"]))
    lines.append("- status: {}".format(trace.get("status")))
    lines.append("- failure_reason: {}".format(trace.get("failure_reason")))
    prompt_versions = trace.get("prompt_versions", {})
    lines.append("- prompt_registry_version: {}".format(prompt_versions.get("registry_version")))
    lines.append("")
    lines.append("## Execution Path")
    lines.append("")
    for stage in trace.get("execution_path", []):
        lines.append("- {}".format(stage))
    lines.append("")
    lines.append("## Context")
    lines.append("")
    context = trace.get("context", {})
    for key in ["original_question", "question_keywords", "years", "company", "abbr", "sql"]:
        lines.append("- {}: {}".format(key, context.get(key)))
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    for item in trace.get("evidence", []):
        lines.append("- [{}] {}".format(item.get("evidence_type"), item.get("content", "")[:160]))
    lines.append("")
    lines.append("## Route Trace")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(trace.get("route_trace", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Answer Preview")
    lines.append("")
    lines.append(trace.get("answer_preview", ""))
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python evaluation/render_trace_report.py <question_id>")
    print(render_trace(sys.argv[1]))


if __name__ == "__main__":
    main()
