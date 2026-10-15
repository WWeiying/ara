# Original VL127 Port: Final03 Baseline Livelock

## Result

The exact source-bound single-case port passes Spike's complete original oracle
but reaches and livelocks at the target on the sealed final03 image. This is
not attribution from a timeout alone: completed maintenance repeatedly changes
v25's layout while the original extension remains unaccepted. No production
RTL or sealed input was modified; no RTL build was launched.

`measurement01/` is retained unchanged. **Use `cycle_review02/finding.json` for
the corrected cycle conclusion**, superseding its first analysis attempt.
The first decoder filtered only NORMAL_OPERATION and missed direct WAIT_IDLE
re-decode, producing `classifier_loop_proved=false`. Its unfortunately named
`target_backend_handshakes=65` meant all upstream handshakes while the target
was held, not original-instruction handshakes. The corrected fields explicitly
count 65 VSLIDEDOWN maintenance handshakes and **zero original VADD handshakes**.

## Identity and Reference

Original identity/source hashes remain in `STATIC_VL127_20261010.md`.
Only Linux entry/output/exit/TIOCOUTQ wrappers changed. Original assembly,
input generator, seed0/op2/VL127/mask-mode0, full 256-byte output oracle,
0xb26b tail, vstart return check, and both guards remain intact.

| Artifact | SHA256 |
|---|---|
| SoC port ELF | c159c6e393697c6b3fb3456c956d1b33720f4188650da2323c7e2d88ffbd1960 |
| Spike reference ELF | e4640497c67f139bc94bf968a3366e1aca7225f38b585e32a9e00384dd31ce52 |
| Spike executable | c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2 |
| final03 simv | 0352c1ffcf9e7340c904184ac2747dd054857bcf59b860ac76f23c0304d62721 |
| Normalized bounded VCD | e396b48abbac027f99dbfeebcaecdc97375e052a92ac580ffe1da3915f6145e9 |

`measurement01/build/reference_checked.json` and `spike_checked.log` record
Spike PASS with actual instruction49932c57, VL127, vtype0x9, vstart0, returned
status0, and `RVV_EXTENSION_PASS sew=16 cases=1 errors=0`. The initial
`reference.json` is a retained harness false-negative: this runtime stores its
log in RAM, not stdout. Reading that RAM log with Spike debug commands fixed
the check without changing either ELF or the runtime.

First SoC retirement: cycle82, PC0x80000000. Target PC from the ELF is
**0x800004cc** (Spike ELF target0x800004dc). The last retirement is cycle20087,
PC0x800004c8, opcode0096f2d7, vsetvli result127. The target request first appears
at cycle20086 as arch_seq9/opcode49932c57. Head-PC inference is no longer the
only evidence: request identity and internal handshakes are captured.

## Measured Cycles

Primary replay: `measurement01/replay/`, 180-second configured wall limit,
180.036 seconds including process termination, no RETURN/PASS. It records
one target arch_start, zero target cvx_req/retire, 8531 maintenance allocations
and 8530 completions; the last observed target allocation is cycle145203.
The C setup had already finished before cycle20086.

One same-image/ELF/seed follow-up captured 20050..21050ns, taking 37.16 seconds.
Its commit prefix matches the first replay; no software or timeout hints changed.
`cycle_review02/cycles.csv` samples immediately before each rising edge and
records after-edge EEW separately. Here cycle C occurs at C+15.5ns.

| Cycle | Observed event |
|---|---|
| 20086 | Decode VADD/ZExt extension, VL127, source EW8, destination/CSR EW16. Both overlap classifiers0; no snapshot; destination reshuffle001 selected. |
| 20109 | Upstream maintenance handshake: VSLIDEDOWN v24, EW8->EW16, VL64. |
| 20110 | Upstream maintenance handshake: VSLIDEDOWN v25, EW8->EW16, VL64. v25 EEW metadata becomes16. |
| 20125/20133 | Sequencer completions for destination v24/v25 maintenance. |
| 20134 | WAIT_IDLE directly re-decodes target; source reshuffle010 selected, classifiers still0. |
| 20135 | VSLIDEDOWN v25, EW16->EW8, VL128; v25 metadata becomes8. |
| 20151 | Source maintenance completes. |
| 20152 | WAIT_IDLE directly re-decodes target; destination reshuffle001 selected. |
| 20153/20154 | VSLIDEDOWN v24 EW16->EW16, then v25 EW8->EW16. |
| 20178/20179 | Source reshuffle selected again, then v25 EW16->EW8. |

The bounded window contains 43 architectural decode opportunities, 43 v25 EEW
flips, 65 upstream VSLIDEDOWN handshakes, no other upstream operation handshake,
and zero frontend target acceptance. The commit monitor reports 64 allocations
and63 completions in this window: allocation follows the upstream registered
request by one cycle, and the window ends with maintenance still in flight.
These counts are not contradictory and must not be called target execution.

Correction to the static prediction: the already-EW16 v24 is also redundantly
reshuffled at each destination batch; it is not skipped at the batch's first
register. This is additional maintenance, not the cause of v25's incompatible
source/destination requirements.

## Cause and Scope

Final03 dispatcher SHA remains
`4eda3df195e1a8ec319e51a14df1a051964cd08f6ee10335145a7c10cc89db4d`;
operand requester remains
`327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2`.
The extension's destination SEW equals CSR SEW, so the old widening-domain
test rejects it in the coordinated overlap/snapshot predicates. Successful
destination normalization destroys the required source layout; restoring the
source destroys the destination layout. Re-decode repeats this cycle without
accepting the original. This discriminates the cause from a stuck first SLDU
request or a dependency stall inside an accepted extension.

The parent's new scoped extension/snapshot candidate is NOT in final03 and
has not been measured here. The independent review's prefix-preservation concern
still needs directed tests. This case does not establish one root cause for all
42 historical records or full original Linux-program acceptance.

## Reproduction and Tool Notes

Run `adapter.py build --out <new-owned-dir>` to reproduce the port and reference;
`replay --build <build-dir> --out <new-owned-dir>` reuses final03, never builds RTL.
The bounded profile was generated before the first replay. For the measured
window use `capture --start-ns 20050 --window-ns 1000` with the same build.
`analyze.py <capture-dir> --out <new-owned-dir>` emits the corrected finding.
Do not overwrite measurement01 for follow-up work.

The FSDB converter exports the unpacked EEW array twice when its indexed
registrations are selected. The successful export is `selected_once.vcd`;
the decoder removes only 32 exactly identical declarations, checking identical
name/code/type/width and retaining every value change. Raw FSDB, raw exports,
conversion failures and normalization hashes are retained. This required only
offline processing, not another simulation. UCLI's forced end leaves outstanding
assertion attempts reported as unfinished; it is not an architectural PASS.

Five host adaptation/pin/oracle checks passed. Image/source/program manifests
were checked before and after both simulations. All owned simulator processes
have exited. Shared helpers, sealed inputs and production RTL were untouched.

## Final04 Addendum: Fixed Original-Source Single PASS

Read-only verification of the parent's completed final04 original-extension run,
2026-10-10. No simulation was restarted. The original-source VL127 port now
**PASSes its full unchanged oracle**, with exactly one target acceptance and
retirement and finite, completed maintenance. This supersedes the final03
failure only for this exact port/case on the new frozen image, not for the
six extension matrix groups or all42 historical records.

Evidence directory:
`/home/wangwy/fpga_runs/current_board_integration_final04/campaign/extension-original/tests/extension_overlap_vl127/`.
The stage `summary.json` reports PASS/exit0 in48.1497 seconds. Its console shows:

```text
RVV_EXTENSION_BEGIN seed=0 op=2 vl=127 mask=0 cap=128
RVV_EXTENSION_RETURN seed=0 op=2 vl=127 mask=0
RVV_EXTENSION_PASS sew=16 cases=1 errors=0
BOARD_CASE_PASS extension_overlap_vl127
BOARD_REPLAY_PASS
Core Test *** SUCCESS *** (tohost = 0)
```

`input.elf` SHA256 is still
`c159c6e393697c6b3fb3456c956d1b33720f4188650da2323c7e2d88ffbd1960`,
identical to the final03 baseline. Thus full256-byte/tail/guard/vstart checks
were not weakened to obtain the PASS. This remains an original-source
bare-metal port, not execution of the original Linux ELF.

Filtering the complete commit trace for opcode49932c57 gives arch_start1,
cvx_req1, retire1, uop_alloc4 and uop_done4, all backend records carrying
arch_seq9. Exact events:

| Cycle | Event |
|---|---|
| 20086 | Original request starts, same cycle as final03 baseline. |
| 20110 / 20121 | First preaccept maintenance allocates / completes. |
| 20125 / 20140 | Second preaccept maintenance allocates / completes. |
| 20126 / 20148 | Third preaccept maintenance allocates / completes. |
| 20149 | Exactly one frontend target acceptance (`cvx_req`). |
| 20150 | One postaccept execution uop allocates. |
| 20151 | Exactly one target retirement, PC0x800004cc. |
| 20167 | Execution uop completes; no later target-tagged event. |

Do not count the four target-tagged backend allocations as four original
instructions: three are maintenance before frontend acceptance. The first
capture followed by two destination normalizations is consistent with frozen
dispatcher SOURCE_SNAPSHOT_CAPTURE/RESHUFFLE code. The commit CSV does not
encode each backend opcode or snapshot bit, so that finer mapping is a static
interpretation, not a new waveform observation. The exact-one frontend
acceptance/retirement and all four completions are directly measured.
The full trace is VALID: eight allocations/eight completions overall, no
architectural request replay, no CVX replay or exception, and program retirement
continues through cycle33133. The former permanent maintenance loop is absent.

Additional pins:

| Artifact | SHA256 |
|---|---|
| final04 frozen ara_dispatcher.sv | 8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2 |
| final04 campaign/image/image.json | 6c6786cfaf55e803ba92a62662624ad2edfe6b257e7bd3234860e87192e8e3e8 |
| Original-port commit_trace.csv | 72fd6a5294cdd6cb1bb56ad8fd308cb7a22cf8eeb672e0e25375a0860f748007 |
| Original-port console.log | d60ca6237a082128e4056175045076fec84efc4f41fcd9315d97b28f9b7d53f2 |

**Matrix status is not asserted by this addendum.** The parent pipeline owns
the subsequent six shape runs; their earlier Spike results are references,
not final04 RTL acceptance. No duplicate group or combined144 run was launched,
and the separate final03 successor service was neither polled nor disturbed.
