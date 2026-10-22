# Focused FP16 Comparison Flags

Bounded architectural ports, not full original Linux ELF replays. No RTL edits,
image builds, Verilator, ZCC, URG, or internal signal injection. Tesla owns VMFPU.
Only this `comparison/` directory is written by this task.

## Measured Scope

All five binaries pass Spike with `rv64gcv_zvfh_zvl1024b`; explicit Zvfh is
intentional. `reference01/reference.json` records the Spike binary, ISA, ELF
hashes, return codes, and nonzero-vstart capability probe. The unchanged runtime
buffers Spike diagnostics in RAM, so reference stdout is not a diagnostic dump.

Frozen VCS image:
`/home/wangwy/fpga_runs/current_board_integration_final01/campaign/image`.
The checked parent `integration/run.py run` validates the sealed sources, image,
compiled configuration, manifest, and software pins before execution and checks
sources/image again afterward. No moving live RTL is substituted.

| Case | Expected flags | VCS flags | Status |
| --- | ---: | ---: | --- |
| `active_snan`: only predicate bit5 on | 16 | 16 | PASS |
| `no_snan`: all off; both sNaN input occurrences quieted | 0 | 0 | PASS |
| `all_off`: exact selected board stimulus | 0 | 16 | FAIL, flags only |
| `tail_vl15`: archived unmasked vf, destination v0 | 0 | 16 | FAIL, flags only |
| `prestart_snan`: restart derivative, start6 | 0 | 16 | FAIL, flags only; localization caveat below |

All five cases have zero independent data errors, setup errors, and fixture
oracle disagreements. Each failing reconstructed fixture reports one error,
flags; the independent check reports that same mismatch again. Thus the final
`errors=2` is two checks of one defect, not two distinct defects.
Exactly five VCS executions were used, each 45-48 seconds, all on the same image.
No RTL repair or internal cycle-level simulation was attempted.

## Provenance and Adaptation

Source root is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_fp_compare_reconstructed01`.
`prepared/source_manifest.json` is copied verbatim; `prepared/provenance.json`
pins each source, original-case metadata, runtime and helper identities.
`prepared/*/original` retains unmodified C, assembly, headers, and fixture table.
The manifest explicitly says `oracle_provenance=current_reconstruction`, with
changed `fp_compare_oracle.c`/`fp_comparisons.py` and archived assembly. These
tests do **not** establish full original-program or historical vector-data
equivalence. The original reduced C oracle still runs alongside an independent
integer-only half-precision equality, NaN-classification, and active-window check.

- `all_off` uses `rvv_small_fp_compare_e16_mf4`: e16/mf4, seed0, VL8,
  mode3, sticky0, start0, op0 `vmfeq.vv v24,v8,v16,v0.t`. Assembly SHA256
  `17ee5822241dee2dd4bcbf24e9c5c27303bf728042c4771da0dc005c8338d0ab`.
  Original board ELF is `rvv_additions28/binaries/rvv_fp_compare_e16_mf4`,
  SHA256 `777190b9d2ea291329db61a01bee011ae389280d30c1437d9ad64901ad46d15f`.
  Historical record: `rvv_recovery08_07/resume/board_report_live07.json`,
  same name and detail expected0/actual16. The reduced Linux ELF is independently
  pinned as `96aaa86168ddcb6df8c5d931e6582975cc93ad42dc62c0fa8baeba2bba583345`.
- `active_snan` changes only mask byte0 from `00` to `20`. All original inputs,
  old vd, instruction setup and fixture lookups remain. This is a derivative.
- `no_snan` maps fixture index15 to14 for both inputs and oracle lookup,
  changing sNaN `7c55` to qNaN `7e55` at v16[5] and v8[15]. Predicate remains
  all off. This is a derivative, not a board-selected trial.
- `tail_vl15` uses the separate archived
  `rvv_small_fp_compare_unmasked_alias_v0_e16_mf4` source: op4
  `vmfeq.vf v0,v8,ft0`, VL15, seed0, mode0, sticky0, start0. Scalar is boxed
  +0 (`ffffffffffff0000`). v8[14] is qNaN, v8[15] is the only sNaN, in the
  tail. Destination old vd comes from the all-one mask, **not** output's `5b`.
  This is not the nonalias-v24 program cited in historical live10.
- `prestart_snan` retains archived
  `rvv_small_fp_compare_restart_e16_mf4` assembly and changes only selected
  start4 to start6. Its mode0 mask is all one; v16[5] sNaN is now prestart;
  active indices6/7 contain no NaN. This start6 case is a directed derivative,
  not the original board start4 data-error symptom (which expected NV16).
  It retains v8[15] sNaN in the tail, so it is **not a prefix-only localization**.
  Likewise the all-off fixture retains that tail sNaN. Architectural excess NV
  is unambiguous, but these traces alone cannot identify which inactive sNaN
  contributed. The dedicated VL15 case has only a tail sNaN. Static issue-count
  analysis predicted v16[5] as the contributor at VL8. The later bounded capture
  in [cycle_proof.md](cycle_proof.md) measures lane1 FP16 slot2 NV and exact
  all-off MASKU acceptance, confirming that contribution.

The selected reduced sources already contain one trial, so there is no large
outer loop or scalar filtering. `integration/prepare.py:adapt` changes only
Linux entry/I/O/exit; local instrumentation adds fixed-size logging, strict
capacity16, and independent checks. Startup, runtime and linker script are
copied unchanged from the pinned parent integration. Archived comparison
assembly is compiled unchanged. A separate post-return helper captures v8,
v16 and v0 after the target's flags were read and saved; it cannot contaminate
that measurement. No FP computation occurs in the integer-only oracle.

## Input and Data Checks

For the all-off/active-sNaN cases, in element order (hex):

```text
v8:  0000 8000 3c00 bc00 3800 4000 4200 1000 0001 03ff 0400 7bff 7c00 fc00 7e55 7c55
v16: 0000 bc00 4200 03ff 7c00 7c55 3c00 4000 0001 7bff 7e55 8000 3800 1000 0400 fc00
```

Logs retain every input, mask bytes, initial destination, output, guards, actual
flags, expected flags, vstart, and separate error counts. Setup checks compare
post-target v8/v16 readback with fixture-derived input memory; v0 readback with
the predicate (or result for the destination-v0 case); all128 mask bytes; and
all128 output bytes outside the two-byte result. Inactive body and prestart
bits must equal old vd. Tail mask bits use the original permitted alternatives
(old, one, or full-width comparison result), not forced exact tail equality.

## Instruction Identity

`soc/*.dis` records decoded instructions. `*_target.txt`, produced by
`collect.py`, binds target PC/opcode and neighboring setup/CSR/store instructions
to actual scalar commit trace lines. The built-in trace decoder prints `INVALID`
for vector opcodes it cannot disassemble; this is not an illegal-instruction trap.

All-off target: PC `80000902`, opcode `60881c57`; prior `fsflags a7` at
`800008fe` writes zero, subsequent `frflags t1` at `8000090a` returns `10`.
Only the target and `csrr vstart` occur between those flag accesses. VCS output
is retained as FAIL, not relabeled PASS because the failure was expected.

| Case | Target PC | Opcode | Immediate post-target flags read |
| --- | --- | --- | --- |
| active_snan | `80000920` | `60881c57` | `10` |
| no_snan | `80000954` | `60881c57` | `00` |
| all_off | `80000902` | `60881c57` | `10` |
| tail_vl15 | `80000986` | `62805057` | `10` |
| prestart_snan | `8000095e` | `60881c57` | `10` |

The prestart trace writes `vstart=6` at `8000095a`; the target returns vstart0
and flags16. The tail trace confirms actual scalar `ft0=ffffffffffff0000`.

`results.json` collects outcomes, source/image identities and the original board
record. `future_design.md` records the bounded ownership review, not a repair.
Architectural results do not replace internal cycle-level proof of where NV
was generated or misqualified. No claims cover other widths, LMULs, comparison
operators, sticky modes, or the separate unordered-reduction missing-NV family.

## Reproduction

From the integration worktree, build into a fresh copy of this directory:

```sh
python3 -B verification/fpga/current_board_review/comparison/prepare_build.py
python3 -B verification/fpga/current_board_review/comparison/reference.py --programs verification/fpga/current_board_review/comparison/spike --out verification/fpga/current_board_review/comparison/reference01
```

Use the parent checked runner with the existing image, `comparison/soc`, a
fresh output, `--jobs 1 --timeout 300 --execute`. Main ordering is
`--case active_snan --case no_snan --case all_off`; tail and prestart each use
their own invocation because the runner correctly cancels after a FAIL.
Exact invocations and image/software identities are retained by each run.
Finally run `python3 -B verification/fpga/current_board_review/comparison/collect.py`.

`*_compile_attempt01` preserves an initial failed software compile (GCC
misleading-indentation warning in the generated entry). It was corrected before
any Spike or VCS simulation. No test semantics or warning policy were weakened.

## Follow-on Evidence

[cycle_proof.md](cycle_proof.md) records real before-patch VMFPU/MASKU timing
for all-off, active-sNaN, and quiet-NaN controls, decoded from bounded explicit
signal-selected VCDs. [test_matrix.md](test_matrix.md) separates the additive
pure-prefix derivative, independent width/NaN matrices, real MASKU consumer
port tests, and pending after-image replay. The original five results above
remain frozen-image baseline results, not current-worktree acceptance.
