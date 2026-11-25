# Compact QBS Reuse Evaluation

This is a new, independently pinned namespace. `qbs/`, old builds, production
RTL and SDK are read-only. `derivation.json` identifies the copied/derived source
revisions; no live helper from `qbs/` is imported.

## Build And Check

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/qbs_reuse -p 'test_*.py' -v
python3 -B verification/performance/operator_eval_20261115/qbs_reuse/prepare.py \
  --suite all \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_qbs_reuse_prepare_20261115_all_01
```

Default `--suite native` builds the six priority cases. `--suite rvv` builds only
three optional x32 comparisons; `--case ID` selects individual catalog cases.
All output must be new and use the authorized prefix. Preparation compiles and
tests host code and firmware only. It never builds or runs a simulator.

The resulting `manifest.json` conforms to the parent runner. Checker argv is
`python3 -B check.py --build BUILD_DIR --log {log} --output {result}`; it emits
`{state: "PASS", metrics: ...}` only after the compact workload gate passes.
The outer `source-pins.json` seals sources, tools, all gold/data/ELFs, input pins,
build receipts and the runner manifest. All files in it are frozen after handoff.

## Static Scope

The real source is Qwen3 attention-Q, eight distinct prefill activation rows,
K2048 and 128 captured weight channels. M4 selects the first four rows; both
M8/tile8 and M8/two-M4 use all eight rows and N64. Compare those two for equal
work. M4 alone has half as many outputs and is not an equal-work M8 baseline.
M1 selects one prefill row, not a decode capture, and N128 is an output slice.

Three M1/N128 modes run DIRECT, OPERATION (FILL/REUSE/REUSE/RELEASE each call),
or CROSS_CALL (FILL/REUSE/REUSE/REUSE, then REUSE/REUSE/REUSE/RELEASE).
Each ELF runs exactly two calls. Operation generation increments between calls;
cross-call generation remains one and the single worker owns the token.
Before repeat REUSE, full canonical input/weight bytes and live Q8/packed bytes
must match, and the first complete proof must have passed. Otherwise no second
call is issued. Cross-call repeat does not poison its validated activation
buffers. Quantization and packing are still repeated and charged on both calls.

SDK/runtime/startup/reference and established x32 kernels are extracted with
`git archive` at `dbe2b78817ef45b912444afcb85ad6e01a2be135`. llama is archived at
`a2b7f30da9aadf88b0a068c447383ed2e26ee867`, and the registered decode-sums patch
is reverse-checked as already present. There are zero SDK overlays and no dirty
AKV source inputs. No old objects, unchecked dependencies or worktrees are used.

## Proof And Timing

The independent host oracle quantizes all input rows, repacks weights and both
activation layouts, executes every command using ordered `qbs_ref`, and checks
the real SDK cursor covers every output exactly once. x32 packing is the
archived field packer, with an independent full-byte inverse audit. Matched
shape/schedule goldens are compared as complete byte arrays, not hashes.

Target validation uses the same host-mutation-tested `verify.h` for every case.
After each ROI it visits every output element, Q8 byte, packed byte, original
input byte, active weight byte, and all ten 64-byte guards. The volatile loops
do not stop at the first mismatch. Native outputs are bit-exact. The unchanged
Q4 x32 GEMV/32x4 GEMM kernels use finite-only tolerance
`abs(error) <= 0.0002 + 0.0002*abs(reference)` for their different FP/FMA order.
Q4 GEMM output is group-major and compared in logical row-major coordinates
outside the ROI, without an extra timed output-layout conversion.

Only counts, error counts, first output mismatch, phases, CSRs and work/caps are
printed. No tensor hashes replace numerical checks, and no full tensor UART
dumps are needed. The host checker trusts the reviewed, sealed target comparison
code/ELF and its fully sized proof; this is not an independent host readback of
all output bytes. The first failure is retained; comparisons are never relaxed.

Consecutive rdcycle stamps measure quant, pack, plan/admission, execute, drain.
Two `csrr zero, cycle` markers enable the parent's commit-ROI monitors. Only the
existing final fence is added. Quant CSR reads are charged to pack; pack CSR
reads and runtime query/cursor work to plan; flag seeding to execute. Final CSR
reads are outside rdcycle but inside the commit ROI. All full comparisons,
poison, identity checks and printing are outside both ROIs. Weight repack is
offline and excluded equally for R4 and x32. No overhead is subtracted.

Native execution uses the real SDK with a record-only executor callback. Its
header/pointer/shape record stores are included in execute timing; validation
of all recorded descriptors is outside the ROI. Actual callback count must
match the independent plan. RVV records real x32 kernel-call count. This is an
instrumented directed full SDK invocation, not unmodified whole-GGML latency.

CSR snapshots are before/after quant, after pack, and after drain. Before state
is zero. Real llama quantization leaves VXRM=1, hence VCSR=2 and VXSAT=0;
pack/execution must preserve it and VSTART=0. Native flags must equal fresh
independent oracle flags with seeds 0/8, proving generation of NX separately
from sticky DZ preservation. RVV permits only NX in addition to the seed.

Actual native capability queries provide raw INFO5 and the SDK cooperation bit.
No ELF assumes cooperation enabled. Hardware dot rate must match the observed
capability and actual command M; queue-depth effects are measured, not assumed.
The parent supplies/qualifies same-source on/off and queue variants. M1/N128
must actually be context eligible; a reuse-mode admission failure is not silently
reclassified as a successful DIRECT ablation. M4/M8 full-K payloads do not fit
the unchanged 4672-byte context SRAM. No board NORMAL_MEMORY claim is made.

The parent remains responsible for current-image/source identity, independent
protocol checking, passive resource metrics and completed-run results. No host
preflight or firmware build is a hardware PASS, FPGA acceptance, model result,
all-nine-format completion, or completion of the overall operator campaign.
