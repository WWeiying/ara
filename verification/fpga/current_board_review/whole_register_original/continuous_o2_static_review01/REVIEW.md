# Continuous1134 O2 Static Review

Decision: no identified source/compiler-delta or actual reference-command
binding blocker. This is a static review, NOT independent full-raw reference
acceptance and NOT DUT admission. Continuous DUT remains HOLD pending measured
reference cost; a projection above10800s must remain HOLD.

## Evidence Checked

- Nine C/assembly/runtime/linker/wrapper inputs equal `prepared01` byte for byte.
  The actual compiler receipts use `-O2` in place of the pinned recipe's `-Os`;
  independent paths are the other change. No LTO, auto-vectorization or extra
  source optimization was added. Both actual compile exits are0.
- Archived manifest SHA4f7b897338c4ec18777e304e9790857a6a406b17ee021b3d5436fa1c3ff06091
  identifies Linux `rvv_whole_registers_detail`, ELF
  f6ca381157fa767ab774017136af26d139e5c4776a1e7771f062251bbb7a2ecc.
  Copied original C matches its manifest c7ab8b2293bf3583140cc8679126f0303a04e21e7c7d722833093da61da6a7ff.
  This does not make the new SoC ELF byte-identical to Linux.
- Independently enumerated seed/op/mode/start matches all1134 ordered calls and
 366 original exclusions. Counts per op0..19 are
 60,60,60,60,60,60,60,60,60,60,60,60,45,60,60,60,48,48,48,45.
  Both operation bounds are0..20; there is no reset partition.
- Every spec PC/instruction was compared directly with actual ELF PT_LOAD
  bytes: SoC1582 entries, Spike1632 entries. Each backend's20 complete helper
  encodings (620 instructions, including branch alternatives) occurs unchanged
  in its old ELF. SoC op0=0x800008c8; Spike op0=0x800008d4. The parser does not
  reuse old fixed PCs.
- Original per-call1024 input bytes and1088 output bytes remain in source:
  1161216 input bytes initialized across the calls,1233792 output-byte oracle
  checks,2268 vstart readbacks. Sentinel/prestart/tail are not relaxed. Status
  remains captured-start in high32 and returned-vstart0 in low32.
- All43 `reference_bound01.json` input hashes matched during this review,
  including actual ELFs, parser, reference executor and external compressed
  memory decoder. Read-only review command exited0 (tool chunk1c6e57).
  An initial review assertion compared the entire tuple JSON against the old
  metadata; old-only `partition_counts` caused that assertion. Rechecking exact
  `cases`/`skipped` plus independent enumeration resolved the review-script
  mismatch; no preparation/reference failure or changed source was involved.

## Parser And Exit Contract

`audit.py:58-61` selects the actual Spike spec and derives target PCs from each
original helper. Lines95-123 enforce helper entry order, original arguments,
branch path, two preloads, both vstart reads, returned status and output store.
Lines145-154 check real scalar read values, byte by byte, against the original
formula and reject duplicates; `finish_call` requires all1088 offsets.
Generic scalar writes decode their actual width/effective address and memory
payload, rather than assuming every write is an output or console byte.

Successful raw firmware return must be0 at `replay_exit`; actual HTIF store
must be64-bit1. This is not SoC CTRL's raw0 protocol. Final counters must be
1134/366/0 with exact console, no traps, full helper completion and legal
post-exit park. Source setup and original status are not inferred from console
alone. The actual parser command uses reference_bound01 digest bfc5d224...,
matching `audit.py` (not the older `bound.json` argument).

Scope limitation for a future DUT checker: the parser's scalar `memory` shadow
checks complete setup VALUES but is not a per-call fresh-write ledger
(`audit.py:99-100,137-140`); vector stores do not update that shadow. Repeated
same-seed input values and sentinel values can remain cached there. Do not call
this proof that every initialization store retired on every call. A future
packing/DUT observer should reset input/output write-coverage sets per call,
require every byte freshly written before entry and reject removal of an entire
initialization interval. This does not demonstrate an error in the pinned C or
actual reference; it bounds the current parser's mutation coverage.

## Actual Run And Budget

Read only the durable small reference receipt: actual Spike wait0,
36.55840876419097s, timeout=false, attempts1. No raw commits were read or
reparsed by this reviewer. At this review snapshot the full-parser exit/result
was not yet available; process0 alone is not reference acceptance.

Actual invocation is non-debug Spike `--isa=rv64gcv_zvl1024b -m2
--instructions=40000000 --log-commits`. Fixed bounds are120s,4GiB raw and600s
parser, with exclusive output/no retry. Source/code pins are checked before
execution and after parsing; actual numeric wait receipts precede acceptance.

Use firmware-through-HTIF from the completed parser, excluding boot/parking.
The existing wholemove proxy23113 retired/46.15s is about500.82ret/s; it supports
only about5.409M instructions in10800s without margin, or4.507M with20% margin.
Even a faster740ret/s scalar proxy supports only6.660M with20% margin. These are
conditional planning thresholds, not a measured O2 throughput or authorization.
Never divide a single continuous workload by the20 prior partition jobs.

## Bound Identities

- SoC ELF: 3f02c7531dd7fd97f75c8f457b3efbf1708672a114da86d81be05cf7f3b3b2a0
- Spike ELF: 1c14e9a41f522c13da4836090cc4161f7232cb5cbbc5439d39d0150e3338f688
- sourceproof: 2cfceebaff944a815551e481d78e90ea6081288b1f6d098c59cd698c796f7b45
- tuples: c6a7c39edc883b9d5076a7361ab42d1139a89bada87213883b82a9c38a5ad7b3
- reference_bound01: bfc5d224fb820f354ee11bc04c779f21093dbdece6baf22ef20a2d6da96bc0b6
- audit.py: 59a23921d296df46b569078baadc1fcd2233e79aef378000641d11d36f82fd8b
- reference.py: 9f6faeb97eea9ca370c83b9fd76e7ef7e9b47730435223ca5514b2ce8a8a3593

No source/helper/RTL edits, compile, Spike execution, DUT launch, active700
inspection or duplicate whole-reference semantic parse were performed.
