import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "evaluation"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_pipeline_metrics_summary_is_present():
    subprocess.run([sys.executable, "evaluation/pipeline_metrics.py"], cwd=ROOT_DIR, check=True)
    metrics = load_json(DATA_DIR / "pipeline_metrics.json")

    assert metrics["classification"]["summary"]["exact_accuracy"] == 0.944
    assert metrics["classification"]["summary"]["bucket_accuracy"] == 0.998
    assert metrics["sql_success"]["summary"]["sql_generation_success_rate"] == 1.0
    assert metrics["sql_success"]["summary"]["sql_execution_success_rate"] == 1.0
    assert metrics["public_demo"]["summary"]["replay_sample_count"] == 4


def test_regression_report_is_green():
    subprocess.run([sys.executable, "evaluation/run_regression.py"], cwd=ROOT_DIR, check=True)
    report = load_json(DATA_DIR / "regression_report.json")

    assert len(report) == 4
    assert all(item["passed"] for item in report)
