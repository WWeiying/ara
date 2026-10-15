# One-Pass Closed Prefix Diagnosis

Status: **DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS**. Original simulation timeout,
producer NOT_PASS, service exit1 and collector NOT_ACCEPTED remain unchanged.
No new DUT/reference execution, no timeout change, no E16/M8 observation.

## Actual Execution and Identity

- Own original M9 E8/M8 Strict/spec/26 helpers and private ELF were checked before
  use. All original `Strict.consume` numeric, initialization, address/BE/data,
  actual PC/code, CSR, order, fresh-output and 129-read checks remain intact.
- Exact source-template qualification changes only original op19/38813c57/VI2
  ownership where offset2 >= VL. Other target and all five memory-helper owners
  remain mandatory. Twelve such nonempty-start no-ops occur in the seen prefix.
- Small constructed partial-EOF Host: 10 tests, actual process exit0. Includes
  incomplete helper/readback, pending requests, wrong numeric/code, deleted
  compulsory memory pair, unmatched done and VI2/op24 qualification. No raw read.
- Exactly one full original CSV traversal: PID3252837, actual OS wait0,
  273.6405904009007s, hard bound600s, timed_out=false, retries0.
- CSV220110178 bytes, SHA256
  `fb6f10d066f9b96c2dfc13dac2bdc5432c76bd04145f0d1e4dd84d9831109d98`.
  Raw hash computed in the same traversal; pre/post inode/size/mtime unchanged.
  All26 scoped source/spec/import/ELF/receipt pins unchanged. This does not claim
  a fresh rehash of the original whole plan's large reference/image inputs.
- All1908677 rows delivered unmodified through the original lossless transport;
  before/after row-stream digest both
  `40acd154aaa695b102cd73fc9c60614268a2f5813b7f42f66185ae2cc96286ae`.
- Neither full4095 Strict.finish nor generic completed-run finish was called.
  EOF reports pending state explicitly; no records or completed results fabricated.

## Measured Source Frontier

All first2601 source calls have complete13 helpers, returned vstart0, full129
packed reads, and completed necessary owners. Their 2663424 result bytes and5202
guard bytes were checked by the original numerical oracle (335529 packed reads).
Source counters independently read from actual stores: checks2601,
elements2663424, errors0. The last checks store is cycle21859157/PC80000da6.
This is a validated prefix diagnostic, not full4095 acceptance.

Last completed source call, original ordinal2601 (zero-based2600):
seed1/op20/li5/mode2/VL1023/vstart0. Next expected original ordinal2602:
seed1/op20/li6/mode0/VL1024/vstart0. Its helper has **not** entered.
The zero-based `next_call.ordinal` in result.json is2601; do not misreport it as
original ordinal2601. Remaining1494 source calls are not validated by this closed
prefix; execution beyond the recorded frontier cannot be inferred.

EOF: retired1793564 instructions, last order1793563, cycle21859382,
PC80000b2c/0721. `helper=null`, next helper index0, output initializer index0.
Last completed call still occupies `current_call`, with all129 reads; this is
not evidence that next call's result checking started.

Freshness ledger: a0/b0/out0 newly written bytes since consumption, mask112.
Zero a/b freshness is normal seed-level reuse, not missing original inputs.
Relevant actual last GPRs:

| Register | Value | Meaning at this PC |
| --- | --- | --- |
| gp/x3 | 8005f810 | Actual global pointer |
| a2/x12 | ffffffffffffffff | Loaded mode0 word14 |
| a3/x13 | 8005f0d8 | Maskcopy destination end |
| a4/x14 | 800020f8 | Source advanced to word15 |
| a5/x15 | 8005f0c8 | Destination word14, store not yet in CSV |
| s3/x19 | 80002080 | Mode0 physical mask ROM |
| s5/x21 | a29 | Completed calls2601 |

Thus CSV proves14 stores (112 bytes) of this mask instance, plus load of the
next word. The earlier bounded hart tail additionally shows that word14 store;
the two log frontiers are kept separate, not merged into synthetic CSV records.

## Protocol and Gaps

-28613 each arch starts, accepted CVX requests, responses and retired offloads;
  matched prefix transport replays0; no unmatched sequence suffixes.
-14637 uop alloc/done pairs;13005 compulsory helper-memory owners plus1632
  required targets. Every completed checked call's owners were qualified.
-EOF pending CVX and uop sets are both empty. No seen accepted vector request
  remains uncompleted at that point. This says nothing about a later unlogged
  scalar/cache stall or the actual simulator stop cycle.
-Largest interval between any recorded events:6352 cycles, within original
  call1357 (seed0/op24/li6/mode0/VL1024/start0), bracketed by later events.
  Target00050c07 owner14925 allocated11437241, completed11443619:6378 cycles.
-Largest retirement gap6354 cycles in that same call. The second largest is
  call1348 (same op24, VL1023). Both completed, not permanent stalls.
-Late full-group output stores02060c27 show6156-cycle alloc-to-done intervals,
  including final checked call2601. They are bounded completed waits.
-Every million-cycle bin in the recorded interval has retirements and backend
  completions. Full bins1..20 contain roughly77.8k..93.6k retires each. There is
  no measured long all-event silence larger than6352 cycles *inside this trace*.

This refutes an unresolved vector-owner deadlock within the recorded prefix and
supports substantial distributed execution cost there. It does **not** establish
three hours of uninterrupted wall-time progress or rule out a terminal stall.
No final simulator-cycle evidence exists; progress fflush was disabled. Original
mtime and hart tail cannot close that remaining gap.

## Full-Scope Cost Implication (Not a New Budget)

The same scan retained all completed source-counter checkpoint cycles. First
seed's entire1365-call configuration set took11529816 monitor cycles including
initial setup; the observed2601-call mean is8404.14 cycles, median8200,
range8130..36325. These are call-to-call check-store intervals, not isolated
vector latency, and include scalar setup/oracle/loop overhead.

Metadata-only calculation after the scan matched each of the1494 remaining
source tuples to seed0's same(op,li,mode,si,VL,start) checkpoint interval. This
gives12726678 additional cycles and about34586060 total. It assumes seed-level
data timing is comparable and is not an upper bound. At the crude recorded-cycle
to10800.1126s wall ratio, the illustrative total is17088s (~4h45m), not <=3h.
The proxy is especially uncertain because final simulator time is unknown; it
cannot justify an extension or identify timeout as purely budget cost.

Do not repeat this full ELF under the same unqualified <=3h projection. Before
any future run decision, either establish a valid full-scope cost reduction with
unchanged history/oracle, or obtain an independent final-simtime/wall-time endpoint
mechanism. A minimal future discriminating probe would retain exact final cycle,
last retire and CVX/uop/cache outstanding state at external timeout, so a long
silent suffix can be measured. No such probe/run/build is executed or authorized
by this report. No narrower source prefix is substituted for the full objective.

## Durable Evidence

- `diagnose_wait.json` SHA256:
  `f1a90df75ac5e3e94e46839944f8875fc9bb46440c6df04393d6aa03ccace0a6`
- `run01/result.json` SHA256:
  `9f6b55280eaa284e1cf2eacd33704be38faa2c3f1447b7e9943afc8d0de871e0`
- `run01/inputs.json` SHA256:
  `ab5328fbd078c7262cb3be6672ddc7003b644797a3712f28efd5114e0100bce0`
- `diagnostic.py` SHA256:
  `658a69a0d36b40fa5809dc88cf119a8b7d390df68b708ab5afad0a96c0434e60`
- `host.json` SHA256:
  `03b7f239fe2e55b8f2f3c024c55dbe3f099e3cbae4af4b78146437a09dd700db`

Original files and original failure receipts were not changed. This report is
the executor's bounded prefix diagnosis, not an independent whole-scope audit.
