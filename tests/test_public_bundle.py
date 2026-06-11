import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_public_bundle_is_trimmed_and_documented():
    manifest_path = ROOT_DIR / "data" / "public_bundle_manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["pdf_info_records"] == 14
    assert manifest["company_table_rows"] == 14
    assert len(manifest["public_sample_slugs"]) == 4

    for folder_name in ["answers", "workflow", "classify", "keywords", "sql", "test"]:
        assert not (ROOT_DIR / "data" / folder_name).exists()


def test_env_example_exists():
    assert (ROOT_DIR / ".env.example").exists()
