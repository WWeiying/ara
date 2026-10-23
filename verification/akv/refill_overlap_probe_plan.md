# AKV Blocking REFILL / Older RVV Overlap Probe

Status: baseline probe completed, 2026-10-23. The initial plan below is retained
as design context; its proposed serial-control interpretation is superseded by
the measured evidence in this section. No overlap RTL has been implemented.
Paths are relative to `/home/wangwy/openproject/ara_dsa_signoff_integration`.

## Measured Baseline And Corrected Control Interpretation

Worker `verification/out/akv-refill-overlap-probe-20261023-01` completed PASS
with exact arithmetic, sticky fflags, replay bytes, canaries and protocol checks.
The 54 AKV commands include two FULL, two REFILL, 48 row loads and two RELEASE.
The reader accepted 74368 payload bytes; all source/image/checker pins agree.
`audit_refill_overlap_probe.py` rechecks logs and both trace streams before
archiving the result, rather than trusting the worker's PASS marker alone.

| Mode | REFILL first presented | Last older FMA done | REFILL backend allocation | Joint cycles |
| --- | ---: | ---: | ---: | ---: |
| Immediate | 121420 | 121498 | 121500 | 756 |
| Nominal serial | 353053 | 353100 | 353102 | 756 |

`arch_start` records first presentation, not request acceptance or an AXI read.
The LMUL-decrease control puts the dispatcher in WAIT_IDLE. It blocks subsequent
backend issue, but the frontend can already present the REFILL. Thus the second
row is not a fully drained presentation control: it still has 47 cycles of older
arithmetic. The immediate row proves a 78-cycle opportunity, not achieved
overlap or a speedup. One older FMA allocates after REFILL presentation, so a
future admission test must include pending requests as well as allocated VIDs.

The first candidate should admit a REFILL while only known-safe, independent
arithmetic remains. Keep normal VLSU drain, exclusive QBS/AKV ownership and no
live context replay. Complete and release the fill VID normally, latch its
success/fault response, then expose that response only after older arithmetic
finishes. Waiting for global idle while retaining the fill's own live VID would
deadlock. Verify all lanes/PEs, sticky fflags, pending-request age, VID reuse,
fault/reset recovery and completion-before/after/same-cycle cases. The success
criterion is earlier payload acceptance and lower joint completion latency on
real Attention, not merely earlier presentation in this synthetic probe.

## Decision To Make

Measure whether a blocking AKV-v2 REFILL reaches the dispatcher while older,
independent ordinary RVV arithmetic is still executing, and how much useful
work remains then. First establish this on the existing SoC image. A later,
separately authorized RTL candidate could relax the older-arithmetic admission
barrier while retaining blocking fill completion and all memory ownership rules.
An unchanged image cannot demonstrate that candidate's speedup.

This experiment does NOT add asynchronous fill, overlap fill with live context
replay, retire token banks early, change softmax order, or add SRAM. Panel4 and
online softmax already exist. The synthetic arithmetic below isolates admission;
it is not a real-attention performance claim.

## Reusable Paths And Existing Image

| Purpose | Existing source, read only |
| --- | --- |
| Full SoC QBS/AKV/RVV handoff and literal instruction encodings | `apps/qbs_akv_handoff_smoke/main.c` |
| Descriptor initialization, row checks, trap tests | `apps/akv_context_smoke/main.c` |
| Production v2 FULL/REFILL/RELEASE opcodes | `software/akv/src/akv_v2_native_riscv.c:148` |
| Existing panel4 arithmetic scheduling | `software/akv/src/akv_v2_attention_rvv.S:232` |
| Bare-metal startup, linker template, output | `apps/common/{crt0.S,arch.link.ld,printf.c,string.c,serial.c,util.c,print_trap_cause.c}` |
| Private GNU objects and libc recursion guard pattern | `apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py` |
| Existing-image launch, pinning and generic result checker | `verification/uvm/run_real_dut_case.sh` |
| Image manifest verification | `verification/ara_verify/vcs_source_manifest.py` |
| Integrated request/backend/AXI checks | `verification/ara_verify/uvm_dut.py` |
| Bounded UCLI FSDB example, NOT a runner for this case | `verification/coverage/probe_gap76_red16.py` |
| Cycle extraction | `hardware/scripts/fsdb_trace/extract_cycles.py` |

Concrete reusable image found during inspection:

```text
verification/out/qbs-context-projection-soc-20261023-01/build/sim/simv
```

Its adjacent `simulator.conf` records `nr_lanes=4`, `vlen=1024`,
`qbs_enabled=1`, `akv_enabled=1`, `akv_v2_enabled=1`, `sim_l2_mb=16`,
`verify_axi_delay=0`. Raw `akv=0` is not evidence of disabled AKV here:
`akv_v2=1` enables the effective implementation. The executable and source
manifest exist. Observed SHA-256 values:

```text
simv:
adef2cd6fa24673e84cdd35d873176683d752244bc0949258553d64e6bda6ce8
simulator.conf:
3b41214b0d0cb173f004475dd4d58334d6415d5317520c126d8be941231d3c75
vcs_source_manifest.json:
83506dea7d62fc5e04d8802ec81f51c22dcd858d9e3597ccb7f02d44a5af00b6
```

These three hashes are NOT a complete runnable-image seal. Before running,
also pin every `simv.daidir/**/*.so`, ELF, launch script, configuration and
checker. Check the source manifest, including the dispatcher and AKV paths;
do not rewrite an old manifest to pass validation. If sources have drifted,
retain the image as explicitly historical baseline evidence or stop for the
parent's decision. Do not claim current-source equivalence from its filename.
Do not write inside its build directory or a live worker's output directory.

Do not invoke `run_current_handoff.py`: it builds RTL. Do not invoke the existing
handoff shell wrapper for this new probe: it rebuilds shared app outputs and its
checker expects an unrelated fixed command sequence. Borrow its checks only.

## Minimal Workload

One query row, D128, FP16 storage, KV length 72. Q/K/V row strides are 256
bytes; descriptor and arrays are 64-byte aligned and entirely in cacheable,
idempotent L2. Use distinct deterministic bytes per stream/token/dimension.
Keep Q/K/V immutable until RELEASE. FULL at tile_start=0 loads 64 tokens;
REFILL at tile_start=64 loads eight tokens, exactly 4096 K/V payload bytes.
Query data must remain intact. This is a bounded tail refill, not a full-tile
bandwidth benchmark. Payload allocation is 37120 bytes plus descriptor/output.

For each of the two modes below: fresh FULL, replay/check selected old Q/K/V
rows, drain the replay and setup operations, run the timed probe, then verify
all eight new K/V rows and Q0. RELEASE outside timing. Use identical data,
instruction arithmetic count, memory placement and binary layout where possible.
Optionally add a 128-token/full-64-token refill only after the first probe is
discriminating; do not start a matrix of workloads.

### Concrete Assembly Skeleton

The following is a proposed standalone `.S` function, not installed or compiled.
Arguments: a0=64, a1=aligned 128-FP32 output, a2=three uint64 timestamps.
All scratch registers are caller-saved. `SERIAL_CONTROL` is an assembly-time
variant, not a runtime branch in the measured interval. A successor benchmark
must verify returned VL=128 and encode checks against `akv_abi.h` before timing.

```asm
    .text
    .option push
    .option norvc
    .globl akv_refill_overlap_probe
akv_refill_overlap_probe:
    li       t0, 128
    vsetvli  t6, t0, e32, m4, ta, ma
    vmv.v.i  v8, 0               # accumulator v8..v11
    li       t3, 0x3f800000
    vmv.v.x  v16, t3             # source 1.0, v16..v19
    vmv.v.x  v20, t3             # source 1.0, v20..v23
    # LMUL decrease drains setup; restore before timing.
    vsetvli  zero, t0, e16, m1, ta, ma
    vsetvli  zero, t0, e32, m4, ta, ma
    li       t3, 8
    csrw     fflags, t3          # preexisting DZ must survive exact FMAs
    rdcycle  t1
    .rept 16
    vfmacc.vv v8, v16, v20       # every element becomes exactly 16.0
    .endr
    .ifdef SERIAL_CONTROL
    vsetvli  zero, t0, e16, m1, ta, ma
    .endif
probe_refill:
    .word    0x02a0605b          # AKV-v2 REFILL: rs1=x0, rs2=a0, rd=x0
    rdcycle  t2                  # blocking command has returned
    vsetvli  zero, t0, e8, m1, ta, ma
    rdcycle  t5                  # both paths now have arithmetic drained
    vsetvli  zero, t0, e32, m4, ta, ma
    vse32.v  v8, (a1)
    fence    rw, rw
    sd       t1, 0(a2)
    sd       t2, 8(a2)
    sd       t5, 16(a2)
    ret
    .option pop
```

Use the common startup to enable FP/vector state and accelerator consistency;
confirm `acc_cons_en` in the trace. No function call, printf, fence, store,
vector CSR operation, or vsetvl between the final FMA and the immediate REFILL.
Only the serial control intentionally inserts a drain. The relevant dispatcher
rule is specifically an integer-LMUL decrease (`ara_dispatcher.sv:1747`), not
the broader and incorrect claim that every vtype change drains all work.

Check every FP32 result equals bits `0x41800000`, fflags equals 8, trap count
is zero, and all replay bytes match source data. Check result stores have
completed before consuming output. Read fflags outside timing. Record the ELF
symbol addresses and disassembly of `probe_refill` and the 16 FMAs. The common
helper's C inline asm must not be inserted here: use one explicit assembly
sequence to control instruction adjacency and register lifetimes.

## Baseline Timing And Falsifiable Hypothesis

Define all cycle events from ONE sampled clock/epoch, not by mixing rdcycle,
UVM counters and FSDB time without calibration:

- `t_present`: first cycle REFILL is presented (`req_valid`, correct insn),
  even if `req_ready=0`. A request handshake alone loses the blocked interval.
- `t_math_done`: final backend completion of the older FMA VIDs, joined by
  allocation/order rather than numeric VID alone; VIDs can be reused.
- `t_accept`: `akv_command_fire` for that REFILL.
- `t_ar`: first accepted AKV payload AR after `t_accept`.
- `t_terminal`: REFILL success/fault terminal and corresponding scalar response.

For the immediate baseline, the hypothesis is `t_present < t_math_done`, then
no AKV acceptance while `ara_idle_i=0`, and `t_accept >= t_math_done` followed
by `t_ar >= t_accept`. Equality can depend on registered completion sampling;
check the actual idle and handshake predicates rather than assuming a fixed
one-cycle lag. No refill AXI transfer may precede acceptance. The control's
explicit LMUL drain moves the wait before REFILL presentation.

`AKV_PERF.busy_cycles` starts after command admission (`akv_engine.sv:905`);
it excludes dispatcher WAIT_IDLE. Equal busy_cycles between modes do NOT prove
equal end-to-end latency or no admission barrier. Report both software
`t2-t1`/`t5-t1` and the hardware events, with constant marker/control overhead
identified. Do not call the immediate/control difference an RTL speedup.

Before implementing an overlap candidate, estimate the available arithmetic
window `max(0, t_math_done-t_present)`. If this is zero, this workload offers no
older-arithmetic overlap; first determine whether setup/drain markers or issue
backpressure consumed the window. Do not repeatedly enlarge the instruction
chain without that diagnosis. Even perfect hiding cannot save more than the
remaining arithmetic window or refill service time, whichever is smaller.

For a future authorized candidate, decisive evidence requires `t_accept` and
accepted memory activity before `t_math_done`, identical outputs/bytes/fault
semantics, and lower combined completion time beyond measurement overhead.
Earlier command acceptance with no earlier memory service, zero useful overlap,
or unchanged/worse combined completion means no demonstrated benefit. This
probe says nothing about fill concurrent with context replay or younger RVV
issue: fill remains blocking, so only older arithmetic can overlap.

## Probe Hierarchy And Existing Trace Routes

Root `A = ara_tb.dut.i_ara_soc.i_system.i_ara`; `V = A.i_vlsu`;
`E = V.i_akv_engine`. These are source-confirmed paths, not `tb.i_ara_soc` from
the separate legacy `ara_tb_vcs.sv` top.

| Scope | Required observations |
| --- | --- |
| `ara_tb` | `clk`, `rst_n`; time-to-cycle calibration |
| `A.i_dispatcher` | `state_q`, `ara_idle_i`, `acc_req_i.req_valid/insn/trans_id`, `acc_resp_o.req_ready/resp_valid/exception`, `ara_req_valid_o`, `lsu_ex_state_q` |
| `A.i_sequencer` | `state_q`, `pe_req_o.id/op`, `pe_req_valid_o`, `pe_vinsn_running_q`, `addrgen_ack_i`, `addrgen_exception_i` |
| `V` | `normal_vlsu_idle`, `akv_command_valid/ready/fire`, `akv_command_id_q`, `akv_active_q`, `qbs_active_q`, `akv_terminal`, `akv_command_early_acked_q`, `normal_pe_req_valid` |
| `V` | `akv_axi_ar_valid/ready`, `akv_axi_ar`, `akv_axi_r_valid/ready`, `akv_axi_r`, `akv_mmu_req`, `akv_mmu_vaddr`, external `axi_req_o/axi_resp_i` |
| `E` | `state_q`, `context_ready_q`, `fill_tile_start_q/count_q`, `read_range_fire`, `read_completion_fire`, `payload_complete`, `read_fault_valid`, `context_write_busy` |
| `A.gen_lanes[0..3].i_lane` | `mfpu_vinsn_done`, `mfpu_result_req/id/gnt`; use completion, not just operand-valid, to establish the arithmetic lifetime |
| `E.i_v2_context` | `write_valid_i`, `row_read_i`, `column_active_q`, `column_capture_valid_q`, `conflict_o`; no concurrent replay is expected in this first step |

Confirm every required signal exists in this image before running a timed
wave extraction; do not quietly omit optimized-out signals. Source paths may
have changed after the image was sealed. `hardware/tb/ara_tb.sv:1025` also gives
the lane operand-fire probe, but operand fire is not instruction completion.

The existing compiled commit monitor supports `+COMMIT_TRACE=<path>` and
`+VECTOR_TRACE=<path>` (`hardware/tb/ara_commit_monitor.sv:71`). Commit events
include `arch_start`, `uop_alloc`, `uop_done`; vector events include `alloc`,
`done`, and VRF writes. `arch_start` records first presentation, not acceptance.
`+AKV_PERF +AKV_SUMMARY` give per-command traffic/completion checks but do not
replace the handshake trace. Request/backend/AXI protocol checking comes from
the integrated UVM/contract monitors, not `akv_engine_tb` alone.

For the first baseline, collect text traces with `+NO_FSDB`. If signal timing
needs disambiguation, perform one separately authorized bounded UCLI rerun,
using the measured marker interval plus a small margin. The existing example
`verification/coverage/probe_gap76_red16.py:26` demonstrates:

```tcl
run <measured-window-start>
dump -file refill_overlap.fsdb -type FSDB
dump -add {ara_tb.clk}
dump -add {ara_tb.rst_n}
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher} -depth 1 -aggregates
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer} -depth 1 -aggregates
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu} -depth 1 -aggregates
dump -add {ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine} -depth 1 -aggregates
# Add the four lane-level scopes above; avoid dumping context SRAM arrays.
run <bounded-window-duration>
dump -close
quit
```

This is a template, not executable with placeholders. UCLI dump availability
depends on image debug access; configuration does not prove that availability.
Do not silently rebuild if unavailable. Use existing text evidence and report
the missing observability. A wave run that quits before program completion is
diagnostic only, never a functional PASS. Do not copy the old example's coverage
arguments or run it against its historical workload.

## Legality, Fault And Ownership Checks

1. Require effective AKV-v2 capability, legal D128 descriptor and strides,
   `vstart=0`, FP/vector enabled, and accelerator consistency enabled. No D256
   logical mapping, masks, indexed memory or scalar dependency in the probe.
2. Verify REFILL receives rs1=x0, rs2=64, rd=x0 and exactly one command fire;
   held frontend/PE requests must not cause a duplicate fill.
3. At ownership transfer require `normal_vlsu_idle`, no QBS owner and no prior
   replay activity. Keep MMU/AXI response ownership exclusive until terminal.
   During fill, no normal vector memory request may be admitted.
4. On success require exactly eight K and eight V row ranges, 4096 payload
   bytes, no Q refill bytes, no replay conflict, and context publication only
   after all ranges and SRAM writes complete. Do not equate payload bytes to
   bus beats without checking alignment/burst formation.
5. After success, read/check Q0 and all new K/V rows, then perform an ordinary
   RVV load/add/store canary. This catches stale ownership and completion state.
6. Fault follow-up (separate ELF/run): use a valid initial tile with K base
   `L2_end - 64*256`, so REFILL token64 targets exactly `L2_end`; leave V valid.
   First verify the image's PMA/decode rejects that address and the setup does
   not overlap ELF/stack. This produces a deterministic boundary fault only
   when that platform check holds. It is NOT automatically an MMU-fault test.
   A valid FULL succeeds first; REFILL must fault, keep arithmetic outputs and
   fflags correct, expose no partial resident context, and allow a fresh valid
   FULL followed by replay and normal RVV. Use a trap handler saving/restoring
   every touched GPR, accepting only the exact REFILL PC/cause/tval, advancing
   mepc by four; unexpected traps terminate failure. Do not blindly reuse the
   smoke test's scratch-clobbering handler in an arbitrary C ABI context.
7. For a later overlap RTL change, older arithmetic must finish before a precise
   REFILL exception is architecturally exposed; younger instructions must not
   escape. Keep existing dispatcher exception-drain and sequencer WAIT paths.
   Reset during refill must cancel/invalidate ownership and hidden metadata;
   a post-reset fresh FULL must work. Existing `run_real_dut_case.sh` has reset
   routes, but they need their own expected-reset checker and are not normal PASS.

## Private GNU Build And Minimal Execution Steps

No commands in this section were executed for this task. A successor benchmark
source is still required; this document intentionally avoids adding a second
owned artifact or modifying app registration.

1. Parent approves a successor benchmark C harness and the assembly above in a
   new private source directory. Reuse existing descriptor definitions/startup,
   not the full attention kernel. Build only private objects, never `apps/bin`
   or the common generated `link.ld`. Use the approved compiler:
   `/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc`.
2. Copy/substitute the linker template into that build directory: ALIGNMENT=16,
   LENGTH=0x01000000 for this 16-MiB image. Compile the new C/S plus common
   `crt0.S`, `printf.c`, `string.c`, `serial.c`, `util.c`, `print_trap_cause.c`.
   Flags: `-march=rv64gcv -mabi=lp64d -mcmodel=medany -mno-relax -O2
   -std=gnu11 -fno-fast-math -ffp-contract=off -fno-tree-vectorize
   -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns
   -ffunction-sections -fdata-sections -DNR_LANES=4 -DVLEN=1024
   -I<root>/apps/common -I<root>/apps/include`.
   Link `-static -nostartfiles -nostdlib -Wl,--gc-sections -T<private.link.ld>
   -Wl,-Map=<private.map> <private.objects> -lm -lgcc`.
   No AKV runtime or reference oracle is necessary for this instruction probe.
3. Disassemble to verify instruction encodings, no hidden call/drain in the
   adjacency window, and no self-recursive memcpy/memset. Preserve compiler
   version/commands, ELF hash, alloc sections and stack headroom (at least 64 KiB).
   Do not use ZCC or a QEMU result as a VCS timing baseline.
4. Pin image/runtime libraries/config/manifest, benchmark ELF/sources and checker
   before launch. Parent owns a fresh output directory and systemd service whose
   foreground process is the bounded worker. Do not poll a long simulation or
   launch detached children from a short-lived service. Preserve first failure.
5. Launch existing simv, from the NEW output/work directory, using the following
   argument shape, after substituting absolute paths:

   ```sh
   timeout --foreground 900 "$SIMV" -no_save -l "$WORK/run.vcs.log" \
     "+PRELOAD=$ELF" +TESTCASE=akv_refill_overlap_probe +NO_FSDB \
     +AKV_PERF +AKV_SUMMARY \
     "+COMMIT_TRACE=$WORK/commit_trace.csv" \
     "+VECTOR_TRACE=$WORK/vector_trace.csv" \
     +ARA_CONTRACT_TRACE_LIMIT=100000 +ARA_UVM_TRACE_LIMIT=100000
   ```

   `run_real_dut_case.sh` supplies the reuse/pinning/checking pattern but does
   not expose these extra trace/perf arguments. Use a successor private worker;
   do not patch the sealed runner. Its existing `ara_verify.uvm_dut` checker
   can be invoked read-only with `--require-events --require-backend
   --require-axi --require-axi-write --vector-trace ... --log ... --simv ...
   --elf ... --output ...`; additionally require this probe's exact data and
   timing records. Generic protocol PASS alone is insufficient.
6. Require simulator exit zero, `Core Test *** SUCCESS`, no Error/Fatal/UVM error,
   no timeout or truncated traces, exact app result PASS, expected command
   geometry/count and immutable pre/post pins. Analyze the immediate baseline
   before any expanded campaign; add the serial control and one fault follow-up
   only as bounded independent runs. Do not reuse performance from an old image
   as proof that future overlap RTL is correct or faster.

## First Implementation Gate

Proceed toward the selective blocking-refill admission change only if the
baseline demonstrates remaining independent arithmetic at REFILL presentation.
The proof must separate dispatcher waiting from queue slots, memory handoff,
SRAM access and scalar frontend stalls. If the useful window is negligible,
do not add a staging bank to fix a different bottleneck. Retain ordinary RVV
and the existing serialized fallback. No throughput or model-level improvement
is promised by this plan.
