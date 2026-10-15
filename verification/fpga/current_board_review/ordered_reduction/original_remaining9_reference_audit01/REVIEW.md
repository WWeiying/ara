# Independent Remaining9 Full-Raw Reference Acceptance

**INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT.** No source, numerical, trace,
retirement-scope, pin or completion discrepancy found. This accepts nine
source-faithful ports of the archived reduced single-call reproducer, not nine
new roots, not nine full6720-call parents, not original Linux ELF execution,
and not SoC/RTL acceptance. No new Spike, Host test, build, DUT or live-service
query was performed by this audit.

## Bound Evidence

- Frozen executor READY SHA-256:
  `ad59b118f7b223b7deea74a04e43a63ff616705571748e01f0d18e1ce98d937c`.
- Frozen TERMINAL_CHECK SHA-256:
  `996e2ad07ecfcf3daadd52018791c590c129fa6e8610a999fa9310249ddba491`.
- Independent result.json SHA-256:
  `73d0ab599a46abe7aa4a871dab35d512de1ac98c055349a8eb732eab069fa781`.
- Independent reader audit.py SHA-256:
  `a6184fd9ab03161337931edb1de3f5b64b2c2fdcd1730b36cb554a87ac3ba01e`.

All741 unique source/evidence pins matched before and after parsing. They include
the prior independently inspected525-pin source/18-ELF set, each shape READY,
command/admission, raw, ledger, execution and sourceproof. All exact nine shape
members are present; nine per-case attempt sentinels and no STOPPED marker.
There is no inference of success from an aggregate status alone.

The independent reader does not import the executor checker. It reads existing
files, checks ELF instruction bytes, reconstructs integer/memory/CSR state,
initialization streams, helper windows and oracle reads, and compares the
entire independently reconstructed ledger (including every PC count) with the
retained ledger. All nine comparisons matched. It parsed all1,099,008,368 raw
bytes,16,925,000 commits; no sampling or rerunning reference. Offline work took
285.819 seconds, separate from recorded Spike execution times below.

## Exact Results

| Shape | Firmware to HTIF | Total raw commits | Post-HTIF park | Reference seconds | Raw bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| e16_mf2 | 1,860,457 | 1,865,000 | 4,538 | 3.024253 | 121,092,946 |
| e16_m1 | 1,864,672 | 1,865,000 | 323 | 3.024112 | 121,188,707 |
| e16_m2 | 1,873,154 | 1,875,000 | 1,841 | 3.024056 | 121,782,179 |
| e16_m4 | 1,890,113 | 1,895,000 | 4,882 | 3.024116 | 122,968,795 |
| e16_m8 | 1,924,035 | 1,925,000 | 960 | 3.124126 | 124,942,133 |
| e32_mf2 | 1,858,929 | 1,860,000 | 1,066 | 3.075488 | 120,860,143 |
| e32_m2 | 1,865,194 | 1,870,000 | 4,801 | 3.024535 | 121,402,821 |
| e32_m4 | 1,873,578 | 1,875,000 | 1,417 | 3.074286 | 121,794,079 |
| e32_m8 | 1,890,347 | 1,895,000 | 4,648 | 3.076651 | 122,976,565 |

Each row also has exactly five boot commits. Firmware total16,900,479 plus45
boot plus24,476 empty park commits equals16,925,000. Every row satisfies its
shape-specific static bound,3M debug-step ceiling,256MiB raw and120-second wall
limit, with numeric rc0/no execution error, actual HTIF1 and complete success
console. Total recorded reference execution time is27.471622 seconds. These
figures are not DUT performance measurements or an authorization to change
future DUT budgets.

## Instruction And Source Scope

- Canonical source remains campaign20261007 handoff03/redspecial02. The selected
  tuple is scenario3/l4/mode3/rm0/op0/sticky0, VL=cap/2 at VLEN1024. Sources,
  full fixture tables and both compiled ELF identities remain those independently
  inspected in `original_remaining9_static_review01/prepared_inspection01.json`.
  The original inner selector and surrounding scalar loops are not shortened.
- Each raw firmware PC/encoding matches its compiled ELF. Each op0 window is
  exactly21 consecutive original encodings, once each, matching that shape's
  archived scenario ELF. All42 instruction PCs in op1/op2 are forbidden, including
  non-vector interior instructions, not merely entries. A second check over
  both complete function address intervals also finds zero retired instructions
  for op1 and op2 in every independently matched PC ledger.
- Exact five-instruction Spike boot prefix is checked by PC/encoding/effects;
  no subsequent return to boot is accepted. All firmware CSR retirements belong
  to the seven ordered startup/vlenb prelude instructions or the original helper.
  All11 vector retirements per case belong to one capacity vset plus the ten
  original helper vector instructions. Extra vector/CSR PCs or unused helper
  interiors would fail the independent reader.
- In actual e16/m1 evidence capacity emits vtype8/VL64/vstart0, while the first
  helper vset emits only VL64/vstart0. Independent state inheritance handles
  this observed unchanged-vtype omission. This confirms the corrected checker
  path rather than treating missing CSR text as either a fault or a default.

## Full Data And Oracle Checks

Every case independently passes:

1. All8*cap input-element writes with exact source-derived values and addresses
   across all eight scenarios, all512 seed-element writes,215040 mask-byte writes
   and144 old-output writes. This includes post-target scalar initialization;
   selected setup is captured at helper entry, not from final RAM.
2. All3360 bank1 fixture rows, bits then flags, in exact address/value order:
   6720 field reads per case. Selected row1545/flattened4905 is confirmed by
   actual addresses, not merely NaN/NV values that may coincide across banks.
3. Entire fullcap input payload and load footprint, including all eight registers
   v8..v15 and1024 bytes at m8. All64 mask initialization bytes are checked;
   actual mask load is ceil(cap/8), before requested VL. e32 seed initialization
   is256 bytes, but the original m1 seed load is128 bytes; both boundaries hold.
4. Exact helper arguments, each capacity/fullcap/requested/final-m1 VL and vtype,
   full seed/old-destination vector loads, saved/requested CSR values and restore.
   Result is e16 `0x7e00` or e32 `0x7fc00000`, NV16 only, returned vstart0.
5. Complete128-byte destination store, all144 original byte comparisons, both
   eight-byte guards, and every unchanged destination tail byte (126 e16 or124
   e32). Total original oracle comparisons1296; total helper instructions189;
   total fixture-field checks60480.
6. Exact original cases1/errors0 marker and board PASS, no diagnostic/trap,
   restored frm/fflags/vstart zero through exit, real HTIF1 and only empty park
   afterward. This tests saved-zero frm/sticky0, not other rounding/sticky modes.

## Configuration And Limits

All nine actual commands, admissions and executions use exactly
**rv64gcv_zfh_zvfh_zvl1024b**, matching this batch's contract. There is no
minimum-versus-actual ISA delta to hide in this batch. The pinned golden Spike
binary and source/ELFs are unchanged. Static and actual instruction scans find
no scalar FP instructions; the relevant arithmetic is the original vector
ordered reduction.

Existing native Host117, preflight180 ledger/558 PC/27 boot tests and180
post-reference witness checks were read as evidence, not rerun. Their scope is
checker sensitivity, not additional architectural trials. In particular the
Host mode called bank0 is only a missing-NV mutation; wrong-bank address checking
comes from the raw checker, as disclosed in the earlier static supplement.

Per-shape JSON files retain actual target PC/ordinal, ELF/raw/ledger hashes,
counts and timing. The separate SoC ELFs are provenance-bound but were not
executed here. Original full6720-call history, Linux semantics, omitted
rounding/sticky variants and current production RTL remain outside acceptance.
