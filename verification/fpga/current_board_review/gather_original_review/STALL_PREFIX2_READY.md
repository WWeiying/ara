# Two Authentic Child Prefixes Prepared

2026-10-11. Preparation only: **no DUT launched, no RTL/image changes**.
Successful fresh directory: `stall_prefix2_03/`. Accepted83 inputs/results
and `STALL_PARENT_PLAN.md` are unchanged. Original stopped tuple is **unknown**;
these prefixes are not claimed exact reproductions or closure of the eleven
archived failures, nor original Linux ELF/full-parent acceptance.

## Review Entry

- `stall_prefix2_03/prepared_ready.json`: exact two source keys and result bindings.
- `stall_prefix2_03/source_elf_proof.json`: original C/ELF/asm identities and limits.
- `stall_prefix2_03/source_diffs/`: separate Linux adapter and prefix-only diffs.
- `stall_prefix2_03/host/host_gate.json`: two positive and fourteen negative tests.
- `stall_prefix2_03/reference/reference.json`: raw-retirement/fulloracle results.
- `stall_prefix2_03/soc01/programs.json`: runnable SoC ELFs and compiler identity.
- `stall_prefix2_audit01/audit.json`: independent raw-log reparse and nine negative gates.
- `check_stall_prefix2.py`: read-only checker; explicit fresh audit output required.

Prepared-ready SHA256:
`a6eb525b0f3461f7d5711e101e596d1d77bbe998ef26ae5be177acd0f956177e`.
Source/ELF proof SHA256:
`11501fc70fe5d4f8d7289954158c04527b04f7e63f083a89c26949185b0b1884`.
Independent audit SHA256:
`ce33455e35cb3a05ff9b31f76b2e6ef650172ede3b730bc9703e07227984684e`.
Audit status is `PASS_TWO_SOURCE_PREFIX_IDENTITY_AND_RAW_FULLORACLE_AUDIT_NOT_DUT`;
all nine negative checker gates passed.

## Exact Bound and Preserved History

Only `rvv_permute_restart_e8_m4_ops1` and
`rvv_permute_restart_e8_m4_ops20` are prepared. Source/manifest mapping fixes
e8,m4 at VLEN1024, capacity512. The companion vv archived boundary maps to
seed0 / selected-op / scalar-index0 / length-index6 / mode0 / trial1:
VL512, vstart256, scalar0, all-on mask. It is the **98th selected child call**,
not66;66 belongs to e8m8. The checker rejects bound66.

All original loops, excluded-op empty iterations, RNG/input/index setup,
per-call predicate/destination setup, full thirteen-instruction assembly,
returned-vstart check, fullcap oracle, both guards and cumulative statistics
remain. The only semantic stop is `if(cases==98)goto prefix_done;` **after**
the original full oracle/guards and `++cases`. A final exact-count check and
separate `RVV_GATHER_PREFIX_PASS/FAIL` marker prevent a short prefix from
claiming the original2688-call PASS. Standard integration entry/I/O/exit
adaptation is separately diffed; no added vector op, reset, fence, per-call
UART, checkpoint restore, scalar-oracle thinning or six-loop single narrowing.

Thus there are97 actual same-op predecessors before the boundary target.
The partition also preserves896 excluded-op empty iterations before op1,
17920 before op20. These do **not** execute the other original parent ops;
the parent has different predecessor state. No original stopped tuple was
inferred from the companion vv marker or prior numeric DETAIL messages.

The host fixture checks every call's original RNG-filled input, truncated
8-bit indices or full16-bit indices, all128 mask bytes, output initialization,
guards, VL/start/scalar and complete tuple order against an independent
Python model. Injecting one active/prestart/masked/tail/guard0/guard1 value or
nonzero returned vstart is caught while all98 calls still execute. Both host
positives and all14 injected negative runs pass their expected exit gates.

## Measured Reference Evidence

| Prefix | Target/returned vstart | Fullcap reads / guards | Firmware retired through exit0 | Reference elapsed including trace validation |
|---|---:|---:|---:|---:|
| e8_m4_ops1, vx | 98 / 98 zero | 50176 / 196 | 2148472 | 29.55s |
| e8_m4_ops20, indexed-e16 | 98 / 98 zero | 50176 / 196 | 2280966 | 30.96s |

Each actual Spike trace independently verifies50372 scalar output/guard
loads, their values against the per-call model, actual target scalar registers,
98 matching target encodings,98 CSR returns0 and committed HTIF store1
(exit0). Boot ROM's five instructions are excluded from firmware counts.
Runtime console is reconstructed from **actual committed byte stores** to
existing `replay_log` RAM; no fabricated PASS and no dependence on debug stdout.
All expected prefix/case/replay markers occur, with no FAIL/TRAP/MISMATCH/DETAIL.

The first and98th target retire ordinals are42152/2136978 for vx and
167506/2268777 for indexed-e16. Target-to-target retired intervals are
18770..31236 (median21475) and18771..31877 (median21476), respectively.
These counts are software retirement, **not measured DUT cycles**.

Existing Spike/GCC/runtime only. Each source reference executes once, with
120second subprocess wall limit,5000000 interactive `rs` steps and768MiB
per-file cap. `--instructions` alone would not bound Spike's interactive
`until`; the prepared debugger script deliberately uses bounded `rs`.
Commit logs are138947762 and147010207 bytes. No limits were raised.

At the prior Gather75 measured whole-run273..528 retired instructions/second,
these retirement counts suggest approximately68..131 and72..139 minutes of
VCS work per full98-call prefix. This is a planning extrapolation, not a
validated DUT runtime or proposed higher timeout. **The full prefixes are not
admitted to a300second DUT batch.** Large-VL gather latency could further
change timing. No shortened oracle/history variant is substituted to fit it.

## Archive Source Versus ELF Proof

Canonical archived C is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`,
SHA256 `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
It is the unfiltered shared partition oracle and equals the archived partition
manifest's source hash. `SEW=8`, `RESTART_PERMUTATIONS=1` and masks2/1048576
bind these exact children. Assembly/header are copied from their authentic
archived child directories. Canonical release ELF and frozen stall-scene ELF
both match their original recorded hashes. Archived PCs bind to the exact
13-instruction routine, all encodings identical in source-port SoC and Spike:

| Prefix | Original ELF SHA256 | Archived target PC | SoC target PC |
|---|---|---|---|
| vx | `8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8` | 0x105dc | 0x800006fa |
| indexed-e16 | `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18` | 0x10980 | 0x80000a9c |

**Entire original ELF byte-identical rebuild is not proven.** One bounded
rebuild per child with the authorized existing GCC produced a different ELF.
Read-only `.comment` comparison identifies original Buildroot2026.02 GCC14.3.0
versus current Xuantie GCC14.1.1; .text/rodata/BSS layout and eh_frame differ.
No compiler substitution, flag search or rebuild retry was made. Consequently
the proof is authentic archived source hash/manifest/flags plus exact original
assembly encodings, not a claim that the whole newly compiled C binary is the
archived Linux binary. Both originals and the nonidentical rebuilds are saved.

## SoC Artifacts and Frozen Image

`stall_prefix2_03/soc01/gather_prefix_e8_m4_ops1.elf` SHA256:
`e3f79fd61e9d3d35ffc1773ba9599630ec69bdbc42b117c103f1b48a367941e5`.

`stall_prefix2_03/soc01/gather_prefix_e8_m4_ops20.elf` SHA256:
`be97b7369ae580019755ac4c5d6e331677050d110943e777142441594490c7f2`.

Reusable frozen image remains
`/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`,
image.json SHA256
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
The compiled ports require VLEN1024/4lanes and retain the existing integration
runtime. No VCS driver/service or image build was created or launched here.

These two programs are useful beyond accepted83's VL2 source singles: they
exercise512-element groups, real same-child histories, all four mask patterns
at earlier lengths, VL511, and the VL512/vstart256 boundary. vx uses constant
in-range index0; ei16 uses authentic mixed in-range/OOR16-bit indices, including
511,512,513. They discriminate scalar request behavior from index/data token
behavior, but Spike itself cannot establish Ara queue progress or RTL repair.

Preparation host failures are retained separately: `stall_prefix2_01` stopped
because resolving the gcc wrapper invoked ccache directly; `stall_prefix2_02`
stopped at `-Werror` for an unused host fixture constant. Neither ran Spike or
DUT. Their exact failed preparer snapshots and errors remain. Only host harness
selection/unused fixture generation changed before fresh03; original C/asm,
98-call stop and reference budgets did not change.

Next decision: review this exact two-prefix preparation and measured cost.
No automatic DUT execution, timeout increase, parent expansion or claim of
eleven-stall acceptance follows from `prepared_ready`.
