# M9 Closed M-Mode Recovery

## Actual First Cause

Old output: `../unmasked_strided_alignment_soc_m9_worker_successor01/prepared01/`.
Its `firstfailure.json` names `strided_alignment_store_m`. Actual checker exit1 is
caused by `KeyError: 'tohost'` in sealed `check.py:142`, not by the helper-owner gate.
Both actual SoC specs have no HTIF symbol, correctly: this backend exits through CTRL.
The unconditional lookup was reached on the **first scalar BSS write**, CSV line23,
cycle173/order18/PC0x80000046/insn0x0002b023/address0x80001000/BEff/value0,
well before the vector target. The existing Spike bridge had a real `tohost` symbol
and could not expose this backend mismatch. This was a checker integration defect.

STORE child receipt: numeric0, 52.20824311673641 s, no timeout/failure/abort at return.
LOAD child receipt: numeric0, 52.6667539216578 s, no timeout/failure/abort at return.
Both actual consoles contain `STRIDED_ALIGNMENT_PASS`, real testbench SUCCESS and
normal `$finish`. STORE's checker failure set sticky abort; LOAD's later postcheck
was vetoed, and neither Sv39 member was dispatched. The original aggregate remains
`NOT_ACCEPTED_LATE_ABORT` with null adapter returncodes and `retries=0` unchanged.
The separate durable child receipts, not those null adapter fields, prove numeric0.

## Strict Correction

The new `Observer` inherits the original oracle and overrides only `step` for an
explicit endpoint recorder. A Host AST equality check proves the original step is
unchanged except the endpoint call and module qualification of original globals.
The seven-helper/nine-owner checker is inherited unchanged. No optional or fake
`tohost` symbol is inserted.

Both original ELF and spec must match original immutable plan hashes. The standard
ELF64 parser independently checks actual `replay_exit` and exit instructions:

- SoC: actual CTRL address construction at 0x80000068, store at **0x80000072**,
  instruction **0x00a2b023**, actual RVFI address **0xd0000000**, full8-byte write,
  data **0**, exactly once. Actual effective address, source GPR, byte enables and
  instruction/PC remain checked by the original scalar decoder/oracle.
- Spike: unique defined **actual ELF** `tohost` symbol, exact spec/hash binding,
  actual AUIPC/ADDI resolution and store instruction, HTIF value1 exactly once.
  CTRL is explicitly forbidden. These endpoint contracts are not interchangeable.

## Actual Offline Acceptance

`host.py` actual exit0 (tool receipt `9a2a17`): 62 negatives; both real SoC first-write
prefixes pass without adding symbols; eight backend/shape ELF bindings verified;
two already-existing Spike traces each read once for complete native-HTIF bridges,
including a full-trace missing-HTIF negative. No Spike execution or fabricated
CVX/backend events. Host bridge is not DUT lifecycle evidence.

`audit_closed.py` actual exit0 (tool receipt `2c1d53`, exec6984); durable audit receipt
`closed_audit01/audit_exit.json`. Each existing closed DUT CSV was fully parsed once,
unchanged, with raw log veto, actual command/private ELF/image, numeric child0,
existing frozen generic validator evidence, original full oracle and successor owner
checks. All **1253 pins** verified before and after.

| Member | CSV rows | Retired rows | Full checks | Memory/helper owners |
| --- | ---: | ---: | ---: | --- |
| load_m | 24090 | 23916 | 697 | 9 / 7 |
| store_m | 23873 | 23699 | 698 | 9 / 7 |

Both include precise alignment trap, prefix/poison, same-PC retry, successor owner,
complete results/guards/page-table checks, target vstart, all14 actual restore CSR
readbacks and exact real CTRL exit. Generic summary rows/retire/last-cycle match
the complete independent traversal. Final cycle: LOAD36021, STORE35417.

Independent status: **M_MODE_CLOSED_CSV_ACCEPTED_OLD_BATCH_NOT_ACCEPTED**.
This accepts only these two directed M-mode results. It does not relabel the old
batch, accept Sv39, establish a Linux-original closure, or claim a new RTL result.
No simulator, build, reference or original DUT was rerun; no sealed file or RTL changed.

## Pins

- Endpoint checker: `8d26dcfc02ee9e7a2cf5b6faa2d52ce0c725347c5d6adbefd1c5370a6f96b604`.
- Host result: `40ba4a9335a2a0d652cbc850892dd749008cfa507bdc0ed21de507726c0ce908`.
- Closed audit result: `fb29028a4ede5c7e07f1814cf6bba68d5c839ad65f4042729c32f25dd1844439`.
- Actual audit exit receipt: `0805b749874b9b060c3129c3f5829554a3c491154c0b486d9ea38a6e6d2865bc`.

Next scope is only the two previously undispatched Sv39 members, in a separate
new plan, same ELF/image/case budget. M-mode and accepted controls16 must not rerun.
