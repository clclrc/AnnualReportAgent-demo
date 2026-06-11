# Benchmark Notes

This repository exposes lightweight benchmark evidence without shipping the full private experiment workspace or the bulk 1000-case artifact archive.

## Included Artifacts

- `data/evaluation/pipeline_metrics.json`
  Public summary metrics over the original evaluation scope.

- `data/evaluation/performance_benchmark.json`
  Latency card over 4 representative public demo questions.

- `data/evaluation/regression_report.json`
  Lightweight regression gate over 4 representative public sample cards.

- `data/evaluation/open_badcase_sample_summary.json`
  Small open-question robustness sample for qualitative review.

- `data/public_bundle_manifest.json`
  Explicit public-bundle boundary for the trimmed demo dataset.

## Provenance

The public repo keeps public sample cards, summary metrics, and recomputation scripts:

- `evaluation/pipeline_metrics.py`
- `evaluation/run_regression.py`

This means reviewers can inspect both:

- the final metric numbers
- the code path that reproduces the public summary files from the bundled demo cards
- the exact boundary of the intentionally trimmed public dataset

## Main Takeaway

The most convincing signal in this demo is not a single accuracy number. It is the combination of:

- route-aware execution
- evidence-bearing outputs
- bounded public sample cards
- reproducible offline summaries

That combination is what makes the repository useful for LLM agent / RAG interviews.
