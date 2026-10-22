# M6 e16/m8/ops1 Prefix98 DUT Case Audit

Verdict: **DUT_CASE_PREFIX98_INDEPENDENTLY_ACCEPTED_NOT_FULL2688**.
This accepts only the completed SoC DUT case, not worker/service actual exit0,
original Linux execution, the entire2688-call child, or an exact old stall tuple.
No indexed-fault output/process was inspected; no DUT rerun or sealed edit.

## Actual Terminal And Raw Recompute

Original complete status is PASS_M6_ORIGINAL_E16M8_PREFIX98_NOT_FULL_CHILD,
aborted=false, retries0, pins_unchanged=true. Its exact result equals the runner
summary: PASS, **simulator returncode0**, elapsed2980.8859622s within9000s.
Runner is COMPLETE/PASS1 with the expected case, jobs1, timeout and image.
Both raw logs pass the exact98 full oracle/normal exit and failure-veto gates.
Private ELF, inputs/image hashes, command and working directory all match.

The frozen generic trace validator and source-derived strict checker consumed
the original CSV. Independent `recomputed_strict_prefix.json` equals the stored
strict report structurally and **byte-for-byte**, SHA:
`9e276ae7bda91801fd2f201bb3739e35f78f02da54491bcf4be2f7d6d3b59066`.
CSV SHA: `a3e2401dca85dd735488125107ee52692e0faaa0f6f54d03cbc3313f8217685b`.

| Actual Checked Evidence | Count |
| --- | --- |
| Original helper calls / each of13 encodings retired in order | 98 / 98 |
| Source/setup values per call, reconstructed from actual scalar stores | 2178 |
| Full512-halfword outputs / two guards per call | 50176 / 196 |
| Actual complete output-and-guard scalar loads | 50372 |
| Returned vstart0 and actual args/VL/scalar/vstart checks | 98 |
| CSV rows / architectural retirements / last cycle | 2002084 / 1997782 / 2980012 |
| Backend allocated/completed uops / CVX exceptions | 528 / 528 / 0 |
| Original CTRL0 exit / permitted post-exit parking retirements | 0 / 6 |

All RNG/input/index/predicate/output initialization, prestart/masked/tail values,
guards, three vsetvli returns per helper and target308e4c57 are retained and
checked; no original oracle was removed or expanded. Natural endpoint is
`[0,1,0,6,0,1]`: ordinal98, VL512, vstart256, scalar0, DUT target80000708
at cycle2958753. Full capacity includes every masked/tail/prestart element.

## Identity And Scope

All708 plan pins and the exact11 terminal evidence pins verify, with original
hashes unchanged through the audit. The combined723 bindings are in `audit.json`.
Frozen M6 image/configuration/snapshot independently verify through the existing
shared gate, without any service/process query or build.

- Plan: `e4476bec15fadab91251915d44bc156e24c9191abd0aea0359a32d372336f5c2`.
- Image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
- Config: `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.
- Snapshot: `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.
- Executed SoC ELF: `161f41852ebbe6d7d9a0574691c39435dec3229b1017b20462e6211fb82fe74d`.
- Authentic Linux ELF: `25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a`.
- Authentic C: `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.

The archive source is the shared permutation C at
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`;
the child ELF is release/binaries/rvv_permute_restart_e16_m8_ops1 in the same
campaign's rvv_permute_partitions01. Actual archived disassembly confirms one
exact13-instruction helper window, target PC105ee. SoC/Spike helper encodings
agree; full raw reference identities/counts are pinned. The SoC runtime/compiler
port is not the Linux ELF, and an entire original Linux binary rebuild is not
proven. The first98 natural calls do not cover the remaining2590 child calls,
Linux/parent history, other stall sources, or the unknown historical stopped tuple.

## Exit Provenance Boundary

The numerical simulator rc0 is present in the actual frozen runner result and
complete.json, supported by raw full oracle/CTRL0 and independent recomputation.
**Worker/service actual exit status is unavailable after the parent's reported
GC.** Not-found and a missing simv are not positive exit0 evidence here; neither
was queried or used to prove success. This audit must not substitute for actual
service-exit evidence in a coordinator requiring it.

The owned auditor's initial post-recompute Path-type error and explicit
retained-result finalization are documented in `INITIAL_AUDIT_NOTE.md`.
The full raw recomputation was preserved, not overwritten or regenerated;
its unpersisted elapsed duration is null rather than invented. Only new owned
audit files were written. No original helpers, records, RTL or images changed.
