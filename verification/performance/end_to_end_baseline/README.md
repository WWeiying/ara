# End-to-end baseline evidence replay

`audit.py` implements the first, read-only step of the end-to-end performance
plan. It does not build software, start VCS/QEMU, access the board, alter a sealed
input, or promote an experimental runtime. Separate reconstruction and bounded
QEMU experiments are described below; they do build and execute software.

Run from the Ara repository:

```sh
python3 -B -m unittest discover \
  -s verification/performance/end_to_end_baseline -p 'test_*.py' -v
python3 -B verification/performance/end_to_end_baseline/audit.py \
  --output verification/performance/evidence/end_to_end_baseline_next
```

The output directory must not exist. Explicit `--ara`, `--llama`,
`--verification` and `--board` arguments override the local evidence locations.
Missing or changed inputs fail the replay; the tool does not fetch substitutes.
The external evidence and checker sources must be trusted local campaign inputs.

## What is checked

- Current repository commits, delivery commits and hashes of tracked local
  differences are recorded separately. Local differences are not build inputs.
- The board campaign's final requirements audit anchors four accepted observer
  receipts. Their source pins and collected artifacts are rehashed; unsafe,
  duplicate and escaping collection paths are rejected.
- The original F16 full-answer, M4 ABBA, quantized native full-answer and Q4/Q8
  restored-prefix grid checkers run again on the collected data. Returned fields
  must match the accepted receipts, including negative results and limitations.
- The existing graph schedule checker replays the historical QEMU log. This is
  a log-level functional replay, not revalidation of every old build input.
- Output preserves software candidate versus production identities and leaves
  hardware per-stage fractions unknown. QEMU timestamps are never converted to
  hardware timing.

## Result and remaining work

`EVIDENCE_REPLAY_PASS_STAGE_ATTRIBUTION_PENDING` means the existing records
passed replay, **not** that a new simulator, current RTL or a newly compiled
model passed. The result includes complete-application paired measurements,
graph/reuse evidence and the gates still required for stage attribution.

The initial replay is stored in
`verification/performance/evidence/end_to_end_baseline_20261105_01/result.json`.
No raw external log or model is duplicated here. Reproducing the audit requires
the referenced local archives. No new timing measurement is claimed.

See `hardware/docs/LLAMA_END_TO_END_BASELINE_AUDIT_20261105.md` for the Chinese
conclusions and the narrowed next experiment.

## Reconstruct the previously measured trace-context change

`prepare_trace.py --output <fresh-directory>` extracts the fixed llama.cpp
delivery sources, applies `trace-context.patch`, checks the exact measured
postimage, and repeats GCC/Clang host checks. It does not modify the dirty llama
checkout or rebuild/replace the complete production binary. Configuration is
sampled at each blocking execution context, not once per native command.

## Output residency experiment

```sh
python3 -B verification/performance/end_to_end_baseline/run_output_tile.py \
  --suite online \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/output_online_next
```

Available suites are `leaf`, `online`, `runtime`, and `entry`. Each requires a
new output directory. Each compiles pinned sources and runs bounded VLEN1024
and VLEN256 QEMU guests. No board access or RTL performance is implied.

- `leaf`: scalar FMA oracle, old Register-PV, and output-resident leaf; includes
  actual captured V and unaligned Q8_0 byte payloads.
- `online`: complete Softmax/PV schedule with controlled QK callbacks; checks
  recurrence state, results, flags, callback sequence and terminal failures.
- `runtime`: existing layout/selector/descriptor fixture with a QBS reference
  executor, redirected to the independent `quant_output_tile_execute` symbol.
- `entry`: actual CSR/VLEN rejection without issuing work or changing outputs.

`collect_output_tile.py --leaf <dir> --online <dir> --runtime <dir> --entry <dir>
--output <new-json>` rechecks current source identities, ELF hashes and raw guest
verdicts. The accepted receipt is
`verification/performance/evidence/output_tile_20261106_01/result.json`.
The failed original runtime tests remain in the external run area; their
diagnostic translation unit is `test_output_binding.c` and their exact compiler
commands remain in those runs' `commands.json` files.

The prototype is not a production default. Its `value_decodes` retains the
existing logical-row report definition; it is **not** a physical decode counter
because multiple head pairs re-read V. See
`hardware/docs/LLAMA_OUTPUT_RESIDENCY_EXPERIMENT_20261106.md` for costs and the
required real-QK, RTL and model gates. The overall architectural goal remains
broader than this experiment and permits justified additional hardware.
