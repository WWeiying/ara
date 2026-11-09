# Resident PV component gate

This record separates measured software behavior, an isolated hardware
experiment, and still-unimplemented SoC integration. Output paths below are
relative to `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out`.
No synthesis, FPGA source replacement, bus change or runtime deployment occurs.

## Accepted comparison

The matched software experiment `resident_pv_rotation_vcs_20261108_02` passed
its original checks and the independent strict-schema audit. The fixed ELF is
`b807a0427b961fdbd180172293126a4238e0d92600fc6e2302fa82693b9e9abf`.
`resident_pv_rotation_attribution_20261108_02.json` records:

| Mean cycles | Native auto | Rotation plus loop layout |
| --- | ---: | ---: |
| Complete Qwen3 attention call | 36783.0 | 34213.5 |
| QK helpers | 9900.5 | 9901.5 |
| PV helpers | 6623.5 | 4411.0 |
| Remaining work | 20259.0 | 19901.0 |

The complete-call speedup is 1.07510x. This is not a model-level result, not a
new-hardware result and not an isolated measurement of WAR cost. Both arms
use native-auto; the candidate changes register rotation and loop layout.
The next hardware comparison must beat the stronger candidate, not the
earlier generic or single-source-register baseline.

## Exact real-model input extraction

`extract_real.py` created `resident_pv_real_operands_20261108_01.json` with
12 cases: three tiles (64,64,9 tokens), two heads, D128 and all four lanes.
It reads retired FP16 conversion results, accepted rescaled-seed writes,
resident V replay writes and every corresponding FMA result from the original
passing trace. Each replay value is checked against the hashed model-captured
tensor with Ara's actual EW16 lane permutation.

All **35072 scalar FP16 FMAs** agree bit-for-bit with independent Spike
SoftFloat, at every intermediate recurrence, not only the last output.
The corpus contains FMA-only flag expectations. Preparation flags are kept
separate; they cannot be obtained by subtracting sticky flag masks.

This extraction is host-side evidence and stimulus preparation, not a new
controller test or another complete SoC simulation. Input and extractor hashes
are included in its artifact inventory. Existing successful traces are reused;
there is no extra long-running SoC run just to capture these operands.

## Controller status

The experimental controller has no arithmetic instance. It exposes a borrowed
FPU interface, 16 local 64-bit accumulator slots, two ingress entries and
per-slot in-flight ownership. It preserves token recurrence, waits for accepted
results, masks tails, accumulates flags and supports cancellation before writes
become irrevocable. Its testbench uses the frozen baseline FPNew FP16 SIMD slice
and independently calculated expected arithmetic.

Component simulation acceptance is recorded below only after the frozen worker
has completed. No controller acceptance or performance claim is made by the
source's existence alone.

The initial `resident_pv_lane_20261108_01` run rejected case 0 before accepting
its first arithmetic beat. A diagnostic successor `_02` preserved the same
stimulus and showed `words=1 word=0 tail=1 computed=1 presented=f`. The function
read configuration through implicit module variables; the continuous call with
unchanged word index did not update its output when configuration changed.
All word-mask dependencies are now explicit function arguments. This is a
new prototype defect, not a previously existing main-RTL failure. Both failed
receipts and their frozen sources remain intact; they are not relabeled PASS.

### Accepted component result

`resident_pv_lane_20261108_03/report.json` is PASS. The frozen baseline FPNew
slice ran with pipeline depths 3 and 5. Each configuration executed the same
899 cases, including the 12 real-model cases above:

| Case category | Unique cases per configuration |
| --- | ---: |
| Normal arithmetic, including IEEE boundaries and real operands | 863 |
| Invalid command admission | 18 |
| Malformed private packets with safe drain | 10 |
| Reset interruption/recovery scenarios | 5 |
| Parent cancellation before commit | 3 |

Each configuration accepted 85533 SIMD FMA beats, returned 85532 and deliberately
cancelled one through reset. There were 4465 acknowledged result words. This
accounting includes failure/recovery tests; the normal cases account for 85384
FMA beats. The 899 cases run twice are 1798 executions, not 1798 unique cases.

The testbench checks every issued operand, slot/mask/rounding mode, FPU result,
flag, final write and completion. Deterministic randomized backpressure covers
ingress, FPU admission, FPU return and final commit. Actual FPNew results are
buffered and deliberately reordered by the test harness to test tagged return
ownership; the controller has no fixed-latency assumption. Required counters
confirm simultaneous issue/return, reset with work pending, abort with work
pending and malformed packets with work pending. These are scenario-hit
counters, not a claim of complete code/functional coverage.

All frozen source and artifact hashes passed. The parent independently repeated
the log/count checks and pin audit. Component simulation took seconds; the
random stalls and reordered-response adapter make its cycle totals unsuitable
as a model-performance measurement. No additional long SoC simulation was
needed for this component gate.

To reproduce into a new directory (replace `NEW_OUTPUT` with an unused path):

```sh
python3 -B verification/performance/resident_rvv/pv_unit/run.py NEW_OUTPUT \
  --module-ready --latencies 3 5 \
  --real-json /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_real_operands_20261108_01.json
```

The runner freezes baseline dependencies, the controller, checker, oracle and
corpus; it refuses overwrites and retains first-failure evidence. The default
without `--module-ready` prepares inputs but does not start VCS.

## Remaining integration gates

- Global FPU acquisition/drain and result/flag ownership.
- Independent coefficient/seed source geometry, native EW16 packing and
  central coefficient collection using existing interfaces.
- Private context-bank delivery and per-lane credit/acceptance.
- Global all-lane commit authorization and irreversible-write fault boundary.
- Generated ISA/capability contract, FP legality, register reservations and
  ordinary RVV/QBS regressions.
- Same real-model complete-call comparison, then D64/D96/head/tail tests;
  QK and llama.cpp integration only after those gates justify proceeding.

A component PASS cannot close any of these gates. The cost budget and proposed
vector preparation are in `../cycle_analysis/DESIGN.md`.
