# Current-RTL QBS Preparation

Build/check recipes only. Parent owns the current externally pinned SoC image,
single-worker execution, timeout, independent protocol checks and result pairing.
No RTL, production SDK, shared helper, simulator compilation or execution here.

## Interface

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/qbs -p 'test_*.py' -v
python3 -B verification/performance/operator_eval_20261115/qbs/prepare.py --list
python3 -B verification/performance/operator_eval_20261115/qbs/prepare.py \
  --case qwen3_attn_q_q4k_m1_n64_direct_native \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_qbs_prepare_20261115_q4_native_01
```

`manifest.json` matches the parent runner: `cases[]` has `id`, `category`, `elf`,
`elf_sha256`, `source_pins`, `checker`, `timeout_seconds`, `plusargs`.
The checker argv is `python3 -B check.py --build BUILD_DIR --log {log} --output {result}`.
`--build BUILD_DIR/build.json` also works. Success writes `{state: "PASS", metrics: ...}`;
failure writes a fresh FAIL receipt and exits nonzero. Existing output is never overwritten.
No old SoC schema is imposed. Parent may use `CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED`
or its activity successor independently of these firmware receipts.

## Sources And Scope

SDK/runtime/startup/reference and established x32 kernels come from `git archive`
of main workspace HEAD `dbe2b78817ef45b912444afcb85ad6e01a2be135`, not branch `main`.
llama comes from its recorded HEAD archive, with only the archived registered
`llama-decode-sums.patch`. There are no SDK overlays. No AKV source, dirty assembly,
dependency rebuild, old object or extra development worktree is used.

Q4_K: audited eight-distinct-row Qwen3 attention-Q and FFN-gate captures, full
K2048, first N64/128, first M1/4/8 rows. M1 is a prefill-row subset, NOT decode.
Q6_K: audited real position40 decode attention-V, M1/K2048/N64 or N128. Fresh
independent Q8, R4 repack and golden are checked against original capture artifacts.
Cropping outputs is labeled selection, not a newly captured full projection.
See `cases.json` for deterministic runnable shapes and nine-format coverage gaps.

`native`: real SDK query, exact encoding binding, planner/cursor and native execute.
`rvv_x32`: unchanged archived `repack_kernels.c` using format-specific 32-output
GEMV and Q4_K four-input GEMM. The archived field packer prepares x32 weights
offline. Current llama RVV quantization is shared by both sides; Q4 GEMM uses
SDK RVV M4 packing, independently byte-checked. Group-major Q4 outputs are mapped
to logical row-major only outside the timed ROI. This is the established optimized
standalone comparison, not current GGML end-to-end dispatch.
`rvv`: actual upstream single-output RVV dot diagnostic, explicitly
`baseline_kind=upstream_rvv_single_output_diagnostic`, `primary_eligible=false`.
Never silently substitute it for the primary x32 baseline or report its ratio as
the primary QBS speedup. Native/x32 receipts carry explicit baseline labels.

## Checks And Timing

Host oracle uses independent `qbs_ref` quantization, packing and ordered execution;
the actual SDK cursor proves every output coordinate occurs exactly once.
Native output bits and flags are exact. RVV differs in FP reduction/FMA order:
every finite output must satisfy `abs(error) <= 0.0002 + 0.0002*abs(reference)`.
That is a stated tolerance contract, not bit equality or a full model accuracy test.
Both trials reset flags before quantization, record quant fcsr, then set execution
flags to 0/8. Native checks newly generated flags then sticky DZ; RVV allows only
NX in addition to the seed. Q8 scales/quants/bsums, packed bytes, all outputs,
ten raw 64-byte guards, fcsr/vcsr/vstart and command work are host checked.

Two committed `csrr zero, cycle` markers per trial enable existing total-ROI
monitors, without adding a fence. Consecutive nonzero-destination `rdcycle`
boundaries measure quant, pack, query/planning/admission, execute, final drain.
Quant fcsr sampling is charged to pack; execution flag seeding is charged to
execute; final CSR samples are outside rdcycle but inside the commit-marker ROI.
No overhead subtraction or cache-residency claim. Snapshot/poison/check/UART work
is outside both ROIs. Cold weight repacking is excluded equally for R4 and x32.
Native SDK fencing/vsetvli/result stores remain unchanged. Only one final hardware
fence is added per trial. Software stamps are issue-side intervals, not stage
completion barriers; commit-marker monitor cycles are reported separately.

Engine phases must exclusively partition busy. Command geometry, issue capacity,
context lifecycle and bytes saved are checked against the independent host plan.
Physical lane utilization is not inferred from pair capacity. Reuse scopes are
DIRECT, per-operation FILL/RELEASE, and two-call FILL_KEEP/REUSE_RELEASE. Runtime
ineligibility retains DIRECT fallback, but flags/shape/execute errors fail closed.
Current full-K M4/M8 activation payloads exceed the unchanged context SRAM capacity.
Cross-call reuse cases use identical activation bytes and explicit exclusive token
ownership; they are not a cross-operator lifetime demonstration.

Raw `[PERF]`/`[LLM_METRIC]` console records are retained in checker output. Complete
two-frame PERF reports are paired in trial order, separately from rdcycle. Other
file-based LLM/activity metrics are retained and audited by the parent; missing
console monitor evidence is labeled unavailable, never invented.

## Remaining Work

Seven formats (Q2_K/Q3_K/Q5_K/Q4_0/Q5_0/Q8_0/IQ4_NL) are explicit nonrunnable gaps.
Historical format and seven-model fixtures exist, but are not requalified against
current SDK/full-K/capture/oracle contracts here. Requantization of Q4 bytes or
repetition of a Q6 decode row must be labeled derived, not real prefill coverage.
Q6 distinct M4/M8 captures, full output dimensions, backend/model execution,
cross-operator reuse and production selection remain future work.

Cooperation requires parent-pinned same-source on/off images with identical M8
ELF, real lane-loan evidence and comparison against M8 work scheduled as two M4
tiles. Do not compare only to the slower old M8 schedule. All-on alone is not an
ablation. This campaign is flat simulation RAM, not board NORMAL_MEMORY admission,
FPGA acceptance, full layer/model evaluation or completion of all seven groups.

After handoff, treat all pinned files, tests and documentation as sealed until
the parent consumer finishes. Use successors for later changes. Failed build
directories and original receipts remain untouched.
