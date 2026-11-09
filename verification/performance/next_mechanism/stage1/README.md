# Stage 1: evidence and model-node timing

Status: cross-linked, **not board-qualified**. No new RTL, synthesis, or board run.
The planning/acceptance contract is
[`INFERENCE_NEXT_STAGE1_DECISION_20261109.md`](../../../../hardware/docs/INFERENCE_NEXT_STAGE1_DECISION_20261109.md).

## Source and build identities

`audit.py` reconciles original evidence without rewriting it. `prepare_replay.py`
derives bounded 1..32-step fixed-history frontends from the exact previously
measured source. It does not replace the real model by a synthetic microkernel.
`node_probe/prepare.py` instruments the original CPU execution loop without
scheduler callbacks, subgraph splitting, extra fences, or changes to fusion.

Build outputs are outside the main worktree:

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/
  stage1_node_build_20261109_02/
```

`result.json` and `commands.json` record the independent cross-build. The
macro-disabled CPU object is byte-identical to the frozen accepted object.
Only the new probe archive's CPU-loop object is replaced. All other archive
members, the original archives and original source trees are preserved.
The probe collector is compiled with auto-vectorization disabled.

| Program | SHA256 |
| --- | --- |
| stage1-plain | f71742f4d5f726908305aced5bb7b41edab15e4e4a338e0e2a6d92dc2b5180ea |
| stage1-probe | 1505993020fbef60c200c3251f880f39072f2efb83f5aa4330f61292b76bf30a |

These identities are not a model acceptance or evidence of performance.

## Three measurement modes

| Mode | CPU-loop metadata | CLOCK_MONOTONIC per unit | Purpose |
| --- | --- | --- | --- |
| plain | No | No | Complete-call control |
| metadata | Yes | No | Quantify common recording cost; verify path |
| timed | Yes | Yes | Attribute software node elapsed nanoseconds |

OFF/ON alone does **not** measure total probe overhead: metadata exists in both.
Compare all modes using identical prompt/history/model, single worker, F16 KV,
M4/cache/context settings, bitstream and clock. First use 4 decode steps after
the full 135-token prompt; expand only if the initial tool acceptance passes.
Suggested order: plain, metadata, timed, plain. Each executable loads the model
afresh; loading is separately timed, not included in compute totals.

This is a new measurement ELF, not the accepted application's binary. All three
modes enable QBS aggregate counters, while disabling per-call, tensor and
lifetime printing. In the pinned `qbs.cpp`, `record_command` updates counters
after callback completion and `print_trace_summary` runs through `atexit`.
These are software witnesses, not an independent hardware PMU. The checker
requires equal per-format native commands, M-distribution, context activity and
dot work across the three modes, with zero emulation.

AKV TRACE remains disabled because the pinned backend prints individual
Prefill/Decode executions and fallbacks inside calls. AKV leaf wrappers still
count completed paths. This differs from the earlier trace-enabled campaign
and must be retained in reports, not described as an identical rerun. No hardware
service time is inferred from a CPU node name. The earlier `_01` build/package
is preserved but superseded for this measurement; do not mix its ELF with the
new QBS-TRACE-enabled launcher.

## Board handoff, not automatic deployment

Do not interrupt another board campaign, replace its executable, reset the
board, change the kernel counter permissions, or reprogram its bitstream.
After the board owner grants a window, copy the two ELF files plus
`frontend/prompt_qwen.txt`, `frontend/history.txt` and `run_board_probe.sh` into a
new directory. Verify ELF and input hashes against build records. Record model,
bitstream and clock identities independently before the campaign.

Example after copying to an agreed board directory (paths are placeholders):

```sh
sh run_board_probe.sh /new/probe_bundle /qwen3.gguf \
  /new/probe_bundle/prompt_qwen.txt /new/probe_bundle/history.txt \
  /new/results/plain_01 plain 4
```

Repeat with fresh outputs for `metadata`, `timed`, and the second `plain`.
The launcher does not set NORMAL_MEMORY eligibility or override auto head
selection. Existing memory eligibility and fallback checks remain in force.
Run only on the board configuration for which those checks were established.

## What must be checked before using measurements

- All return codes and phase counts; no missing, duplicate or partial reports.
- Exact input token IDs and the full logits binary across all three modes;
  greedy token agreement alone is insufficient.
- Metadata/timed path fingerprints **and** actual member records, op/shape/name
  and fused spans. Hash agreement is a quick check, not the only check.
- Identical actual route/work under the current runtime selection; timing a
  fallback accidentally is not evidence for the selected accelerator path.
  QBS exit counters must be present and consistent, not simply omitted.
- Valid probe reports with no overflow, unsupported mode or clock error.
- Only the first member of a fused unit owns elapsed time. Followers have null
  elapsed time and must never be counted a second time.
- Sum of unit intervals plus unattributed time equals the probe phase interval.
  This phase interval is adjacent to, not exactly identical to, the frontend
  timer. No-sync intervals do not independently prove accelerator completion.
- Compare `prefill_compute_ns` and individual/cumulative `decode_compute_ns`.
  `inference_window_ns` includes node-file export and cannot measure pure compute.
- Total probe perturbation target <=2% against plain, with paired-repeat
  variation reported. This is a project threshold, not an industry standard.
- Short Decode profiles cannot establish long-context Attention shares.

Collection stores complete JSON records after each synchronized call, not in
the node loop. Copy results only after completion. Do not include transfer,
logits export, or model loading as a node's execution time.

After collecting four complete directories:

```sh
python3 verification/performance/next_mechanism/stage1/check_probe.py \
  --trials /results/plain_a /results/metadata /results/timed /results/plain_b \
  --output /new/check_output
```

The checker validates raw progress, full binary logits, actual fused-member
paths, completed-work counters and time accounting. It groups a fused operation
sequence as one category, never assigning its full time to each member.
`LOCAL_DATA_CHECKED_EXTERNAL_IDENTITY_PENDING` deliberately does not mean board
acceptance: model/bitstream/ELF/environment identity needs independent evidence.

## Local tests

```sh
python3 -m unittest discover -s verification/performance/next_mechanism/stage1 -p 'test_*.py' -v
python3 -m unittest discover -s verification/performance/next_mechanism/stage1/node_probe -p 'test_*.py' -v
```

Host clock tests exercise fused accounting, metadata mode, overflow, bad order,
unsupported worker counts, execution failure, clock failure and JSON escaping.
These qualify the collector, not the actual model, RTL, or board.
