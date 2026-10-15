# e64/m4 Exact One-Reference Entry Review

Verdict: **NO_BLOCKER_ONE_BOUNDED_REFERENCE_ENTRY_NOT_DUT** for entry SHA
41b945d40245cbb661d0ff8b014250e155d80c790eb0e97b32a274c974de72a2.
Under the parent's existing conditional authorization, Tesla alone may execute
this one reference after binding reference_entry.json and its SHA. No further
parent approval cycle is needed. No VCS/DUT authorization is provided.

## Exact Scope and Limits

The frozen software02 Spike ELF is
42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae;
the separate SoC ELF is
7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620.
Full original5985/35ops/3seeds/CAP64/vtype26/physical4/history is retained:
383040 results,11970 guards,5985 returned-vstart checks,77805 helper
instructions,395010 actual LD,395010 expected LD,53865 ID LHU and395010
equal BEQ. This is not a prefix, current-image PASS or historical Linux closure.

Exact execution: rv64gcv_zvl1024b,-m2,rs4000000 then quit;120s,768MiB raw,
offline600s,actual firmware through HTIF<=3M. A completed reference over3M
produces HOLD, not READY. The static upper2863981 is not measured retirement.
Fresh reference01 creation prevents a second execute attempt. Actual child
numeric wait is persisted before interpretation; offline parser has its own
numeric wait receipt. Pins are checked before/after; closed raw SHA/stat are
checked around the single semantic parse. Failure is retained without retry.
No command in this review executed reference, Host, compiler or VCS.

## Actual Observer Gates

- context binds this shape's full gold bytes,1986-block dictionary,original
  call ledger/seed arrays and640 exact-bit FP table. Per-row input/output hashes
  are checked; no host floating-point oracle or explicit fflags claim is added.
- Helper windows are the actual original13 instructions, with exact call
  arguments, VL/vtype/vstart, t3=7, one capacity window and RNE bootstrap.
  Extra/interior/out-of-order helper retirement is rejected. Inputs/oldvd and
  output are checked across four128B physical registers, not a fractional or
  two-register surrogate. Full scalar result storage and both64-bit guards
  remain mandatory. The full backing arrays are checked against known BSS.
- Each comparator follows its actual all-equal linked PC path. Each call
  requires nine ID reads at row stride18 and offsets0..16, and66 ordered
  actual/expected LD pairs. Addresses, widths and values are source-bound;
  the ninth block reads only offsets0/8. Each BEQ requires actual input
  register equality and flag0; the real initial-zero instruction is counted
  each call. Completion requires66+66 reads,nine IDs and final sticky0.
- Each FP call requires its real seed-slot read,eight table LD and128 ordered
  a/b SD, including VL0 and repeated values. Seed-specific paths and original
  552 RNG/override stores preserve cross-seed history. Full totals241920 FP
  SD/15120 FP table LD/1890 FP calls are required.
- Mask groups require16 clear SD before original selected LBU/ORI/SB,
  including cumulative values and matching pending loads. Full totals35280
  clear stores/77175 selected stores/2205 groups are required. No final-mask
  copy or aggregate-only substitute is allowed.
- The raw boundary checks exact five reset-ROM retirements, actual firmware
  entry and PC/code, software return0, HTIF value1 at8000007a/00a2b023,
  full counters and exact console. After HTIF only8000007e/a001 with no side
  effects is allowed through EOF. Whole raw steps remain bounded by4M.
  SoC has no tohost; its separate derived spec does not pretend to have used
  this Spike exit transport. Future DUT observer/transport needs separate review.

## Preserved Checker Correction and Host Evidence

Host01 actual rc1/1.1683934079483151s is a genuine checker event-order defect,
not a reference or DUT failure and not a PASS. Its old lifecycle/log/receipt
remain pinned. enter previously tested mask completion before the final SB
effect. Corrected delivery is enter -> store/read/register effects -> leave.
The unchanged completeness predicates now run after that same final effect,
with exact closing-PC validation. Missing final effects still reject.

Host02 retains19 tests,actual rc0/1.1682375739328563s. Host03 retains all19
plus seven final-instruction phase tests,actual rc0/1.2774355690926313s,
PID3378444,no timeout,14 tested-source pins unchanged. All26 named tests
appear exactly once in the actual log and end OK. They cover missing actual
or expected LD,wrong ID/address/value,rear guard,stale flag,missing/cached/
cross-seed FP,mask omissions,physical4,exit/marker/EOF,missing/duplicate final
SB,LBU,leave and wrong closing PC. They use explicit synthetic prior-call
checkpoints, not whole firmware execution or fabricated DUT evidence.

## Independent Identity Checks and Nonblocking Limitation

All450 entry pins independently rehashed and matched. Both specs' helper and
sticky records match the independently reviewed linked artifacts; all included
code bytes match their own ELF. Actual fcsr/vstart/HTIF/parking encodings and
the absence of SoC tohost were checked. No raw reference trace was read.

A direct complete instruction inventory found a fail-closed metadata omission
in the reused assembly reader: whitespace after operand-less RET crosses a
newline and absorbs the following failure-block instruction. Spike code map
has2859 of2862 decoded instructions; omitted PCs are80001c5e (unsupported
capacity),80001c96 (errors!=0 text path),800023f6 (invalid replay_write args).
SoC has2829 of2832,with80001c72/80001caa/8000237e respectively. Actual incoming
branches establish these are failure paths, not the complete successful path.
Executing any omitted PC is rejected by code.get(pc)==insn; this cannot turn a
failure into PASS. It may report PC/code mismatch instead of the original
diagnostic. No sealed file was changed and no retry is authorized on that basis.

Related scope correction to earlier static-frame wording: the omitted
replay_write error entry has a16B frame. All-path frame sums including it are
568B Spike/520B SoC, rather than552/504; main remains320B and the64KiB stack
reserve is unaffected. This failure-path omission does not alter the successful
CFG upper or reference admission. This report adds the qualification without
editing the already consumed artifact review.

## Receipts

Host03 receipt SHA:
5967481dc015d16bcf92c3f1e09658bbfa03d78c216351b22eb782e69ad9b917

Preserved Host01 receipt SHA:
320382c10a7d3a0bbd4a042b894f7aefaf50d4ab3d7a0b11b5f97f5ed817f367

CHECKER_ORDER_CORRECTION.md SHA:
f32b5fce38d540fa2aed477c7c13a924ffcdd1da2ad6f94e4afd97644672ea42

README.md SHA:
5d207df15ccf5fd0c919aa2203c274c6749fab4ee049064eef33d096d09883fa
