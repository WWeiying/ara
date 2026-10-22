# Unknown Gather Stall: One Archived Scene Recovery

2026-10-12, bounded read-only review. **The actual stopped tuple is NOT RECOVERABLE from this archive.** No new prefix, acceptance, reference, compile, simulation, RTL edit or live query is proposed/performed. Only this note is written.

## Selected Record

`rvv_permute_restart_e8_m4_ops3`, original Linux child, recovery168. Chosen because the11 `gather_operand_stream` entries have the same two-snapshot schema and NULL trial, but this record additionally preserves four actual preceding program exits and an earlier `board_report_live01.json`. This is a selection for information recovery, not a new test selection or a hypothesis that those predecessors caused the stall.

Roots:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `R=C/rvv_recovery08_168`
- `T=R/terminal_scene`

`C/stall_family_triage02/triage.json` identifies this row as `gather_operand_stream`, `opcode_family_candidate_no_trial`, `last_trial=null`; its ledger has no retest attempt for this child. Actual scene ELF and canonical `C/rvv_permute_partitions01/release/binaries/rvv_permute_restart_e8_m4_ops3` freshly hash to **a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b**. All20 entries in `T/hashes.json` verified without discrepancy.

## Recoverable Actual Facts

| Evidence | Actual information / limit |
| --- | --- |
| `T/batch_uart.bin` and `R/resume/batch.sh:47..62` | Same batch id255460613af189e686ddd6d8bc6a8f16: slots0..3 are ops8/9/10/11, each PASS2688/errors0 and END rc0; slot4 START is ops3, no END or final PASS. START is printed by the shell **before** invoking the ELF; not a target-accepted event. |
| `T/report.json` | Ops3 stalled; four preceding rc0 results belong to separate Linux programs, not ops3. No completed-call count for stalled ops3. |
| `R/resume/board_report_live01.json` | Earlier copy records ops3 running with the same preceding results and completed DETAIL lines. Despite its filename this is an archived file, not a queried live task. No new registers or tuple checkpoint. |
| Two `T/batch_progress_000{1,2}/snapshot.json` | Retired1955925713 unchanged; cycles12221031926 ->12789029119, delta567997193 =11.35994386s at recorded50MHz. Reported last_pc1063e/head_pc10642 remain unchanged. DDR outstanding/errors0; no DDR-counter progress. |
| Actual original ELF disassembly | PC1063e is308fbc57 `vrgather.vi v24,v8,31,v0.t`;10642 is00802573 `csrr a0,vstart`. Same13-instruction helper is reused for every tuple. Neither PC encodes seed/scalar/VL/mask/trial or proves a currently valid accepted request. |
| Snapshot mailbox/marker | All16 mailbox words0, marker0, resultffffffff/done0. These are unpopulated debug fields, **not** GPR values, seed0, scalar0 or a successful return. No VL/vstart/current CSR bank. |
| Snapshot trap fields | Historical last_trap_pcffffffff8001cc84, cause9/tval0, count291152 unchanged. These are trap-monitor metadata, not a contemporary CSR/GPR/stack dump for the stalled helper. |

Snapshots were captured2026-10-10T10:44:16.397357Z and10:44:27.671443Z, sequences5/6, ABI1/caps3; `watchdog_snapshot=false` and flags0. The paired observation establishes **no retirement over the sample interval**, not an internal MASKU cause or this program's retired instruction count. The absolute counter includes Linux/other work and cannot locate an original call ordinal.

## UART: Useful Lower-Level Progress, Not the Stopped Target

Raw UART is2415bytes. The report keeps **nine complete DETAIL lines**; the original raw bytes also retain an unfinished tenth line:

```text
RVV_PERMUTE_DETAIL op=3 seed=0 scalar=0 vl=256 mask=0 element=4 vstart=128 expected=91 
```

The latest complete lines describe the same source tuple, elements0..3, expected91/actual177. Original retained C `C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c` puts DETAIL inside the scalar oracle **after** `functions[op](...)` returned. This establishes a prior returned-call numerical-error tuple **seed0/op3/scalar0/VL256/mask0/vstart128** and progress into that oracle; it does not prove all its oracle/guards/statistics completed, any following tuple, or the currently stalled invocation. The partial line has no actual value or newline and must not be promoted into another complete mismatch.

The archived observer (`R/resume/guest_watch.py:44`) feeds only newline-completed lines, explaining the lost JSON suffix. No per-call TRIAL/BEGIN/END exists for ops3; original TRIAL printing is conditional on op0. The20-error print ceiling is not a call counter; nine complete lines plus one fragment do not identify the terminal call. UART timing is not tied to an accepted hardware instruction tag.

Under the previously intended VLEN1024/cap512 shape, that **returned** tuple maps to source call66 (length slot4/mode0/trial1). This is a configuration-based source-order mapping, **not the stopped tuple**; this snapshot itself contains no measured vlenb/capacity. Do not label current stall as call66, call67, a later guessed boundary or VL512/start256. Recoverable provenance of four earlier processes is likewise not proof of preserved Linux vector/context state at ops3 entry. `R/previous_report.json` ends with ops7 stalled, but recovery metadata is an unchanged-bitstream restart: that administrative predecessor is not an additional in-process predecessor.

## Why No Hidden State Can Complete the Tuple

The selected recovery directory has412 files; state/dump filename inventory finds only the two JSON/CSV snapshots. Scene console.log is empty. No GPR/CSR/VRF/stack/coredump, process maps or retirement/accepted-request trace was found in this selected scene and its resume/debug artifacts. Both `debug/transport.jsonl` files contain only **busD** debug-bank operations, not busM DDR/process-memory reads. They read identity/live, core bank100, DDR banks180/200 and mailbox40..7c; the write is debug snapshot control, not a saved CPU context.

This is corroborated by the **hash-matched historical collector** now retained at `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/software/host_load.py:62`: its snapshot is exactly eight64bit core fields plus DDR/live/mailbox, with sequence validation; `fpga_debug.h:39` defines the same layout. Their hashes match the snapshot report's host provenance, so absence is not merely a JSON summarizer dropping a saved register bank.

The Linux ELF is stripped, with `.eh_frame` but no symbol/DWARF register-variable locations; `.eh_frame` is an unwind recipe, not captured stack contents, and `.bss` is NOBITS, not live a/indices/predicate/output. Initramfs/rootfs/firmware images in R are boot inputs, not process RAM/VRF dumps. A filename `scene_preserved` means the observer avoided reset at capture time, not that architectural state was exported.

The inspected `rvv_stall_handoff*/index.json` entries are five FP-move contexts and **e16/m1 ops16 slide**. The latter has explicit measured tuple in instrumented trace/single, but its README explicitly leaves the original uninstrumented trigger unknown. Different ELF/opcode/shape and instrumentation: it supplies no missing Gather11 tuple and cannot be used to close this record.

## Precisely Missing / Minimum Future Evidence

| Missing evidence | What it would permit |
| --- | --- |
| Original call ordinal plus seed/op/scalar-slot/length-slot/mode/trial, before/after phase tied to program/run identity | Unique intra-child predecessor position. Do not collapse duplicate trials or scalar slots merely because values coincide. |
| Actual GPR a0..a7/t3 plus relevant caller saved registers, SP/RA and stack bytes if loop state is spilled; matching ELF/process address map | VL, capacity, scalar/start arguments and exact loop counters, instead of interpreting unrelated total retirement. |
| Contemporary vlenb/VL/vtype/vstart and v0/source/destination VRF or corresponding live arrays | Confirm actual shape/window and predicate/source state. Last-trap metadata and zero mailbox cannot substitute. |
| Valid&&ready acceptance with instruction id and op/VL/vstart/vm/scalar, matched response/completion and retire/CSR phase | Distinguish pre-call/setup, accepted target, queued/waiting CSR, completed helper and later oracle. A before-print alone is insufficient. |

For any separately authorized future reproduction, the lowest useful capture is a durable original-call sequence/tuple/phase record **plus matched actual acceptance/completion evidence**, preserving the original predecessor order, complete oracle and continue-after-numerical-error behavior. Instrumentation timing and Linux/context differences must be disclosed. If using a halted register/stack route instead, it must include the context and saved-loop data above; raw PC alone still cannot select a tuple. This note authorizes none of those captures or any replay.

**Stop blind prefix selection:** existing prefix PASSes cover their stated prefixes only. This archive cannot tell which later tuple to select, cannot prove a new RTL defect, and closes none of the11 unknown original stalls. No further sweep of all11 is needed to state this selected record's limitation.

## Key Evidence Hashes

| C-relative path | SHA256 |
| --- | --- |
| stall_family_triage02/triage.json | eb87f0ed9c07b3978e91e35ff5bcc0824388beb312510ba942ef061c0f63043f |
| stall_family_triage02/ledger.json | 3aa890a18addcf256e6af586bea00f4665bb2624e283f8eb392fd642eb5e9063 |
| rvv_recovery08_168/terminal_scene/report.json | 0908961a67b3b26f032efdd264869205f0b1930b46eb72eac5aaf714ff4266a1 |
| rvv_recovery08_168/terminal_scene/batch_uart.bin | 87813cbfaba425d942c400b96eeffcf1a8865a1473955994e2d0ffbc88de64e1 |
| rvv_recovery08_168/terminal_scene/batch_progress_0001/snapshot.json | fef0f1ddac3972b15c0e6c3576177bc129f2623e0c1d9dd1a8500fb86476a0fc |
| rvv_recovery08_168/terminal_scene/batch_progress_0002/snapshot.json | ae6e097757e967bff1a5db6f38b74852055ae627be120091e148d721b3d2ade8 |
| rvv_recovery08_168/resume/board_report_live01.json | 1e5a2d1b7c11800d5122e07d981c319da8ee67f1c908a640079aeec59032769f |
| rvv_recovery08_168/resume/guest_watch.py | 4d34f1b5f5382223f41666892f62fba5e6ae0a2d1b5b4bcc822b021fee276bd0 |

Matching snapshot collector SHA d7276f9aad22b2fa5e7efde85538102811c07ae647fa794adb696b0a9d67aa9b; debug header SHA eb12cfc1d9790f247cc1cdfe6c86acb908a503f479b3071256f9b2dfdb6e6054.
