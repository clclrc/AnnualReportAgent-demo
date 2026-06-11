import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def run_replay(*args):
    return subprocess.run(
        [sys.executable, "scripts/replay_demo.py", *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )


def test_replay_list_contains_public_samples():
    result = run_replay("--list")
    output = result.stdout.strip().splitlines()

    assert "structured_field_qa" in output
    assert "sql_ranking_qa" in output
    assert "open_report_boundary" in output


def test_replay_sample_json_output():
    result = run_replay("--sample", "structured_field_qa", "--json")
    payload = json.loads(result.stdout)

    assert payload["question_id"] == 1
    assert payload["route"]["route_name"] == "structured_precise_qa"
    assert "14908230.95" in payload["answer"]
