import json
import os


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(ROOT_DIR, "evaluation")
SAMPLES_DIR = os.path.join(ROOT_DIR, "docs", "samples")
OUTPUT_DIR = os.path.join(ROOT_DIR, "data", "evaluation")


def load_json(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def main():
    cases = load_json(os.path.join(EVAL_DIR, "regression_cases.json"))
    results = []

    for case in cases:
        sample = load_json(os.path.join(SAMPLES_DIR, "{}.json".format(case["slug"])))
        route_name = sample["route"]["route_name"]
        has_answer = bool(str(sample.get("answer", "")).strip())
        has_execution_path = bool(sample["route"].get("execution_path"))
        has_evidence = bool(sample.get("evidence"))
        passed = has_answer and has_execution_path and has_evidence and route_name == case["expected_route_name"]

        results.append(
            {
                "id": case["id"],
                "name": case["name"],
                "expectation": case["expectation"],
                "passed": passed,
                "has_answer": has_answer,
                "has_execution_path": has_execution_path,
                "route_name": route_name,
                "status": "success" if passed else "failed",
                "success": passed,
                "failure_reason": None if passed else "public_sample_mismatch",
                "answer_preview": sample.get("answer", "")[:120],
            }
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "regression_report.json")
    with open(output_path, "w", encoding="utf-8") as file_obj:
        json.dump(results, file_obj, ensure_ascii=False, indent=2)
    print(output_path)


if __name__ == "__main__":
    main()
