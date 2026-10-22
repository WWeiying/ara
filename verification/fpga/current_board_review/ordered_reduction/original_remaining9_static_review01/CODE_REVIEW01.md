# Generic Remaining9 Initial Code Review

Decision: **HOLD this checker revision before reference**. Two concrete false
failure paths were found and sent to Tesla, who is preparing corrections.
This document records the reviewed revision, not approval of later edits.
Only source, ELF bytes, retained Host outputs, disassembly, and old reference
evidence were read. No new Host/Spike/DUT/compile or live query was performed.

## Findings

### P1: Boot ROM CSR Is Rejected Before Firmware

`original_remaining9_prepare01/check_reference.py:100-101`, SHA
`4c0c8692d8bbce10e6c8926dc3573a0dba468b2debf1bf1fcc20951e81e8bc53`:
the extra-CSR check applies to every raw PC, including Spike's boot ROM.
The already accepted e16/mf4 raw's third record is:

```text
core   0: 3 0x0000000000001008 (0xf1402573) x10 0x0000000000000000
```

This `csrr a0,mhartid` is neither a firmware prelude PC nor an op_0 PC, so the
new checker raises `extra CSR retirement`. Every normal reference with this
same Spike boot sequence would fail extraction before its first firmware
instruction. This is a checker defect, not an architectural or RTL failure.
Separate and bind the exact boot prefix; do not weaken firmware CSR ownership.
Tesla acknowledged the issue before reference and plans boot-prefix tests.

### P1: e16/m1 Loses The Incoming vtype State

Same checker, lines199-202 initializes `vt=None` and only considers CSR updates
inside the helper. Its capacity extraction at lines102-108 retains PC/ordinal
but discards capacity's CSR state. For e16/m1, capacity already sets vtype8.
Helper instruction0 sets the same m1 type, so Spike does not emit a vtype write.
`None` persists and `vt==8` fails even for a correct trace.

This is established by `riscv/vector_unit.cc:33-49`, which writes vtype only
when the new value differs; the existing e16/mf4 raw at PC0x80000750 also
demonstrates an omitted unchanged vtype write. Initialize helper state from
the actually observed, validated capacity CSR state, not an assumed expected
constant. Add a positive same-type/no-write witness and missing/wrong incoming
state negatives. No new reference is needed to establish this static defect.

### Dispatch Boundary Needs Parent Clarification

The inspected `reference.py` SHA
`69ad5fd9b72f4eec302ddea6fbad214d4855f21edf50ab0b416107dd60e1d70d`
has jobs1 but `run()` dispatches all nine sequentially, without a first-two
boundary. If the parent's "small batch2" means stop after the first two for
review, this entry point does not implement that condition. If it means only
at most two concurrent, jobs1 satisfies it. This is an authorization-boundary
question, not a numerical bug; it was sent to Tesla for coordination.

## Source And Two-SEW Review

`prepared_inspection01.json` is an independent offline read of525 input/evidence
pins across all nine shapes. SHA:
`d0965d992eb0b74f62388385402704b1b6ee7fee825a08252ca2f1acea923699`.

- All nine sourceproof/configs match the intended membership. All source main
  bodies retain the original loops and selector after exit-to-return adaptation.
  All per-shape fixture headers match the complete archived JSON tables.
- All18 compiled ELF disassemblies match their actual ELF bytes, and all three
  21-instruction helper windows per ELF match each shape's archived scenario ELF.
  Existing13 Host outcomes per shape have consistent setup/PASS/failure logs;
  these were not rerun and are not reference acceptance.
- Checker tracks512*w input storage,64*w seed storage,64 mask bytes,144 output
  bytes. It checks8*cap input writes and512 seed writes in per-array value/address
  order, plus215040 mask writes and6720 ordered fixture-field loads, including
  post-target scenarios. Its setup snapshot is at the helper entry, not final RAM.
- The fullcap vector payload concatenates every required register, including
  v8..v15 for m8. e16/m8 cap512 needs exactly1024 input bytes and64 mask-load
  bytes; e32/m8 uses1024 input bytes and32 mask-load bytes. Fractional LMUL checks
  only the architecturally defined loaded prefix, without demanding undefined tails.
- e32 correctly initializes256 seed bytes but loads only128 bytes into m1.
  Its result is four bytes `00 00 c0 7f` with124 unchanged destination bytes;
  e16 is `00 7e` with126 unchanged destination bytes. Both retain16 guard bytes
  and all144 original scalar checks; final store width and count are parameterized.
- Returned flags/vstart, saved-zero CSR values, restore, contiguous helper order,
  full store footprint, exact console and real HTIF are checked. Wrong-bank raw
  mutation changes the actual address even if bank0 has the same NaN/NV value.
  Host13's mode named `bank0` merely sets status0 and duplicates missing-NV for
  larger shapes; it must not be described as a genuine wrong-bank test. The
  separate address-based raw negative covers the intended distinction.

## Cost Review

All nine compiled main bodies contain one memcpy callsite, the32-byte seed
copy; no input-scenario memcpy callsite exists. The matched seed body has12
instructions plus memcpy(32) at7*n+3:512*(12+227)=122368. Both e16 SH and e32 SW
seed/input stores are present. The mask body has the same six/eight-instruction
branches and64-byte bound, giving1,612,800 instructions across all fills.

The input switches include out-of-line cases after the first scalar loop,
with backward branches into its store/backedge; those paths must remain in
cost reasoning. The inspected e32/m8 example places these at0x8000046a..4b2,
returning to0x800003ee/3f2. They have no unbounded internal loop or extra call.
The allowance872*cap includes more than the actual simple/complex paths, even
charging hypothetical24-byte copies for scenarios4/5. Combined with336000 for
fixture/selector/outer control, complete oracle/printing,8000 startup and20000
setup slack, the finite normal-path envelopes are:

| Shape | Static upper |
| --- | ---: |
| e16_mf2 | 2,143,584 |
| e16_m1 | 2,171,488 |
| e16_m2 | 2,227,296 |
| e16_m4 | 2,338,912 |
| e16_m8 | 2,562,144 |
| e32_mf2 | 2,129,632 |
| e32_m2 | 2,171,488 |
| e32_m4 | 2,227,296 |
| e32_m8 | 2,338,912 |

These support the fixed3M instruction allowance, conditional on corrected
checker/dispatch gates; they are not measured counts. The static-cost script
matches mask/seed/memcpy instruction shapes but does not mechanically prove
every other CFG charge: the remaining conservative allocations are reviewed
engineering bounds on these pinned finite programs, not a general WCET tool.
256MiB and120s stay independent fail-closed limits. Do not retry or shorten
loops on a bound hit. Actual ISA is consistently Zfh+Zvfh in current configs.

## Snapshot Identity And Pending Work

- common.py: `d435b1661fec3c6d95e9d328dc45ff0066df9096e2697848d0889929294cd3fe`
- prepare.py: `38641de516d429562a7cdffc38b41645323b901178acb57e90c0d0de01fead3f`
- host.c: `95ba3b0f3d99c4c707ef0a54bd29bb16c8594c775b63590504343ff8b3298371`
- static_cost.py: `7b3d999dcac21efbf8a18f8b001ef238f459d8fff134aa85ebc3eb52af3f930b`
- manifest.json: `c7757c1ad1db3b308a43235f1282bc6f8d3e184152b65a80329faebdf7eb2979`
- static_admission.json: `c23f6b29d700ab48adc134eb4d8561445716e86e93233e221b69149c2fe1ebdc`
- Spike vector_unit.cc: `ab45b3556c3fed6134727b0b9111a18fbc9ab4a6a743a4fd7cac492d67df3723`

Await corrected frozen checker, its boot and m1-state host evidence, and explicit
batch dispatch scope before clearing reference preparation. Existing evidence
and the initial refusal remain intact. This review does not approve unseen
successor code or authorize DUT execution.
