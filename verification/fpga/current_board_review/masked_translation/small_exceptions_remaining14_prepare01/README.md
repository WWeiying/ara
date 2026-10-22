# Remaining Fourteen Original Small Exceptions

Preparation/reference only. No DUT launcher, image build, or RTL edit.
Frozen execution image binding: M9 image SHA256
`48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.
This does not relabel the current worktree as M9.

## Exact Scope

Members: e8 scenarios 1/2/3/5; e16 and e32 scenarios 0/1/2/3/5.
Each is one genuine archived round0 single from
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_exceptions01`.
The archive manifest and measured symptom ledger bind each original ELF,
C/S hashes, original target PC, cause13/address/tval and original geometry.
No e8/sc0, e64 member, scenario4, or arbitrary new tuple is included.

| Scenario | Original helper | Original predicate byte0 | Source base relative to boundary P | Immediate VL | Result contract |
| --- | --- | --- | --- | --- | --- |
| 0 | load_1, masked FOF | ff | P - 4 * element bytes | 4 | First four 11/48/85/122; only final out[5..8] undefined by original source |
| 1 | load_0, masked unit | 0f | P - 4 * element bytes | 8 | Four data, four typed91 |
| 2 | load_1, masked FOF | 0f | P - 4 * element bytes | 8 | Four data, four typed91 |
| 3 | load_0, masked unit | 00 | P | 8 | All eight typed91 |
| 5 | load_1, masked FOF | 00 | P | 8 | All eight typed91 |

All targets use original VL8/m1/tu/mu, returned vstart0, original eleven
helper instructions and three capacity instructions. Both helpers' encodings
are compared with each archived ELF; execution of unused helper PCs is
forbidden. Unused helper presence is not an extra invocation. Every member
retains the original single-call oracle; no warmup or matrix reduction occurs.
The single C differs from canonical exception_oracle.c only in its archived
round/scenario loop selection. Adapted SoC/Spike ELFs are not claimed identical
to Linux binaries or equivalent to Linux clone/wait/signal behavior.

## Shared Implementation

One `fixture.c/.h/.S`, observer and checker serve all fourteen members, selected
by SEW/SCENARIO at compile time. Original source helpers are copied unchanged
into each private software directory. Data/PTE expected bytes are independently
constructed by Python, including narrow-width little-endian packing, and
compared against the Host C oracle and actual Spike writes/checkpoints.

Each fixture checks all 130 typed output slots before the target and all
defined slots afterward, original guards0/9, sixteen mask bytes, complete
8KiB data plus 12KiB page tables and both external guards. Only sc0's original
four undefined result slots are omitted in its final phase; no other mask,
tail, memory, CSR or target-fault exemption is added. The original helper
stores all eight vector elements after restoring VL8, even for sc0 VL4.

True S-mode Sv39 uses an invalid second-page leaf in place of Linux PROT_NONE.
No target may cause an architectural trap. The sole handler is the later
completion S-ecall; saved/restored CSRs, immediate returned VL/start and
post-helper VL8 remain distinct. Exact underlying Linux permission encoding
and zero physical/MMU request traffic are not asserted by architectural PASS.

SoC exit is the actual ELF CTRL0 store at 0xd0000000, not an optional `tohost`
symbol. Spike has its own real HTIF1 exit and original pure parking code.
`source_owners.py` requires four nonempty source-bound memory lifecycles,
including the alloff target, not merely balanced totals. `abi_check.py`
inherits the data/owner checks and applies Aquinas' actual-first-spill method:
exact compiled main prologue, actual startup SP/frame, twelve first callee
spills; exact completion ecall followed by the handler's seventeen-entry
instructions and sixteen matching restore loads. Only the five approved
otherwise-unknown temporaries may enter at their exact first handler spills.
No global default-zero GPR model or unknown business-store exemption exists.

Every new SoC profile is extracted from that ELF and checked against actual
file bytes, not copied e64 PCs. Host negatives use those real specs with
synthetic RVFI rows; they do not constitute an observed DUT decoder run.

## Commands And Bounds

`prepare.py build`, then `prepare.py host`, followed by exactly one
`prepare.py reference --sew N --scenario S` per member and `prepare.py finalize`.
Outputs are exclusive; a failed reference is preserved and not retried.
Each reference has 800000 records, 120 seconds and 256MiB raw bounds, ISA
`rv64gcv_zfh_zvfh_zvl1024b`. Actual Spike wait and separate parser wait receipts
are mandatory; nested exit0 is not inferred from a parent log.

Future DUT budget remains at most 1800 seconds per case; eventual jobs8 is
not a launch authorization. Actual reference cost and measured comparator
timing must be reviewed before the separate runner is admitted. No timeout
increase or oracle shrink is automatic.

Diagnostic receipts retain first failing case, exception type/message,
current row/cycle/event/PC/encoding where available, stage and short traceback.
Final batch abort must not overwrite the first concrete checker failure.

See `READY.json`, `input_pins.json`, `software01/*/source_proof.json`,
`reference01/*/{status.json,spike_exit.json,parser.log.execution.json}` and
`REPORT.md` for measured preparation results once finalized.
