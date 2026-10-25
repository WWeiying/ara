# H/S/B Diagnostic Retirement Analysis

New offline-only analyzer. It does not launch simulations, build programs, edit
RTL, certify independent UVM, or promote diagnostic timings into mirrored
performance acceptance. Old Q4/Q8 accepted traces without scalar retirement
cannot establish these results. No actual diagnostic result exists yet.

## Preparation Interface

Actual UART protocol, aligned with `../worker/check.py` and the preparation
renderer's diagnostic prefix (no adaptation of old six-call transcripts):

```
QUANT_DIAG_HSB_CAP kind=1 heads=6 d=128 visible=128 kv_head=0 trials=3 scale=3db504f3 k_token_stride=144 v_token_stride=272 workspace=13120
QUANT_DIAG_HSB_BEGIN trial=0 mode=0
QUANT_DIAG_HSB_RESULT trial=0 mode=0 cycles=... [unchanged full result fields and 768 output words]
... trial=1 mode=1 ...
... trial=2 mode=2 ...
QUANT_DIAG_HSB_SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0
Core Test *** SUCCESS ***
```

Keep the original result fields and numerical/work predicates. This analyzer
checks the diagnostic identity, order, extent, declared work/flags and exact
timing. The preparation/worker checker still owns original golden comparisons,
input retention, guards, actual eight QBS_PERF records and independent UVM.
There are no mirror repetitions in this diagnostic. No `repeats_exact=1` claim.

Core API:

```python
elf = LinkedELF(elf_bytes)
instructions = disassembly_map(actual_objdump_text, elf)
calls = call_log(raw_log)
report = analyze(instructions, commit_stream, calls,
                 [actual_start_csr_pc, actual_end_csr_pc], phase_map)
```

The caller must use the **new ELF**, not old call timing or old measurement PCs.
Exactly two `CSRRS rd,cycle,x0` instruction sites and six retired occurrences
are required. If compilation creates different sites, stop for explicit source
review; do not search for any convenient matching cycle differences. Every
in-window retired instruction must match executable ELF bytes and linked
disassembly. Sized ELF STT_FUNC symbols, not next-label guesses, define functions.

## Monitor and Accounting Contract

Primary sources inspected:

- `hardware/tb/ara_commit_monitor.sv:72-89,247-264`: COMMIT_TRACE header, RVFI
  PC/instruction/destination value, sequential `order`, ordered commit ports.
- `verification/akv/run_refill_overlap_probe.py:48-54,191-213`: immutable strict
  CSV parser reused directly; this helper and monitor source are input-pinned.
- `verification/akv/paired_heads/analyze_attention.py:49-127`: earlier exact
  CSR pairing and architectural-retire accounting, not copied old acceptance.
- `verification/akv/quantized_kv/attention_threeway_main.c`: the original timed
  window includes Query quantization, plan/mapping, online computation and drain;
  output verification/UART are after the end CSR.
- `software/qbs/src/qbs_native_riscv.c:45-106`: this Q4/H6 fixture executes
  alternating M4/M2 commands `06b5045b,02b5045b`, four token panels. Require
  zero commands in H/S, exactly that eight-word retirement sequence in B.

All retire orders must be contiguous from zero; same-cycle ports must increase.
Unknown CSV fields, X values, missing/extra boundaries, traps inside windows,
changed instructions and mismatched CSR deltas reject analysis. Non-retire
`arch_start`, `uop_alloc`, `uop_done`, `cvx_req/resp` records are parsed but never
counted as architectural instructions. Analysis failure is not downgraded to a
successful partial result.

Each `rd_wdata` end-minus-start (unsigned 64-bit) must equal that diagnostic
call's printed cycles exactly. Separately report monitor end-retire minus
start-retire and its difference from the CSR delta. CSR execution and retirement
are not simultaneous; **do not force equality of these two spans**.

Instruction counts exclude both CSR boundaries. Descriptive interval accounting
uses `[previous retirement cycle, next retirement cycle)` and assigns the gap to
the **next** retired PC's function/phase. The final end-CSR gap is separate;
same-cycle retirement contributes zero gap. These bins must sum to the monitor
retirement span, not application cycles. They are PC-context interarrival
accounting, NOT function execution time, exclusive stalls, busy time, issue
occupancy or FPU utilization. No call-stack inference is made.

## Phase Coverage

`online.h` is inlined into `main` and `akv_quant_strided_execute`; QK callbacks
can also inline at O3. Whole-function labelling of either mixed orchestration
function is forbidden. Admission, gathering and softmax are **not** inferred
from these function names. Without proven PC ranges they remain
`unclassified_orchestration`. Independently linked quantize/decode/dot/expf/
scale/mad/native-command functions can be mapped after inspecting the actual
new ELF. No claim of exact stage coverage is made merely because such functions
exist. Helpers shared across callers are not charged to an assumed caller stage.

Phase map format, with only symbols actually present in this ELF:

```json
{
  "schema": "quantkv_phase_map_v1",
  "functions": {},
  "ranges": []
}
```

Optional reviewed ranges have string fields `start`, `end` (exclusive),
`function`, `phase`, `evidence`. Require exact instruction boundaries, one actual
function, no gaps or overlapping ranges. `evidence` records the reviewed machine
PC/source derivation, not a fabricated source line. If actual debug information
exists, `objdump -dl` can support that review; ordinary `-d` alone does not prove
inline source stages. The analyzer verifies range geometry, **not the semantic
truth of an annotation**. Do not supply fine-stage ranges without the separate
source/machine review. Default empty ranges intentionally leave orchestration
unclassified. Report mapped/unmapped retired instruction counts in every window.
`ALL_RETIRED_PCS_LABELLED` would still not mean all stages precisely measured.

## Offline CLI and Evidence

The input manifest uses schema `quantkv_phase_inputs_v1`, exact keys `schema`,
`files`, `start_pc`, `end_pc`. `files` has exactly `elf`, `log`, `commit`,
`phase_map`, `objdump`, `monitor`, each `{ "path": "...", "sha256": "..." }`.
Paths resolve relative to the manifest (absolute paths also work). Use the actual
image's pinned monitor, not an unrelated current source. The caller's image/run
receipt must establish that provenance; this analyzer is not an image validator.
Supply the independently reviewed manifest SHA explicitly. Pre/post hash checks
cover these files, analyzer/test/README, CSV parser and Python executable.

```sh
python3 verification/akv/quantized_kv/phase_diagnostic/analysis/analyze.py \
  --inputs /absolute/diagnostic-analysis-inputs.json \
  --inputs-sha256 REVIEWED_SHA256 --output /absolute/fresh-analysis-output
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/phase_diagnostic/analysis -p 'test_*.py'
```

CLI runs only the pinned GNU objdump `-d` (120-second bound), reads the linked
ELF and streams COMMIT_TRACE. No compiler, EDA or background worker. It emits
disassembly/stderr, pins and result only after complete proof and post-identity
checks. Host tests use synthetic ELF/retire fixtures and mock the CLI subprocess;
they are parser/contract tests, not RTL or real phase coverage evidence.

## Review Checkpoint

Host suite: **13 tests PASS** on 2026-10-25. Includes CSR/own-cycle mismatch,
missing/duplicate retirement, X/unknown events, changed ELF/instructions,
wrong custom work, two-port same-cycle ordering, CSR wrap, scalar-CSR versus
FP classification, phase-range boundaries, actual diagnostic-only protocol,
and mocked CLI finalization/post-pin drift. No real diagnostic trace has been
analyzed and no exact softmax/gather/admission coverage is claimed. The worker's
`retirement.py` can call the core API directly after its independent numerical
checker; it need not use the standalone CLI's deliberately smaller log check.
