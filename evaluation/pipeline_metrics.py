import json
import os


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARK_CARD_PATH = os.path.join(ROOT_DIR, "benchmarks", "benchmark_card.json")
OPEN_BADCASE_SUMMARY_PATH = os.path.join(ROOT_DIR, "data", "evaluation", "open_badcase_sample_summary.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "evaluation", "pipeline_metrics.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def main():
    benchmark_card = load_json(BENCHMARK_CARD_PATH)
    open_badcase_summary = load_json(OPEN_BADCASE_SUMMARY_PATH)
    metrics = benchmark_card["metrics"]
    sample_ids = benchmark_card["public_demo_scope"]["public_sample_ids"]

    report = {
        "provenance": {
            "note": "Public demo snapshot rebuilt from bundled benchmark cards instead of the full private artifact archive.",
            "benchmark_card": "benchmarks/benchmark_card.json",
            "open_badcase_summary": "data/evaluation/open_badcase_sample_summary.json",
        },
        "classification": {
            "definition": {
                "classification_accuracy": "Original evaluation exact classification accuracy from the private benchmark run.",
                "bucket_accuracy": "Original evaluation route-bucket accuracy from the private benchmark run.",
            },
            "summary": {
                "evaluated_count": 1000,
                "exact_accuracy": metrics["classification_exact_accuracy"],
                "bucket_accuracy": metrics["route_bucket_accuracy"],
            },
        },
        "sql_success": {
            "definition": {
                "sql_generation_success_rate": "Original evaluation SQL generation success rate.",
                "sql_execution_success_rate": "Original evaluation SQL execution success rate.",
            },
            "summary": {
                "expected_sql_count": 200,
                "sql_generation_success_rate": metrics["sql_generation_success_rate"],
                "sql_execution_success_rate": metrics["sql_execution_success_rate"],
            },
        },
        "answer_accuracy": {
            "definition": {
                "structured_answer_accuracy": "Original evaluation structured-question answer accuracy.",
                "open_answer_accuracy": "Original evaluation open-question answer accuracy.",
            },
            "summary": {
                "structured_answer_accuracy": metrics["structured_answer_accuracy"],
                "open_answer_accuracy": metrics["open_answer_accuracy"],
                "structured_count": 700,
                "open_count": 300,
            },
        },
        "public_demo": {
            "summary": {
                "replay_sample_count": len(sample_ids),
                "replay_sample_ids": sample_ids,
                "open_badcase_sample_count": open_badcase_summary["sample_count"],
                "open_badcase_success_count": open_badcase_summary["success_count"],
                "avg_latency_ms": metrics["avg_latency_ms"],
            }
        },
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
