# Original e64 Scenario0 / Scenario3 Successor

Software/reference preparation only. No DUT launcher is included.

The source is `ara_hw_campaign_20261007_01/rvv_small_exceptions01`:

| Single | Original helper | Base | Predicate | Immediate returned VL/start | Defined final output |
|---|---|---|---|---|---|
| e64/sc0 | load_1, vle64ff.v | P-32 | ff | 4/0 | out[1..4] = 11,48,85,122 |
| e64/sc3 | load_0, vle64.v | P | 00 | 8/0 | out[1..8] = scalar 0x5b |

Only sc0 final out[5..8] is undefined by the original oracle. All 130
output elements are initialized and checked before the target; all other
final output elements, original guards out[0]/out[9], and all 16 mask bytes
remain strict. The original helper restores VL8 before storing all eight
vector elements, so completion-ecall VL8 is distinct from sc0 target VL4.

Original C/assembly/ELF identities and archive failure PC are checked against
the manifest and symptom ledger. The sole archived C delta from canonical
exception_oracle.c must be its single-round/single-scenario loop selection.
Both 11-instruction helpers and the three-instruction capacity helper retain
the archived ELF encodings; execution of every unused-helper PC is forbidden.

This is a source-derived S-mode Sv39 port, not execution of the Linux ELF or
proof of Linux clone/wait/signal semantics. A real invalid second-page leaf
replaces PROT_NONE. Neither target may cause an architectural trap; the one
permitted handler is the later completion S-ecall. Complete 8KiB data, 12KiB
page tables, surrounding guards, saved/restored CSRs and 14 restoration
readbacks supplement the original oracle. No MMU/AXI-zero claim follows from
an architectural no-fault result alone.

Reuse: independent copies of the accepted e64 suffix fixture/checker template,
with scenario/base/predicate/VL/defined-tail parameters changed; the existing
sc1/2 inputs are not modified. Common disassembly/ELF utilities remain shared.
The DUT entry is `source_owners.analyze(csv, soc_spec)`, preserving the complete
scalar oracle and actual RVFI addresses/byte enables/data. It requires four
nonempty memory owners, including old-vd load, mask load and result store,
actual VID/request/response/done ownership, and source-bound FOF context.
Unknown GPRs are not initialized to assumed reset zeros. Generic trace
validation, actual numeric child exit, command/image pins and console veto
must additionally remain mandatory in any later worker.

Preparation commands (exclusive outputs, no automatic retry):

```sh
python3 -B prepare.py build
python3 -B prepare.py host
python3 -B prepare.py reference --scenario 0
python3 -B prepare.py reference --scenario 3
python3 -B finalize.py
```

Each reference uses `rv64gcv_zfh_zvfh_zvl1024b`, real S-mode, 800,000
instruction bound, 120 seconds and 256MiB trace-size limit. One attempt per
final ELF. Independent entry review is required after READY; no DUT is
launched by these commands. This does not repeat e8/sc0, e64/sc5 or sc1/2.
