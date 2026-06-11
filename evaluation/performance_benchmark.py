import json
import os
import sys
import time


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "evaluation")

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.service_api import QueryRequest, query


BENCHMARK_CASES = [
    {"id": 0, "question": "无形资产是指什么？"},
    {"id": 1, "question": "请告诉我龙岩卓越新能源股份有限公司2021年的应付账款的具体数值"},
    {"id": 2, "question": "2019年负债总额第2高的上市公司是？"},
    {"id": 26, "question": "当升科技2019-2020年这两年的法定代表人是否都相同？"},
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []
    started_at = time.perf_counter()
    for case in BENCHMARK_CASES:
        case_started_at = time.perf_counter()
        response = query(QueryRequest(question=case["question"], question_id=case["id"]))
        elapsed_ms = round((time.perf_counter() - case_started_at) * 1000, 2)
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "success": response.success,
                "status": response.status,
                "route_name": response.route_name,
                "question_type": response.question_type,
                "latency_ms": elapsed_ms,
                "route_trace_performance": response.route_trace.get("performance", {}),
            }
        )

    report = {
        "benchmark_count": len(results),
        "total_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "avg_latency_ms": round(sum(item["latency_ms"] for item in results) / len(results), 2) if results else 0.0,
        "results": results,
    }
    output_path = os.path.join(OUTPUT_DIR, "performance_benchmark.json")
    with open(output_path, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
    print(output_path)


if __name__ == "__main__":
    main()
