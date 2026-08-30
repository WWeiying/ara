# Attention/KV Streaming Milestone 3 Results

## Scope

Milestone 3 implements the version-1 AKV contract in synthesizable RTL and a
fixed-register D=128/GQA6 kernel using real Qwen2.5-1.5B Q4_K_M Decode Attention
data. This document records the implemented boundary, the measured optimization
decision, and the tests that must be reproducible before the milestone commit.
KV=128/256 scaling, exhaustive fault injection, and physical cost belong to
milestone 4 and are deliberately not claimed here.

## Implemented mechanism

- `akvfill.full` reads a 64-byte descriptor, up to eight F16 Q rows, and the
  first eight-token K/V tile through the existing translated VLSU read path.
- `akvfill.refill` preserves descriptor and Q state while atomically replacing
  the K/V tile. A failed full or refill leaves no valid hidden context.
- The hidden payload is a 6,144-byte, 32-bank by 192-row byte array. Its current
  RTL form is a banked register array; SRAM mapping and timing are not assumed.
- `akvload.v` validates context, selector, D, destination alignment, and register
  span before issuing any write. It replays 128 or 256 bytes through the normal
  LDU result ports, preserving Ara's VRF hazards, byte enables, and completion.
- A valid local load acknowledges the scalar request at command acceptance but
  retains its vector PE entry until all replay words complete. Invalid loads,
  fills, refills, and release acknowledge only at their terminal outcome.
- Normal VLSU, QBS, and AKV use mutually exclusive MMU, AXI-read, and LDU-result
  ownership. AKV never drives an AXI write channel or a private VRF port.
- AKV adds no dot-product, reduction, exponential, or FMA array. All arithmetic
  remains ordinary RVV lane/MFPU work.

The real kernel processes one KV head and six associated query heads at a time.
For each token it loads K once, replays six Q rows to form six packed scores,
loads V once, and updates six resident F16 output vectors. Packed FP32 maximum
and sum state stay in the VRF across the complete active prefix.

## Measured implementation decision

The first fixed-register kernel was functionally correct but used twelve
`vrgather.vi` scalar splats per online update. A bounded cycle trace showed that
each gather transition occupied 776--779 cycles in Ara's MaskU path. The 360
gathers at KV=16 caused 255,986 `mask_block_cycles`, accounting for 80.47% of
the function retire span. This falsified the assumption that a vector-domain
broadcast was cheaper than a scalar operand on this microarchitecture.

The corrected kernel keeps score, maximum, sum, and exponential evaluation in
vector registers, but extracts the two update factors for each query row and
uses `vfmul.vf`/`vfmacc.vf`. These extracts are data operands, not scalar control
decisions, and they do not spill online state to memory.

| Metric, real KV=16 | Gather version | Scalar-factor version |
|---|---:|---:|
| operator cycles | 321,815 | 50,873 |
| online/pack phase cycles | 315,723 | 46,287 |
| request-blocked cycles | 259,522 | 9,801 |
| queue-full cycles | 282,100 | 2,674 |
| queue-resource-block cycles | 256,973 | 771 |
| mask-block cycles | 255,986 | 0 |
| scalar-result-wait cycles | 0 | 1,440 |

The standard RVV implementation takes 137,961 cycles on the same real input.
The corrected AKV kernel therefore provides 2.712x speedup and reduces cycles
by 63.13% at KV=16. Relative to the rejected gather implementation it is 6.326x
faster. The added scalar-result waits are visible and are not hidden in the
report, but they are no longer the first-order limiter.

## Traffic and command accounting

The passing KV=16 run executes two KV-head contexts and reports:

| Counter | Value |
|---|---:|
| full / refill / local load / release commands | 2 / 2 / 256 / 2 |
| Q external bytes | 3,072 |
| K/V external bytes | 16,384 |
| local replay bytes | 65,536 |
| local replay backpressure cycles | 2,048 |

External Q+K/V traffic is 19,456 bytes, matching the residency lower bound in
the baseline study. The corresponding generic loop moves 245,760 targeted
logical bytes, so this mechanism removes 12.63x of that targeted external
traffic. Local replay bytes are reported separately and are not presented as
external-memory savings.

## Reproducible checks

Generate and verify the shared ABI:

```bash
python3 scripts/gen_akv_abi.py --check
python3 tests/test_akv_contract.py
```

Compile the enabled RTL and run the focused context test:

```bash
make -C apps akv_context_smoke
make -C hardware compile qbs=1 akv=1 sim_l2_mb=16 \
  buildpath=$PWD/hardware/build_akv_m3_audit \
  sim_dir=sim_akv_m3_audit
hardware/sim_akv_m3_audit/simv -l run_akv_smoke_final.vcs.log \
  +NO_FSDB +AKV_PERF +PRELOAD=$PWD/apps/bin/akv_context_smoke \
  +TESTCASE=akv_context_smoke
```

The test covers D128 full/refill/tail replay, D64 replay, invalid selector,
odd D128 destination, release, empty-context access, no partial destination
write on illegal loads, and recovery after a fault. It prints both
`AKV context smoke: PASS` and `Core Test *** SUCCESS ***`.

Representative coexistence checks on the same AKV-enabled image pass for
ordinary `vvaddint32` and the rebuilt `qbs_control_smoke`. With `akv=0`, the AKV
smoke reports `SKIP (extension disabled)` through an illegal-instruction probe,
while the same QBS smoke passes with identical per-command QBS counters.

The real operator command is:

```bash
LLAMA_ATTN_SIM_DIR=$PWD/hardware/sim_akv_m3_audit \
LLAMA_ATTN_RUN_ROOT=$PWD/hardware/llama_attention_runs_akv_m3_fixedscalar \
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh \
  akv 16 --ara-only
```

## Remaining milestone-4 work

- Run KV=128 and KV=256 in independent background directories and confirm that
  speedup and traffic scaling persist.
- Add descriptor/Q/K/V page-fault, PMA, AXI-error, reserved-field, overflow, and
  release-order tests beyond the focused functional smoke.
- Run broader ordinary RVV and QBS regressions with AKV enabled and disabled.
- Synthesize the banked context, quantify area and 1 GHz timing, and decide
  whether its implementation must change to SRAM or a pipelined register bank.
- Compare against both the generic RVV loop and a portable multi-row tiled-RVV
  software baseline before attributing the full dataflow gain to hardware.
