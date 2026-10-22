# Remaining Historical Gather Stalls

Read-only source/evidence recovery, 2026-10-11. **No DUT, build, reference run,
RTL edit, or sealed-input change.** M6 indexed-memory pilot is unrelated to
this register-gather inventory and was not polled. This note updates the next
selection after the accepted M5 prefixes; it does not supersede archived FAILs.

## Evidence Roots

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `P=C/rvv_permute_partitions01`
- `R(N)=C/rvv_recovery08_N/terminal_scene`
- `H=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review`
- Historical classification: `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/STALL_TRIAGE.md`, section D;
  exact records: `C/stall_family_triage02/triage.json`, group `gather_operand_stream`.

All eleven canonical ELF hashes, matching scene ELF hashes, report hashes,
and two-snapshot no-retirement observations were freshly rechecked for this
note. All eleven have `last_trial=null`; the evidence establishes stalled
program identity/opcode, **not the exact unreturned call**. Archived cycle
deltas are 559824418..598691642 with unchanged retirement and PCs, not a new
SoC timeout. Head PCs have no validity proof; do not call them accepted CSR
instructions or infer an internal queue state from zero DDR outstanding.

## Exact Eleven

Every suffix below means `rvv_permute_restart_<suffix>`. Canonical original
Linux ELF: `P/release/binaries/<name>`; scene copy: `R(N)/<name>`; raw report:
`R(N)/report.json`. Original assembly/header: `P/<name>/operations.S` and
`operations.h`. All eleven children retain **2688 calls each**, not one tuple.

| Suffix | Recovery N | Snapshot last/head PC | Last DETAIL VL/start; element | Original ELF SHA256 |
| --- | ---: | --- | --- | --- |
| e8_m4_ops1 | 154 | 105dc/105e0 | 256/128; 4 | `8f5fd128fdc39014de31bd72f9e997f76d07382ee6268d7e6da83a59b7ddfcd8` |
| e8_m4_ops2 | 155 | 10600/10604 | 256/128; 4 | `498805cf438a11729e74f0ac7b74068fa5e19bbcf56318790b01afc798d18b65` |
| e8_m4_ops3 | 168 | 1063e/10642 | 256/128; 3 | `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b` |
| e8_m4_ops20 | 169 | 10980/10984 | 256/128; 4 | `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18` |
| e8_m8_ops1 | 171 | 105dc/105e0 | 3/1; 0 | `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf` |
| e8_m8_ops2 | 172 | 10600/10604 | 3/1; 0 | `cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712` |
| e8_m8_ops3 | 173 | 1063e/10642 | 3/1; 0 | `ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c` |
| e16_m8_ops1 | 175 | 105ee/105f2 | 256/128; 3 | `25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a` |
| e16_m8_ops2 | 176 | 1060e/10612 | 256/128; 3 | `13a9b694ade91e25687108b4bf93b50ecc2d80c3a2a6fd532b269dac3b4aafcf` |
| e16_m8_ops3 | 177 | 1064a/1064e | 256/128; 3 | `16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853` |
| e16_m8_ops20 | 178 | 10994/10998 | 256/128; 3 | `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888` |

All last DETAIL rows have seed0/scalar0/mask0. They are **post-return oracle
observations**, not pre-call markers: `original.c:80` calls the helper, then
lines81..94 check data. VL256/start128 maps to selected-child call66 (length
index4, trial1); it proves the checker reached that returned call, not that
the entire oracle finished or the next call stalled. VL3/start1 admits trial0
or trial1 (call49/50); no unique stopped ordinal follows. Report outputs have
only 3..10 DETAIL rows, and source printing is capped at the first20 errors;
do not infer a precise later call from the last printed row or missing text.

Recovery168 uniquely records four earlier **processes**, ops8 -> ops9 -> ops10
-> ops11, each PASS2688, before ops3 stalls. Their PASS is not ops3 PASS.
Other ten reports list the stalled case first. A `previous_report` link is
administrative history, not proof that another process ran without reset in
the same machine state. Do not fabricate a short warmup to replace these.

## Authentic Source and Available Boundaries

Shared complete partition C, not a reduced scenario:
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`, SHA256
`b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
This was rechecked against `P/manifest.json`'s `permutation_oracle.c` hash.
Each child selects `PERMUTE_OP_MASK=1U<<op`, SEW and LMUL from the manifest;
`P/parent_mapping.json` binds its original parent. The three parents live at
`C/rvv_permute_restart01/overlay/opt/ara-tests/rvv_permute_restart_<shape>`;
their hashes were rechecked against `STALL_PARENT_PLAN.md`. Parent originals,
partition ELF aliases, reduced singles, and SoC source ports are different
acceptance scopes, not extra independent failures or interchangeable binaries.

Ops1/2/3/20 target opcodes are respectively `308e4c57`, `30803c57`,
`308fbc57`, `38880c57`: vx, vi0, vi31, ei16.vv, all masked v24/v8 forms.
Every snapshot head is target+4, `00802573` (read vstart). e8_m8_ops20 is
authentically excluded because the index EMUL would be16; do not add it.

Companion **op0** records R153, R170, R174 do print the pre-call marker
`VL512/vstart256`. Those are different records, classified as
`packed_mask_restart_boundary`. Source print condition additionally fixes
seed0/scalar-index0/mode0; the helper immediately follows the print/drain.
Their natural child endpoint is call98 for cap512 (e8m4/e16m8), call66 for
cap1024 (e8m8). These are justified localization boundaries for the eleven,
**not recovered exact failing tuples for them**. Earlier full-parent records
provide companion evidence, not permission to skip actual parent predecessors.

## Reuse, Do Not Repeat

Use existing M5 evidence at
`H/gather_repair05/m5_successor01/prefix_terminal_audit01/{TERMINAL.md,audit.json}`
and `.../prefix_vcs_candidate05_01/replay/tests/`:

| Accepted original child prefix | Calls | Fullcap checks / guards | Retired | Cycles | Elapsed s |
| --- | ---: | ---: | ---: | ---: | ---: |
| e8_m4_ops1 | 98 | 50176 / 196 | 2092785 | 3021740 | 3046.565 |
| e8_m4_ops20 | 98 | 50176 / 196 | 2225267 | 3350943 | 3257.146 |

Both include the real original setup, all13 assembly instructions/call,
returned-vstart checks, full oracle, guards and original sequential history
through VL512/start256. Reuse this acceptance; do not launch either again just
to populate a new table. It also covers the known M4 numerical call66 repair;
that numerical failure is not proof of the old stall location. M5 acceptance
is not automatically M6 acceptance. Existing83 M4 numerical singles cover
other shapes and do not close any of these eleven large-group histories.

Original Linux ELF byte-identical rebuild remains unproven with the current
compiler; source/manifest/assembly proof is available. Neither accepted prefix
closes its full2688-call child, the full parent, or original Linux execution.
All eleven historical stall records remain open at those original scopes.

## Next Discriminating Test

**First prepare, for review: e16_m8_ops1 natural first98 child calls.** Endpoint
tuple `[seed=0,op=1,scalar-index=0,length-index=6,mask=0,trial=1]` is VL512,
vstart256, scalar0, cap512; original target0x105ee/opcode308e4c57. Compared with
accepted e8_m4_ops1, capacity, loop history shape, masks, scalar index and active
boundary are identical, but data EEW and group layout change to e16/m8.
The constant in-range scalar source also avoids conflating this first test
with ei16 index truncation/OOR token handling. It is a localization prefix,
not a claim that the archived unreturned call has been recovered.

Retain all97 predecessors, excluded-op empty iterations, original xorshift
input generation, fullcap loads/stores, all-capacity oracle, guards and CSR
checks. Stop only after call98's full oracle with a separately labeled PREFIX
result. Do not narrow to the endpoint single or add vector warmup/drains.
Reuse the accepted prefix adapter/checker contracts in a fresh owned successor;
do not modify sealed98 inputs or use a synthetic VL2 substitute.

One bounded host/Spike preparation pass is the next authorization to seek,
not a DUT launch: existing120s/5M-retirement preparation ceilings are suitable
initial stops, with no automatic retry/increase. Record actual reference
retirement and counts before selecting a VCS budget. M5's approximately
683..687 retired/s and 50.8..54.3min are context, not measurements of e16/m8;
use the slower archived273 retired/s admission estimate if resources differ.
No inherited180/300s timeout and no blanket eleven-program DUT batch.

If this prefix passes, next consider **e8_m8_ops1 first66 calls**, which changes
cap to1024 while reaching VL512/start256; require67584 fullcap checks +132
guards. Retain the remaining vi0/vi31/ei16 and beyond-prefix histories as open,
not equivalent PASSs. Do not schedule full2688-call children or the994-call
op1 parent prefix until reference cost and discriminatory need are reviewed.

If a later authorized run stalls, record last target/returned target separately
and then capture one bounded window: packed mask accepted words; gather
index/request FIFO push/pop; per-lane source-request handshakes; OOR/no-data
tokens; MaskB valid/ready; result commit/final grants and done. Count real
handshakes, not valid cycles. Preserve all preceding calls and original oracle;
finite scalar checking or transport timeout alone is not a liveness defect.

## Identity Anchors

Read-only SHA256 rechecks performed for this note:

```text
triage.json                  eb87f0ed9c07b3978e91e35ff5bcc0824388beb312510ba942ef061c0f63043f
P/manifest.json              6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58
P/parent_mapping.json        46b142c59ce1bf63e122355bba5ca03f86b8a0e63dc5237826f3afa68062c1d9
M5 prefix audit.json         e368d848ba691608b3349af5b7af73bd51c135b475dc756e5c04766ac43e23f8
M5 prefix complete.json      f957a2efbbda9857c95759ab70ef00886004ffa081bd4f6de8b3fc476920dd62
```

Individual report hashes and full original parent/assembly hashes remain in
`STALL_PARENT_PLAN.md`; all eleven referenced reports/ELFs/assembly/header
files were read again. This note reuses the completed independent M5 terminal
audit, rather than claiming a fresh raw-CSV re-audit or changing its status.
