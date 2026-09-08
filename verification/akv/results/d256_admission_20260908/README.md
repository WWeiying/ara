# D256 GGML Model Admission

Four completed cases revalidated from their original logs. No model rerun,
log replacement, tolerance relaxation, or substitution of an older PASS.

- Run: `hardware/akv_d256_efficiency_runs/model_admission_20260908/`
- Revision: `8fafaf3983e644a7bec1aa32aa0f32ec80fe1525`
- UTC interval: 2026-09-08 07:50:22 to 10:19:20.
- `models.csv`: per-case coverage and numerical summary.
- `models.json`: all parsed AKV calls, QBS profile counters, numerical summaries,
  fallback reasons, original run provenance, and source-file SHA-256 values.
- The original ELF, scripts, raw logs, and model disks remain in the run environment.

Each case compares RVV, QBS-only, and QBS+AKV for three generated tokens.
QBS executes the QEMU custom-instruction model; AKV uses the GGML functional
executor. These are model integration results, not native RTL model timing or
perplexity certification. Gemma QBS/RVV is not bit-exact; its short-prompt KL
of 0.0184498306 is close to the unchanged 0.02 decision-preservation threshold.
D256 Decode remains opt-in; D256 Prefill remains on fallback.

Revalidate into a new directory from the repository root:

```bash
python3 verification/akv/summarize_d256_admission.py \
  --run-root hardware/akv_d256_efficiency_runs/model_admission_20260908 \
  --output /tmp/d256_admission_recheck
python3 -m unittest discover -s verification/akv -p '*d256*.py'
```

Native RTL evidence is stored separately in `../d256_online_20260908/`.
