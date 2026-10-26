# Fixed-size field-copy: paired complete-Attention result

## Scope

Two freshly linked programs compare `839a0362` against `083d4ed8` on the same
canonical VCS RTL image. Only the fixed-size field-copy implementation and its
compiled consequences differ. No RTL, hardware parameter, numerical policy,
runtime opt-in default, or external llama.cpp source was changed for this pair.

The original real-model capture supplies Q4_0 K, Q8_0 V, six query heads in one
selected KV-head group, D=128 and 128 visible tokens. Original strided backing
storage, model gold, mask and scale are retained. This is a complete Attention
call for that captured group, not an entire layer or model execution.

Each program performs H/S/B/B/S/H, producing 768 FP32 values per call:

- H: head-major RVV; one value decode per head and token.
- S: shared-schedule RVV; value decoding is reused across heads.
- B: shared quantized Attention using native QBS DIRECT for QK and RVV for
  remaining work. B is not an AKV F16 command path.

The timed interval includes query quantization and actual Attention work. B also
includes GGML tensor mapping, admission, strided panel preparation and native
execution. Completion drain precedes the ending cycle read; output checking and
printing follow it. Top-level fixture construction and output clearing remain
outside the interval identically in both programs.

## Fresh paired cycles

| Mode | Baseline calls | Candidate calls | Baseline sum | Candidate sum | Fewer cycles | Speedup |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| H | 1587996, 1583123 | 1505915, 1503639 | 3171119 | 3009554 | 5.09% | 1.0537x |
| S | 876887, 878145 | 862636, 863509 | 1755032 | 1726145 | 1.65% | 1.0167x |
| B | 567130, 570632 | 476050, 475661 | 1137762 | 951711 | 16.35% | 1.1955x |

Fewer cycles = `(baseline sum - candidate sum) / baseline sum`; speedup =
`baseline sum / candidate sum`. Both repetitions improve in every mode.
The primary new result is B's 16.35% cycle reduction, not a reused historical
baseline. Candidate B averages 475855.5 cycles per call.

Within the candidate executable, H/B is 3.1623x and S/B is 1.8137x. These are
different comparisons: H/B includes software scheduling and QBS, whereas the
1.1955x paired result measures this latest software change. None is whole-model
speedup or pure hardware speedup.

Native QBS work is unchanged: 8 commands, 4 K panels, 9216 gathered bytes and
6 query quantizations per B call. The sum of QBS busy cycles over the two B
calls is 17609 on both sides (8805/8804 versus 8804/8805). The full-call gain
therefore is not an increase in the measured QBS compute throughput. It is
consistent with removing small-copy call overhead and enabling better compiled
software around the device. Identical ordinary linker rules allow natural
code/data-layout changes; no exclusive per-instruction attribution is claimed.
Whole-run AXI request counts are not ROI memory-traffic counters.

## Correctness and identity checks

- Both original suites terminate successfully, with all six calls present.
- Each side checks 4608 output words against original model gold using the
  existing absolute/relative tolerance; all guard bytes and output padding pass.
- H and S remain bit-identical within each program. Mirrored same-mode outputs
  and FCSR/VCSR are exact. Every corresponding output word, CSR and workload
  count is also exact across the two executables (4608 cross-binary pairs).
- Native QBS emits exactly 16 command records per program; actual descriptors,
  command/work counts and RTL performance-record schema pass the original checks.
- Independent event/backend/AXI-read/AXI-write checks all pass with no issues.
  Both sides observe 266705 contract events and 449932 UVM backend events.
  All AXI requests complete with zero pending/aborted reads or writes.
- Same compiler flags, floating-point policy, original object order, input bytes
  and actual simulator image are checked. All 3 objects affected by changed
  inline headers were rebuilt per side; the 14 reused objects have dependency
  and hash evidence. Both image and input identities pass before/after checks.
- The offline collector rechecks raw numerical evidence, closed protocol
  receipts and hashes; it does not launch a simulator or substitute old timings.

Both runs started 2026-10-26 08:22:24 UTC. Baseline worker finished at 11:15:38
(about 2h53m), candidate at 10:53:06 (about 2h31m), including checking. There was
one simulator launch per side, no retry and no timeout extension.

## Evidence and reproducibility

All paths below are relative to this verification worktree:

| Artifact | Path |
| --- | --- |
| Frozen preparation | `prepare/out/build-gnu-06/build.json` below this directory |
| Parent launch review | `parent-review-20261026.json` below this directory |
| Baseline raw evidence | `verification/out/field-copy-baseline-20261026-01/` |
| Candidate raw evidence | `verification/out/field-copy-candidate-20261026-01/` |
| Offline collection | `verification/out/field-copy-pair-collection-20261026-01/` |
| Final parent acceptance | `verification/akv/results/field-copy-pair-acceptance-20261026.json` |
| Source/runtime switch inventory | `hardware/docs/qbs_akv_software_paths.md` |

The final acceptance is a new receipt. Frozen launch review, build evidence,
worker helpers, original side results and pending-parent collector receipt are
not rewritten. Raw traces and generated builds remain local artifacts; the Git
receipt pins their identities rather than embedding large traces in the repo.

The existing helper is shared with the GGML quantized-KV path through its SDK
source root. Old llama.cpp binaries do not acquire the inline change without
rebuilding affected objects and relinking. External runtime rebuild, broader
shape/model performance, synthesis and FPGA evaluation remain separate work;
none is needed to interpret this bounded paired software measurement.
