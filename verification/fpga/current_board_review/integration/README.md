# Current-board Architectural Integration

Prepared sidecar only. No RTL edits, VCS compilation, Linux boot, Verilator
execution, ZCC, coverage collection, or commit. Parent authorizes the final
source freeze only after unit PASS and independent review. Do not reuse the
disposable `/tmp/current-board-integration-snapshot-preflight01` as acceptance
evidence: it predates the final patch freeze.

## Programs and Identity

`prepared/provenance.json` preserves original names, Linux ELF SHA256s,
reduced-source SHA256s, measured tuples, and source directories. Original
assembly, headers, oracle C and fixture tables are retained byte-for-byte under
each `original/`. `case.c` changes Linux entry, write, exit and TIOCOUTQ only.
Assembly register roles and instruction order are unchanged; compile-time
symbol renaming permits linking cases together. The original ELFs are not
bare-metal executables and are never passed to the SoC testbench.

`all.elf` contains exactly these six cases, with per-case begin/pass markers:

| Port | Original identity and exact selected semantics |
|---|---|
| `maskslide` | `rvv_permute_restart_e16_m1_ops16`, via measured single from `rvv_permute_single01`. `vslidedown.vi v24,v8,0,v0.t`, e16/m1, VL32/vstart16, all-on predicate, original seed0 xorshift input, old destination 91. Preserves prestart/tail and checks returned vstart plus guards. |
| `restart_compare` | `rvv_masks_scalar_restart_e64_m1`, `rvv_small_masks01`. Original seed0/op0, VL8/vstart4, all-on predicate, scalar -3, packed old destination 0x5b. Original scalar boundary injection and packed-mask oracle, including permitted tail alternatives, retained. |
| `reduction_fflags` | `rvv_fp_redspecial_e32_m1`, `rvv_small_redspecial01`. Scenario3, length index4 (VL16), mask mode3 (0x24), frm0, op0, sticky0. Alternating +/-infinity, +infinity seed, `vfredosum.vs`. Fixture index4905 at VLEN1024: result 0x7fc00000, fflags NV=16. Original selected fixture and all output sentinel bytes checked. |
| `m8widen` | `rvv_reduction_fpwide_e32_m8`, `rvv_small_fpwide01`. Original first trial seed0/op0/frm0/mask0/**VL0**, `vfwredosum.vs v24,v8,v16,v0.t`. Do not substitute the generic handoff's VL1 arithmetic case. All destination elements remain the original 64-bit value 0x5b; vstart/fflags remain zero. |
| `wholemove` | `rvv_whole_registers_detail`, `rvv_small_whole01`. seed0/op16/mode1/start1. Source and old destination loaded with `vl8re8`, then architectural e16/m2/VL7 and `vmv1r.v v24,v8`. Input byte i = (37*i+3)&255. First two destination bytes must stay 91; original wrong byte33 was40. Checks status, all1088 bytes and guards. |
| `slide1up_prestart` | Explicit directed supplement, **not** an original ELF. e16/m1 VL2/vstart1, src[i]=1000+i, old vd91, all-on predicate, scalar777, `vslide1up.vx v24,v8,t1,v0.t`. Expected first two elements `[91,1000]`, all remaining elements91. Source comment identifies this footprint. |

Two additional, separate ELFs stay **outside** `all.elf` and the five-priority
repair scope unless the parent separately accepts the gather repair. Their ordinary failures/timeouts do not cancel other selected
cases; their results still remain FAIL, never converted to PASS:

* `gather_original`: verified03's `rvv_small_gather_restart_e16_m1_ops0`, parent
  `rvv_permute_restart_e16_m1_ops0`. e16/m1 VL2/vstart1,
  `vrgather.vv v24,v8,v16,v0.t`, original xorshift data and indices. Its measured
  prestart error is expected91/actual61881. Preserve this identity separately.
* `gather_prestart`: handoff02 `rvv_repro_gather_restart`, CASE4,
  `vrgather.vx v24,v8,t3,v0.t`, scalar index0, src[i]=1000+i, old vd91,
  expected `[91,1000]`. The handoff marks this generic case `board_tested=false`;
  it is not the board-confirmed original above. Its unchanged generic assembly
  and C are retained. Compilation rejects CASE !=4, so no Linux mmap/mprotect
  cases are enabled by this adapter.

`extended.elf` and four corresponding single ELFs supplement the originals:

| Port | Additional architectural coverage |
|---|---|
| `slide_source_e32` | e32/m1 VL16; vstart0,7,8,9; all-on and0x24 masks. Unique src[i]=1000+37*i, old vd91, scalar777. Checks every element, including prestart/tail; the vstart8 result must source element7, not a restarted source origin. Eight checks. |
| `slide_source_e64` | e64/m1 VL8; vstart0,3,4,5 with the same unique data and two masks. Eight checks. |
| `m8widen_nonzero` | Reuses the original ordered/unordered m8 assembly helpers. VL33 and65 cross v8/v9/v10 boundaries. All-on and0x24 masks, seed2.0, src[i]=1+i%7; exact finite FP64 sum and flags0. A fifth trial per opcode activates only input1=+infinity and33=-infinity, requiring canonical FP64 qNaN0x7ff8000000000000 and NV16. All remaining destination words and guards retained. Ten checks, independent integer IEEE-bit oracle. |
| `wholemove_layout` | vmv2r: source both e64 -> current e8, and source v8=e8/v9=e64 -> current e16. vstart1 and vstart=whole-group EVL (no-op). An adjacent `vmv2r.v v16,v24` reads the destination before any CSR drain/vset. Checks all256 bytes of both results; old destination91, old dependent destination99. Four checks. |

These directed tests are not relabeled as original FPGA programs. A mismatch
in their new numerical/flags checks is an open integration failure, even if a
unit liveness-only test passes. No RTL repair or expectation weakening is done
by this sidecar.

## Oracles and Limits

Each original port retains its complete selected-case scalar/byte/fixture
oracle. Acceptance requires its exact `cases=1 errors=0` marker, the per-case
completion markers, valid commit trace, and the testbench's successful exit.
The reduction additionally requires `flags_seen=16`; wholemove requires
`skips=0`. An empty loop, SKIP, missing terminal marker, timeout, assertion,
unexpected trap, or source/image drift is not PASS.

The selected C oracles are **not** a certification of every original matrix
oracle. In particular, no generic unsigned-FP conversion arithmetic oracle is
used here: ordered reduction uses pinned SoftFloat bit/flag fixtures, and the
m8 original case is VL0 with no FP arithmetic result to infer. The original
`from_half` initializer is retained; its inputs are positive powers of two and
the original seed is1.0. Keep any separately identified original C-oracle
error open, with its exact input/result/flag tuple; never adjust an expected
value just to match RTL. Host tests independently check the selected qNaN/NV
fixture and wholemove byte boundaries. Spike success validates these ports'
self-oracles, not full original matrices or RTL/Spike trace equivalence.

The SoC's UART is0xc0000000 (`ara_soc.sv`, `ara_testharness.sv`, `mock_uart.sv`).
CTRL0xd0000000 takes the **raw** return code; `ctrl_registers.sv` adds the valid
bit. The Spike build instead buffers diagnostics in `replay_log` and writes
`(code<<1)|1` to HTIF `tohost`. It accesses neither SoC MMIO address. Spike must
pass the framework's nonzero-vstart capability probe first. It is a separately
linked runtime, not a same-ELF architectural differential comparison.
No case expects an illegal-instruction trap: traps record case/mcause/mepc/
mtval and fail with code127. No reduction restart restriction is invented.

## Software Preparation

Run from `/home/wangwy/openproject/ara_dsa_signoff_integration` with fresh output
names. The checked-in prepared sources do not require the external campaign
directory for compilation. `freeze` regenerates **software** sources only and
requires every archived input hash to match; it is unrelated to RTL freezing.

```sh
I=verification/fpga/current_board_review/integration
python3 -m unittest discover -s "$I" -p 'test_*.py' -v
python3 "$I/prepare.py" compile --prepared "$I/prepared" --out /tmp/board-software-final
python3 "$I/prepare.py" compile --prepared "$I/prepared" --out /tmp/board-spike-final --spike-reference
python3 "$I/reference.py" --programs /tmp/board-spike-final --out /tmp/board-reference-final
python3 "$I/smoke.py" --out /tmp/board-smoke-final
```

The smoke set is unmodified existing vadd, vslideup, vslidedown, vrgather,
vmseq, vfredosum, vfwredosum plus qbs_control_smoke, akv_context_smoke and
qbs_akv_handoff_smoke. It uses non-ZCC LLVM, the existing runtime/2MiB linker
script, private objects, copied software inputs and SHA256 pins. Custom smoke
requires the **enabled** PASS marker; extension-disabled SKIP is rejected.
These smoke ELFs are SoC-only and are not sent to standard Spike.

## Prepared Handoff

Final prepared outputs (no VCS execution):

| Artifact | Absolute path |
| --- | --- |
| SoC ports, 14 ELFs | `/tmp/current-board-integration-software-05` |
| Spike HTIF ports, 14 ELFs | `/tmp/current-board-integration-spike-04` |
| Spike reference, 14/14 PASS | `/tmp/current-board-integration-reference04/reference.json` |
| Normal/custom smoke, 10 ELFs | `/tmp/current-board-integration-smoke01` |

`SOURCE_SHA256SUMS` pins every integration source/prepared file;
`ARTIFACT_SHA256SUMS` pins these ELF files and their provenance/result ledgers.
Verify both with `sha256sum --check` from this integration directory before
consumption. Each `programs.json` additionally verifies ELF SHA256 at launch.
The commands below use fresh reproducible output names from the preparation
section; substitute the prepared SoC/smoke directories above to reuse them.
Host tests: 16 PASS. Spike validates port self-oracles only, not current RTL,
custom instructions, original Linux execution or full closure.

## Final Freeze and Launch

Do not run this section until the parent confirms all unit results/review and
authorizes freezing/building. The latest reference full-build command is
`verification/out/upstream-relocate-closure-20261009-02/compile_command.json`.
Its compile log reports149.509s compile +2.689s elaboration +4.081s link CPU;
budget roughly3-6min wall, longer under host/license contention. Its subsequent
run status is FAIL (missing frozen disassembly symbols), not signoff evidence.

The new command uses that image's four lanes/VLEN1024, QBS/AKV/AKV-v2, 2MiB L2,
AXI delays, assertions and no FSDB/coverage. It deliberately omits the old
SV39/trap diagnostic probes. `run.py` reuses `verify.py`'s `RegressionRunner`
build/run/checking paths; it does not change the shared framework.

```sh
R=/home/wangwy/openproject/ara_dsa_signoff_integration
I=$R/verification/fpga/current_board_review/integration
O=/home/wangwy/fpga_runs/current_board_integration_final01
# Only AFTER parent authorization; captures current sources at this point.
python3 "$I/run.py" snapshot --out "$O/frozen" --authorize-freeze
# Omit --authorize-build for a dry run in a separate fresh output directory.
systemd-run --user --unit=ara-board-integration-build01 --collect \
  --property=KillMode=control-group --property=RuntimeMaxSec=3600 \
  --property=StandardOutput=append:"$O/build-service.log" \
  --property=StandardError=append:"$O/build-service.log" \
  /usr/bin/python3 "$I/run.py" build-image --snapshot "$O/frozen" \
  --out "$O/image" --authorize-build
```

The service directly owns the Python worker and its EDA children. Confirm its
actual process/log progress once, then inspect `image/run.json`, `image/image.json`
and `_build/vcs-build.log` after completion; do not poll long runs. No Linux
boot is part of this workflow. No Verilator executable is invoked: Bender's
`script verilator` is the existing VCS filelist format, and `svdpi.h` is copied
as a header-only build input from the installed tool tree.

Snapshot details: capture the current Bender list, all listed RTL, recursive
include headers, DPI sources/headers, config/Makefile, and verification framework;
physically copy files and remove write permission, with no live RTL symlinks.
A read-only Bender adapter emits only that relocated fixed filelist. Rehash the
live set before/after copying and reject drift. Build outputs are outside this
tree. Preserve the whole frozen directory and `simv.daidir`; moving just simv
loses generated libraries and does not preserve its identity. The wrapper
checks source/config/ELF/launcher/shared-library hashes before and after replay.

After successful build, run six individual points first, then combined and the
extended checks, then
normal/custom smokes. Each command defaults to dry-run unless `--execute` is
present. Program execution defaults to `--jobs 4`, bounded to 1-8 workers;
the image build is unchanged. The shared cancellation event still stops queued
and running priority cases on the first failure. The shell gate below launches
combined only after all six singles PASS. Independent gather results may be collected separately regardless of
their expected open failure; do not label them repaired.

```sh
if python3 "$I/run.py" run --image "$O/image" --programs /tmp/board-software-final \
  --out "$O/singles" --jobs 4 --case maskslide --case restart_compare \
  --case reduction_fflags --case m8widen --case wholemove --case slide1up_prestart --execute
then
  python3 "$I/run.py" run --image "$O/image" --programs /tmp/board-software-final \
    --out "$O/combined" --case all --execute || exit 1
else
  exit 1
fi
python3 "$I/run.py" run --image "$O/image" --programs /tmp/board-software-final \
  --out "$O/extended" --case slide_source_e32 --case slide_source_e64 \
  --case m8widen_nonzero --case wholemove_layout --case extended --execute
python3 "$I/run.py" run --image "$O/image" --programs /tmp/board-software-final \
  --out "$O/gather-open" --case gather_original --case gather_prestart --execute
python3 "$I/run.py" run --image "$O/image" --programs /tmp/board-smoke-final \
  --out "$O/smokes" --jobs 4 --case rvv_vadd --case rvv_vslideup --case rvv_vslidedown \
  --case rvv_vrgather --case rvv_vmseq --case rvv_vfredosum --case rvv_vfwredosum \
  --case qbs_control_smoke --case akv_context_smoke --case qbs_akv_handoff_smoke --execute
```

Stop priority work on a new mismatch/stall. Preserve the first failing case,
last begin marker, private ELF/disassembly, trace and image/source identities.
The functional image intentionally has no FSDB. A cycle-level follow-up needs
separate parent authorization for a bounded-window, focused-profile image;
do not increase timeouts or rerun repeatedly without a discriminating hypothesis.

## Original-program Acceptance Remains Separate

1. Require the parent-owned MASKU/SLDU, lane sequencer, dispatcher and VMFPU
   unit evidence and independent review before the final freeze.
2. Pass the architectural ports and representative normal/custom regression
   on the exact sealed full image. This establishes only those architectural
   programs under the SoC simulation configuration.
3. Later, with separate board/Linux authorization, replay the **original
   unmodified ELF identities** recorded in provenance, not only reduced scenes.
   Record current bitstream/RTL/tool/config hashes, original ELF SHA256,
   fixture/source/oracle versions, complete output, exit status, completed
   case counts, vlen/privilege settings, board boot identity and raw fault data.
   Compare full parent/partition prefixes and original operation order; a single
   passing port does not close sequence-sensitive sparse/all-off slide failures.
4. Preserve archived failing-image evidence separately. Associate each result
   with its exact original name/SHA and measured failure tuple, not a family
   count. Distinguish flag-only, data/prefix, legality and completion results.
5. Linux protected-page, FOF, context-switch and actual fault/restart cases
   remain outside this bare-metal replay. Synthetic CSR vstart assignment is
   not Linux signal/MMU/fault recovery. Handoff02/verified03/compare01 source
   hash audits (parent reports62/62,795/795,326/326) establish source identity,
   not repair acceptance. Leave unexecuted/unmatched original cases open.
