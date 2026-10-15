# Pilot First Failure, Read-Only Analysis

Status: **MEASURED_FIRMWARE_FAIL_NOT_CHECKER_FAILURE**. Pilot
`d32m2_i64_fault_ov1` failed in 628.6328329639509 s; recorded return code 255.
The runner stopped on the raw firmware mismatch marker. This is not a timeout,
nor a post-processing checker rejection. Return code 255 is not evidence of a
natural successful CTRL exit. Both controls remained NOT_RUN.

Only new analysis artifacts in this directory were written. No DUT rerun,
RTL change, timeout change, or sealed-input/log modification was performed.
No historical service-exit state is inferred from a collected unit.

## Architectural Ledger

`ledger.json` reconstructs the original CSV, including scalar checks, all trap
CSR reads, PTE writes, SFENCE/MRET, target CVX transactions, and source logs.
`first_error.json` summarizes the first counterexample and binds the evidence.

| Event | CSV cycle | Evidence |
| --- | ---: | --- |
| Original gather32 helper entry | 357344 | Args: indices=0x80002018, VA=0x40000000, output=0x8000211c, overlap=1 |
| Sole index-load request | 357354 | Opcode 02057207; no index reload between retries |
| Target attempt 0 request/exception response | 357496 | Opcode 0645f207, original target PC 0x80000d64; vstart=0, mtval=0x40007000 |
| Target attempt 15 request/exception response | 367076 | vstart=15, mtval=0x4000a000; repair and MRET complete |
| Target attempt 16 request/exception response | 367681 | First bad exception address, vstart=16 |
| Handler reads bad mtval | 367806 | Actual 0x0000400040017000 |
| First unequal check call | 368106 | CSV line 299437; check ordinal 160; expected 0x40017000 |
| replay_mismatch entry | 368145 | CSV line 299453; PC 0x80000f04; same values as console |

These are accepted CVX front-interface transactions, not the earlier backend
issue time. There are 17 requests and 17 exception responses, not 17 successful
vector retirements. All faults retain mepc=0x80000d64, mcause=13, vl=32,
vtype=0x11, fcsr=0x75, vcsr=5. Vstart advances 0 through 16. The first 16
handlers each complete PTE repair, addressed SFENCE, and MRET. The seventeenth
fails before PTE repair/MRET. No round checkpoint is reached.

The console's `index=0xa0` is **check ordinal 160**, not vector element 160.
Final observed scalar state is io_errors=1, io_checks=160, io_round=0,
io_minor=16, io_maps=1, io_unmaps=0. Last CSV cycle is 370929 with 300626 scalar
retirements. This does not accept a round, the 50-round pilot, or either control.

## Exact Check and Source

The private ELF matches reference03 `d32m2_i64_fault_ov1/soc.elf`:
`5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`.
Original source, assembly, Linux ELF, SoC ELF, fixture, disassembly, and raw
inputs are bound in the evidence files. This is reference03's bytewise opcode
reader, not reference02's misaligned 32-bit handler read.

`io_trap()` checks `tval == VA + indices[vstart]`. Disassembly at 0x80000738
loads indices[vstart], 0x80000742 adds VA, and 0x80000744 calls check with
return PC 0x80000748. The observed failed check and diagnostic arguments agree
with this code and with the raw console marker. The host strict acceptance
checker was never invoked after a pilot PASS because no pilot PASS occurred.

At helper entry all 32 initialized indices equal `((i * 13 + 7) % 32) * 4096`.
For the failing element, indices[16]=0x17000 and indices[17]=0x4000:

```text
expected mtval = 0x40000000 + 0x17000 = 0x40017000
actual offset = 0x0000400040017000 - 0x40000000
              = (indices[17] << 32) | indices[16]
```

This is a discriminating 32-bit-packing/64-bit-index interpretation clue,
**not yet a proven RTL root cause**. In particular it does not identify which
retry descriptor, EEW metadata, shuffle, or downstream operand stage first
changes the interpretation.

## Source Snapshot and Wave Scope

All 32 `ARA_SOURCE_CAPTURE` events match the initialized source, using global
element `4 * snapshot_word + lane`. The frozen lane logging condition is also
the snapshot-buffer write condition. Element16/lane0/word4 is 0x17000 and
element17/lane1/word4 is 0x4000. There are only eight `ARA_SOURCE_REPLAY` log
events, for words0/1 across four lanes, all correct. The replay log is a replay
valid observation, not independently a downstream AddrGen-consumption proof.
It cannot establish correct delivery of all 32 indices or failing element16.

The complete original FSDB header reports **100fs** units, status finished,
and maximum tick 3709495000, or **370949.5ns**. Source log time 3574300000 is
357430ns, not 3574300000ns. Consequently the planned 1000000ns dump-disable
point was never reached; its console closure marker is absent. The existing
wave temporally covers the observed target/fault chain and mismatch. This is
**failure-truncated before checkpoint, not a temporal profile miss**. It does
not cover 32 faults or a complete first round, because execution failed early.

`wave_metadata.json` binds the full FSDB, summary, tool, and successful offline
357000..369000ns compact VCD conversion. No new simulation was used. The earlier
stopped un-compacted export and unmatched-scope empty export are explicitly
excluded; neither is evidence of a DUT failure. The compact wave is available
for further descriptor/EEW/AddrGen analysis, but this report makes no such
wave-derived root-cause claim.

The fixture intentionally requires 32 faults per round, 1600 over 50 rounds.
This is not the original Linux minor-fault count of 150 and does not establish
Linux replay acceptance.
