# Portability Stage 2 Evidence

This is a small, committed snapshot of measured results, not a replacement for
the original logs and binaries. The original paths and hashes are recorded in
the CSV/JSON files. Hardware configuration: four lanes, VLEN=1024, simulation-only
L2=16 MiB; no RTL or synthesis change in this stage.

- `rtl.csv`: ten measured same-capture runs, including the slower initial
  portable implementation. The final portable runs are in cohort `r3`.
- `rtl_all_metrics.csv`: every LLM_PERF phase plus AKV command totals. Do not
  sum the repeated command totals across phases.
- `models.json`: model metrics, QBS native execution, AKV functional coverage,
  and original failed experiments. `r3` Refact failed before its numerical
  executor was corrected; that failure is intentionally retained.
- `selected_models.json`: explicit final selection, independent of pass/fail.
  Qwen2.5/Qwen3/Gemma use `r3`; Refact uses `r4`.
- `finalize.status.json`: strict final validation of the selected model runs,
  RTL records, and the native feature/QBS/AKV/RVV handoff regression.
- `summary.md`: compact view of all cohorts. `PASS_REVALIDATED` means that the
  original worker's collection failed, but its unchanged completed log passed
  the corrected strict collector. The original worker status is retained.

The QEMU runs use native QBS instructions and the GGML AKV functional executor.
They are not complete-model native AKV RTL simulations. The final AKV logits
are identical to QBS_ONLY for three records per model; this is not a general
perplexity or long-generation quality guarantee. Model QBS/RVV comparisons
are recorded separately in `models.json`.

See `hardware/docs/qbs_akv_portability_work.md`, section 6, for the root-cause
analysis, supported boundaries, exact dimensions, and reproduction commands.
