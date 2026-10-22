# M6 Fault-Overlap Pilot Independent Acceptance

Verdict: **PILOT_FULL50_SV39_REFERENCE03_INDEPENDENTLY_ACCEPTED**.
Only `d32m2_i64_fault_ov1` is accepted here. Controls2 and the complete three-case
worker/service exit were not inspected or accepted. No DUT launch or campaign
poll; no original or sealed artifacts were modified.

## Recomputed Raw Evidence

The frozen `repair06_worker/checker.py::analyze` was invoked directly on the
completed pilot's raw `commit_trace.csv` and reference03 symbols/disassembly.
It took52.64s. Independent `recomputed_indexed_analysis.json` matches the
original analysis structurally **and byte-for-byte**:
`d4628ddfdb8d9a40cf2b55f6b0cbb83d9d0444550e0df92b42f35837969b39a1`.
Raw CSV SHA: `47faec1b29967ba5cd7083463b16ebf5a5f2c6c6e9d2cce07556ecf29e816ae5`.

| Checked Quantity | Actual |
| --- | --- |
| Complete rounds / original helper calls | 50 |
| Complete32-value outputs / two guards per round | 1600 / 100 |
| Original firmware check calls | 21595 |
| Accepted original targets | 1650 |
| Fault responses / correct CSR records / repairs / MRET retries | 1600 each |
| Successful target retirements / accepted-and-retired reloads | 50 each |
| Trapped-target retirements | 0; fault acceptance is counted from exception responses, not invented retirements |
| Actual final backing / PTE scalar reads | 32768 / 1536 |
| Architectural retirements / last CSV cycle | 1587848 / 2253376 |

The checker reconstructs actual scalar stores/loads, all32 outputs and guards,
original setup/prologue and target encodings, per-fault CSR/PTE records,
addressed SFENCE, unchanged scalar context/PC, real MRET and same-PC retry
without reloading/reconstructing vector state. Missing memory bytes fail closed.
It verifies50 per-round fault counts32, terminal counter/magic, errors0,
CTRL0 exit and only the permitted side-effect-free parking after exit.

## Execution And Identity

Raw runner is `COMPLETE`, exact membership `{PASS:1}`, simulator rc0,
elapsed3059.0834649s within4200s. Both raw logs have exactly the original full
oracle markers, normal simulator exit, and no failure-veto marker. Closure is
one standalone actual marker line per log, distinct from the UCLI command echo.
Private input, source path, actual command, captured profile and image ledger
match the frozen plan; generic trace summary is VALID.

All737 plan pins were verified before and after recomputation;751 combined
inputs/evidence pins are retained in `audit.json`. Original pilot file hashes
were unchanged throughout. Actual ELF symbols/disassembly and all41 original
helper encodings were independently checked through the sealed reference gate.
Same M5/M6 SoC ELF SHA:
`5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`.
Authentic original Linux ELF SHA:
`07b1438fbea419215576f071fd5e89c38f01238ab19fbc564ad861faf738e03d`.
They are distinct programs/backends; the executed ELF is the reference03 Sv39
source fixture, not the original Linux ELF or its minor-fault scheduling.

M6 plan: `d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8`.
Image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Snapshot: `3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.

## Causal Closure And Scope

Earlier independent bounded-wave evidence is bound to this same private ELF.
Source conversion completes before capture; after destination EW32 conversion,
saved EW64 replay supplies index16=`0x17000`, actual MMU VA and mtval40017000,
correct vstart16, and all nine handler checks. Old M5's400040017000 is absent.
Full50 raw-CSV/oracle acceptance now complements that cycle-level causal result.
It does not expand the sampled wave window or claim all old-vd values were
captured; BE evidence applies to the measured element15 data write only.

The initial owned-auditor substring-count error and its narrow fix are retained
in `INITIAL_AUDIT_NOTE.md`; no simulator was rerun and no gate was weakened.
