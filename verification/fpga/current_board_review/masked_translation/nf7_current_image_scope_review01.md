# NF7 Current-Image Regression Feasibility

Read-only review, 2026-10-12. Only this document was created. No reference,
Host, build, VCS, RTL edit, live process query, or CSV read/reparse was done.
NF2 remains the primary running campaign; this is preparation advice only.

## Conclusion

**A full96 M6 acceptance was not found in the integration verification tree.**
The accepted NF7 result is the exact24-group/original96 source-derived trial
set on frozen M2. `CURRENT_SCOPE.md` still attributes it to M2; its older row
mentions an M4 gap, not a later M6 acceptance. Searches of current review,
plan/result/complete artifacts and the NF7 subtree found no M6 NF7 terminal.
This is a bounded repository evidence conclusion, not a claim about other
machines or unrecorded runs.

The smallest complete current-image regression is **the same24 existing SoC
ELFs, once each**, with their four trials and full original group oracle intact.
No rebuild, new Spike reference, slicing, or new test algorithm is needed.
A one-group startup pilot may be `nf7_g00` (trials0..3), counted as group00 of
that same24-run campaign, not repeated afterward. It is not full96 acceptance.

## Exact Existing Evidence

Paths in this section are relative to `masked_translation/indexed_review/`.
The following files were read and their actual SHA256 recomputed:

| Artifact | SHA256 |
|---|---|
| `geometry01.json` | `496413f2fc5ef86f08767ed0059ab91cdcdae671a457afa36a07d77260981bfc` |
| `sv39/vcs_plan06/plan.json` | `edc7b0e20d0ef1cbf99b978421b8ca5df1eb9ce6505ec22e3bbc69db3e901839` |
| `sv39/vcs_plan06/programs/programs.json` | `f39037e695688e0706324b3f9d27dc62e0765848348e306d19a4d8f4572f611c` |
| `sv39/vcs_plan06/reference_acceptance.json` | `cdbf1906768e02d07501533f7a5f2d0aeac7a8990fc7f2b3074b412ba20ebbbf` |
| `sv39/vcs_plan06/complete.json` | `dea28b2cc035c63558b9369949a11b6faede8584b9bf81d0ed592f7aad0fc1a4` |
| `sv39/terminal_audit01/results/complete.json` | `183b1bd1a268741f5c49dfa97b57ae9a8e239ff02bd5e478a3773f94bcf63a80` |
| `sv39/terminal_audit01/results/evidence_pins.json` | `adb3cd297087c1f3109a9358b51abb9cd144a013a1793229b6a27a68dfe97a07` |
| `sv39/csv_oracle.py` | `246a21b910becd67dc271e32107fcfdce36191317924f7829a01b47f8c5b4451` |
| `sv39/reference.py` | `f8ec3cc86956d6d1dacd4e99e9da74c10b9d70ee09e966acb47aa6fd7eb3e05d` |
| `sv39/ledger.py` | `5eb425300a8ba18764134899fd9767421af55b389be6f4d01bc3ae05dc9c4212` |
| `sv39/terminal_audit01/audit.py` | `dac3c83be65880a76cc5ce1f94df638aaf9761ca853b4aba73f41d7a883c850f` |

The hashed programs manifest is the exact ELF inventory, not an illustrative
list: names `nf7_g00`..`nf7_g23`, group g containing trials4g..4g+3, each entry
binding its absolute source ELF path, full SHA256 and `IX_SV39_PASS` marker.
All24 source ELFs were rehashed here and matched the accepted reference and
M2 private `vcs_plan06/groups/gNN/run/tests/nf7_gNN/input.elf` hashes. Membership
is exactly0..95 once. Their paths under `sv39/` are:

- g00: `reference01/group00/soc.elf`.
- g01/g06/g18/g23: `reference02/groupNN/soc.elf`.
- All other19 groups: `reference03/groupNN/soc.elf`.

The old terminal independent audit accepted24 complete CSVs,284816 comparisons,
168 checkpoints,72 precise page faults (36 load/36 store),96 S-mode ecalls,
and exact full oracle/returncode/no-abort/time/pin checks. It recorded24531873
rows/24492801 retirements. This review binds that prior audit, not a new CSV
recomputation. M2 image.json SHA:
`384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
Original service exit0 was parent-observed before GC; the old audit does not
invent historical exit status from later missing-unit defaults.

Original archive identity, as bound by geometry/source provenance:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery12_indexed_failure01/rvv_fault_replay_segment_nf7_indexed_e32_mf2`,
ELF SHA `581a695b625716256771c14df272b7afa912b1fa55f6180822d5bc7d17c87b42`;
adjacent `.S` SHA `3feee0ad33d2005fe47f47a18b4c7592827388b0f9f61dc2faab258fc5c2b845`.
The archived assembly is linked unchanged into the adapter. Current C oracle
SHA `631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a`
is pinned, **not proven byte-identical to the C compiled into the Linux ELF**.
Original board aggregate:96 trials/72 signals/one check error, failing trial
and phase unknown. Do not call this a localized original RTL root cause.

## Geometry And Non-Overlap

NF7 is ordered `vloxseg7ei32.v` / `vsoxseg7ei32.v`: e32/mf2, VL8, indexEEW32
in v16, data v24..v30, capacity16 words/field. Its96 combinations retain
unmapped/protected modes, load/store, boundaries1/3/5, masksff/aa/24/00 and
split0/1 (field boundary0/3). Scrambled indices address nonoverlapping segments.
The oracle retains all field tails, physical upper halves, v23/v31 and v16,
full buffers, guards, both4KiB data pages (8KiB total), PTEs, CSR restoration,
permitted fault-field tval, partial-segment state, prefix poison and same-PC
nonzero-vstart retry. Do not tighten partial completion into atomic rollback.

M6 RVV-01 whole3 is different: e32/m2 VL32 destination v4 (overlap) or v16
(disjoint control), indexEEW64/e64m4 in v4, **single-field** gather load,
50 full rounds plus the resident restart control. Its measured mixed-EEW
dedup/snapshot defect and repair cannot close NF7's disjoint v16/v24..v30 path.
The additional `indexed_load_groups_overlap` preservation condition is false
for NF7's disjoint sources/destinations, but shared dispatcher/indexed AddrGen,
VLDU/VSTU, exception and completion behavior still merits a current-image test.

M6 representative48 contains38 original/10 smoke programs, not NF7. All48
accepted ELF hashes were compared with this NF7 set: **intersection empty**.
Its16 cycle-identical controls are not NF7 performance evidence. M6 whole3 and
reg48 use image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`,
at `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.

## Minimal Successor And Time

Use a new small M6 wrapper/plan around the existing integration runner and
unchanged `csv_oracle.Checker(symbols,cases,status,ledger)`. Reuse all24 original
ELFs, per-group symbols/cases/reference statuses and `vcs_plan06/ledgers/gNN.json`.
Retain every group's initialization and all four in-order trials, including
predecessors; do not extract only the last trial. This preserves the previously
accepted partition scope, not a new claim of one continuous96-trial Linux run.

Old actual group records give1345.250..1800.927s per group (22.42..30.02min),
sum37650.243s/mean1568.760s. Runner-only values are1330.251..1783.667s.
Replaying the recorded durations in original group order estimates:

| Jobs | Ideal work/jobs | Ordered scheduling estimate |
|---:|---:|---:|
| 2 | 18825.1s /5.23h | 18890.8s /5.25h |
| 3 | 12550.1s /3.49h | 12887.4s /3.58h |
| 4 | 9412.6s /2.61h | 9689.7s /2.69h |

These are estimates from M2 actual elapsed, not M6 or current-contention
measurements. Each original2400s case budget and2700s group envelope is below
3h. **Full96 is not a <=3h total guarantee**, even at4 jobs. Preserve bounds
initially; outer service must cover all waves plus teardown/observer time.
The old2-job service allowed33600s; old4-job planning allowed16800s. If total
wall time must be <=3h, stage immutable whole groups across separately
authorized batches, retaining results without rerunning accepted groups; no
scope/timeout/oracle reduction to manufacture a full96 claim.

## Hard Prerequisites Before Launch

1. Parent authorization and capacity allocation after/around primary NF2 work;
   do not reuse old alias/arithmetic reservations or silently take NF2 slots.
   Fresh bounded admission must account actual+reserved simv under24 and at
   least32GiB available, fail closed on unreadable inventory, and never stop
   external jobs. No resource or service query was made in this review.
2. Freeze a new plan binding exact24 runtime IDs/96 trial membership, identical
   ELF bytes, full oracle/ledgers/reference identities, M6 image/DSOs/config/
   frozen-source manifest, and new runner/checker hashes. Recheck at launch and
   terminal. Do not call old M2-only `check_image`/terminal entry points or
   mutate their globals/sealed sources to make them appear M6-compatible.
3. Runtime-label gate: actual `+TESTCASE=nf7_gNN`, run.tests, summary.name,
   private input path and commands must match the program manifest key, **not**
   the historical Linux basename. The old NF7 terminal checker already uses
   the correct runtime name (`terminal_audit01/audit.py:92,126`); preserve this
   behavior while replacing M2-only image/path assertions. Keep historical
   identity in separate provenance fields. Add offline negative coverage for
   wrong labels/image/ELF, partial membership, PASS+FAIL, timeout and abort
   before any successor launch; none was executed here.
4. Preserve immediate firsterror/default-trap/mismatch rejection, full scalar
   oracle and exact traps/retry/checkpoints, both-raw-log failure veto, complete
   CSV and CTRL0/magic/marker gates. Expected page-fault logs are not generic
   failures. Log-read exceptions, late cancellation or exceeded elapsed bounds
   cannot become PASS merely because the legacy runner writes a success row.
5. Persist actual numeric simulator/runner exits before downstream metadata
   checks, including their exception paths. Pin durable service generation/
   exit evidence where required; GC/missing process is not exit0. Use an
   independently bounded process group/cgroup, no automatic retries, and an
   outer deadline larger than inner work+teardown+observer bounds. Terminal
   acceptance must require all24 current-M6 results; old M2 PASS is baseline
   provenance only. No raw/reference rerun or source rebuild is needed now.

No runner was prepared or authorized by this review. Original Linux signal ABI,
whole-parent execution history and identification of the historical single
check error remain outside any proposed M6 source-derived96 acceptance.
