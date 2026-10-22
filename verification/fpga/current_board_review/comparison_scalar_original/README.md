# RVV-12 Scalar Comparison Restart: Original19

## Terminal Acceptance

**Candidate04:19/19 archived genuine scalar-comparison singles PASS.**
[Independent terminal audit](terminal_audit01/README.md) and
[raw-evidence checks](terminal_audit01/finding.json) verify exact membership,
same staged ELF, actual candidate04 image, full original oracle, failure-marker
veto and zero exit for every case. All1321 plan pins,166 source pins and539
frozen snapshot files were rehashed unchanged. Each complete CSV contains one
target VMSEQ.vx allocation, retirement and completion, with continuous scalar
retirement order and no exception indications.

The service terminated inactive/exit0. Recorded overall walltime481.53s;
representative e8/m2 completed in49.86s. No simulation was repeated for this audit.
Acceptance is limited to the19 original singles, not full parent matrices,
all12 scalar operations or original Linux ELF execution. No common historical
root cause is inferred merely from these passes.

## Recorded Startup

On2026-10-11, after the host/Spike/provenance gates below passed, independent
service `ara-rvv12-scalar19-candidate04-01` started. Actual simv PID42429 was
confirmed running the e8/m2 representative on the existing candidate04 image.
Output is [vcs_candidate04_01](vcs_candidate04_01/). This paragraph preserves
historical startup evidence, not the terminal status; the later acceptance is
recorded above. No long-batch polling followed this startup confirmation.
The representative gates the remaining18 jobs2. Sealed replay driver SHA256:
`1f73b36ee40b3526cf84f3f81e0765310350fc998542f07c66150012e034c53e`.

## Scope and Provenance

These are19 genuine archived `rvv_small_masks_scalar_restart_*` singles,
not the4032-case parents. Assembly retains all12 functions but the original
single C driver executes only seed0/raw_op0/mask-mode0, oneVL and onevstart.
Actual instruction: `vmseq.vx v24,v8,t3,v0.t`, t3=-3. Mask-mode0 is all-on.
Scalar boundary values and original xorshift input generation remain unchanged.

Archive root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`.

- `rvv_additions35/binaries/rvv_masks_scalar_restart_*`: original Linux ELF.
- `rvv_mask_first_trace01/rvv_trace_masks_scalar_restart_*/original_rebuilt.elf`:
  hash-identical rebuilt original; accompanying assembly matches each single.
- `rvv_small_masks02/`: original single C/assembly/operations.h, ELF and manifest.
- `rvv_mask_symptoms02/symptoms.json`: matched single/prefix first wrong bit,
  returned vstart, guards and error count. All19 records are confirmed.

[166 source pins](prepared01/source_pins.json),
[exact tuples and original ELF hashes](prepared01/tuples.json),
[unchanged sources and wrapper diffs](prepared01/prepared/) and
[ported address map](prepared01/address_map.json) retain identity.
Only Linux syscall/entry/exit wrappers were changed for Spike/SoC. The original
assembly and complete scalar oracle block are byte-preserved.

Original setup loads full-capacity v8/v16, predicate v0, and old destination
v24 through vlm.v from output filled with0x5b. The target restores original
VL/vstart, then immediately reads returned vstart and stores v24 at capacity.
The oracle checks every capacity bit plus both distant64-bit guards; it retains
the original permitted agnostic choices, not a stricter replacement oracle.

## Exact Tuples

All rows: seed0/op0/scalar-3/all-on mask/returned vstart0. The historical first
wrong bit is2, prestart, old/expected0 versus actual1 in every row. Error totals
below are archived failing-trial totals, not current DUT results.

| Shape | Capacity | VL | Vstart | Historical Errors |
| --- | ---: | ---: | ---: | ---: |
| e8/mf8 | 16 | 8 | 4 | 1 |
| e8/mf4 | 32 | 16 | 8 | 3 |
| e8/mf2 | 64 | 32 | 16 | 6 |
| e8/m1 | 128 | 64 | 32 | 16 |
| e8/m2 | 256 | 128 | 64 | 33 |
| e16/mf4 | 16 | 8 | 4 | 1 |
| e16/mf2 | 32 | 16 | 8 | 3 |
| e16/m1 | 64 | 32 | 16 | 8 |
| e16/m2 | 128 | 64 | 32 | 16 |
| e16/m4 | 256 | 128 | 64 | 33 |
| e32/mf2 | 16 | 8 | 4 | 1 |
| e32/m1 | 32 | 16 | 8 | 4 |
| e32/m2 | 64 | 32 | 16 | 8 |
| e32/m4 | 128 | 64 | 32 | 16 |
| e32/m8 | 256 | 128 | 64 | 33 |
| e64/m1 | 16 | 8 | 4 | 1 |
| e64/m2 | 32 | 16 | 8 | 4 |
| e64/m4 | 64 | 32 | 16 | 8 |
| e64/m8 | 128 | 64 | 32 | 16 |

## Reference Gates

[Host evidence](prepared01/host.json):19 positive oracle checks PASS; four
selected negative checks independently flip an active bit, prestart bit, guard,
or returned vstart, and each is rejected by the original oracle. Host-only C
uses a constant VLENB and an op0 emulator; this is oracle/wrapper self-testing,
not an architectural or RTL measurement. SoC/Spike source does not include
these host substitutions.

[Spike evidence](prepared01/reference.json):19/19 PASS with original assembly,
full oracle, actual target VL/vstart/t3 recorded and replay_exit a0=0. All166
source pins were rehashed unchanged. No DUT result is inferred from this.

Representative: e8/m2 VL128/start64, source has a scalar-boundary pattern that
distinguishes full-stream origin from a64-element displacement. Candidate04
has comparison source start0 and existing MaskB start0, while retaining
architectural vstart in MASKU. This is the current static contract to test,
not an assertion that all historical errors shared one cause.

Representative SoC PC `0x80000544`, opcode `0x608e4c57`; ELF SHA256
`4bb78c650fdb532dcce58ed576c371dea08547e4d94cf4cb5977d03decf9c575`.
Spike ELF SHA256
`d6902e7d97c987ead79d3d1584382f016281d1850bc8b6bfdebfc5182a6354c5`.

## Replay Plan

Use existing candidate04 image ledger SHA256
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
[replay.py](replay.py) reuses integration/run.py and its frozen runner, no build
or RTL edits. The representative must finish full-oracle PASS before the other18
launch atjobs2. Each ELF is bounded180s with explicit RVV_MASK failure-marker
veto, first failure cancels the queue and preserves evidence. Admission checks
global24 simv and32GiB available memory, reserving NF7 capacity when needed.
All other live processes, including NF8/gather, count toward the cap.

Fresh output: `vcs_candidate04_01/`; independent background service outer2400s.
After actual simv startup confirmation, no long-batch polling. Source singles
are the acceptance scope; complete Linux programs/parent matrices remain distinct.
