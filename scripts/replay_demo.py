import argparse
import json
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES_DIR = os.path.join(ROOT_DIR, "docs", "samples")


def load_sample(sample_name):
    sample_path = os.path.join(SAMPLES_DIR, "{}.json".format(sample_name))
    if not os.path.exists(sample_path):
        raise FileNotFoundError("Unknown sample: {}".format(sample_name))
    with open(sample_path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def list_samples():
    samples = []
    for filename in sorted(os.listdir(SAMPLES_DIR)):
        if filename.endswith(".json"):
            samples.append(filename[:-5])
    return samples


def render_sample(sample):
    route = sample["route"]
    lines = [
        "Sample: {}".format(sample["title"]),
        "Question ID: {}".format(sample["question_id"]),
        "Question: {}".format(sample["question"]),
        "Route: {} / {} / {}".format(
            route["question_type"],
            route["route_name"],
            route["route_label"],
        ),
        "Execution Path: {}".format(" -> ".join(route["execution_path"])),
        "",
        "Answer:",
        sample["answer"],
        "",
        "Evidence:",
    ]
    for index, item in enumerate(sample["evidence"], start=1):
        lines.append(
            "{}. [{}] {}".format(index, item["evidence_type"], item["content"])
        )
    lines.extend(
        [
            "",
            "Validation:",
            "- Regression case: {}".format("passed" if sample["validation"]["regression_passed"] else "failed"),
            "- Stored latency: {} ms".format(sample["validation"]["latency_ms"]),
            "- Artifact: {}".format(sample["validation"]["artifact"]),
        ]
    )
    if sample.get("notes"):
        lines.extend(["", "Notes:", sample["notes"]])
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Replay stored public demo samples for AnnualReportAgent-demo.")
    parser.add_argument("--sample", default="structured_field_qa", help="Sample name under docs/samples/")
    parser.add_argument("--list", action="store_true", help="List available samples and exit")
    parser.add_argument("--json", action="store_true", help="Print the sample JSON instead of a formatted replay")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.list:
        for name in list_samples():
            print(name)
        return 0

    try:
        sample = load_sample(args.sample)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(sample, ensure_ascii=False, indent=2))
        return 0

    print(render_sample(sample))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
