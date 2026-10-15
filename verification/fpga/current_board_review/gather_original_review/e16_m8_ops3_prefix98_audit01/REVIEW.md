# Independent vi31 Prefix98 Source Review

2026-10-11. **ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT. No blocking finding.**
This accepts the frozen source/Host/Spike preparation, not a future runner,
DUT launch, DUT result, original full child, or Linux execution.

Preparation: `../e16_m8_ops3_prefix98_prepare01/`.
READY SHA256 `a354337fd4e6f2177b572db9ae372d580558fc55c12b21c1c05e3eac3f1bc672`.
All62 owned evidence pins and148 baseline pins matched actual files. No sealed
input/helper/RTL changes, build, Host/Spike rerun, DUT or live-process query.

[audit.py](audit.py) is a new local derivative of this reviewer's independent
ei16 auditor, specialized to original vi31. It does not use the producer's
model or raw parser. An independent xorshift/oracle reconstruction and a
single full raw parse check the actual architectural state; existing pure
adaptation helpers are used only to verify source transformations. Objdump
reads existing ELFs. No firmware, compiler or simulator is executed.

## Original Identity

Campaign root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
The exact original child is `rvv_permute_restart_e16_m8_ops3`, bound by
`rvv_permute_partitions01/manifest.json`, original C/operations.S/header,
`release/binaries/rvv_permute_restart_e16_m8_ops3`, and matching scene ELF/report
under **rvv_recovery08_177/terminal_scene**. It is not recovery175 (vx).
Recovery168's different e8m4 vi31 multi-process history is not imported.

| Artifact | SHA256 |
| --- | --- |
| Original partition/scene/copied Linux ELF | `16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853` |
| Recovery177 report | `15a4bd6236a76e9ef8b3eec69fdf018ffb85ab3989114fad066851c0635f1bbf` |
| Shared original C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original operations.S | `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` |
| Original operations.h | `886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4` |
| SoC ELF | `c1064255efa0ff19d492d263723d1c7b88ad9521983ae07d12ecf8a753b5cf44` |
| Spike ELF | `e515e9b39af91af64f83d743a919fc6284512492a1a3f112b27646807cc70760` |

The shared C is the unchanged original retained at
`rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`; its hash
matches the partition manifest. Actual original and prepared ELF disassembly
each has one matching13-instruction selected helper. Target opcode `308fbc57`
is `vrgather.vi v24,v8,31,v0.t`, at original0x1064a, SoC0x80000764 and
Spike0x800007b0. This is not a vx31 substitution. Whole original Linux binary
byte-identical rebuilding is not claimed; reference uses the Spike runtime ELF,
not the SoC runtime ELF.

## Source and Natural History

Recomputed source adapter/prefix diffs exactly match the recorded diffs and
prepared C. Only the existing Linux startup/output/exit wrapper and a stop
after call98's complete result/guard oracle are introduced. Prefix PASS/FAIL
is explicitly named. No oracle reduction, per-call reseeding, warmup, hint or
vector drain was added. Build selection remains SEW16, m8,
RESTART_PERMUTATIONS1, PERMUTE_OP_MASK8. Disabled ops0..2's2688 source-level
empty iterations remain; these are not2688 vector predecessor calls.

All97 actual vector predecessors are retained. Seed0/scalar-slot0 remains
fixed throughout the prefix, with VL0/1/2/3/256/511 each16 calls, then VL512
twice. Original mask order and four restart trials are unchanged. Final tuple
is `[0,3,0,6,0,1]`: VL512/start256/all-on/scalar0/cap512. Both index arrays
are still initialized; actual a1 names ordinary `indices`, and its unused
vle16 load into v16..v23 is retained. Original `mv t3,a6` also remains and
both a6/t3 actually contain0, not31.

Every call checks all512 results, both91 guards and returned vstart0.
Expected active-selected result is original input[31] because31<cap512,
regardless of requested VL. Exact91 is required for prestart, inactive and tail
under tu/mu. The independent model agrees with all initialized data/index
arrays and all98 rows of host_expected.json, not just stored hashes.

Historical `last_trial` is still null. Last archived DETAIL is a post-return
VL256/start128 observation, not proof of which subsequent call stopped.
Reaching a selected prefix boundary does not recover that unknown tuple.

## Actual Raw Reference

The actual raw is **120211844 bytes**, not137MB; SHA256
`c958f455c9ec66eb298efcd2e05594afdfec871537081576feece36242dcc5a9`.
It was fully parsed once, successfully on the first invocation, and hashed
again within that pass. [audit.json](audit.json) records each actual target
line/retirement and call tuple. No repeated full raw parsing or Spike rerun.

| Independently checked observation | Count/value |
| --- | ---: |
| Actual original helper calls/targets in order | 98 |
| Each original instruction encoding/retirement | 98 each;13x98 total |
| Actual initialized scalar setup values | 2178 per call |
| Full512 input/index/old-vd vectors and low512 predicate bits at target | 98 groups |
| Full512 target result vectors and vstart reset | 98 |
| Full512 vector-store address/value sequences | 98 |
| Scalar LHU result checks | 50176 |
| Scalar LHU guard checks | 196 |
| Distinct output/guard reads, once per position/call | 50372 |
| Actual vset returns and VL/vtype state | 294 |
| Actual target vstart / returned-vstart0 | 98 each |
| Actual source[31] / scalar a6 and t3 | 32689 /0 |
| Active-selected / preserved result elements | 2669 /47507 |
| Firmware retired through successful HTIF store | 1905086 |
| Last target retirement | 1894835 |

All98 call targets/trace lines agree with reference.json. The independent
parser reconstructs vector registers from raw updates, including no-op calls
with no destination updates; old-vd91 is checked before every target and the
full result afterward. Upper unused mask bits are not overconstrained.
No output is used as its own golden value. Original CSR oracle is vstart;
this is not extra fflags/vxsat coverage.

Raw console exactly matches recorded runtime.log/reference.json and has one
each of PREFIX98/errors0, case PASS and BOARD_REPLAY_PASS, with no
FAIL/TRAP/MISMATCH/DETAIL or misleading full-child RVV_PERMUTE_PASS.
Successful actual HTIF store value1 and recorded Spike process exit0 are
required in addition to the complete oracle, not used alone as acceptance.

## vi31 Discrimination and Layout

Actual instruction fields are OPIVI funct3=3, funct6=12, vm=0 and unsigned
5-bit immediate31. Each actual source vector contains input[31]=32689,
whereas input[0]=61881 and unused scalar a6/t3=0. Exact opcode and this
observed result distinguish the original vi31 from vx0, vi0, or a signed
extension of31 to -1 (which would be OOR and produce0 for selected elements).

Concrete actual calls checked:

- Call18, VL1/start0/all-on, target retirement366858: element0=32689 even
  though source index31>=VL; remaining511 elements and guards retain91.
- Call33, VL2/start1/all-on: element0 remains91 and element1=32689.
- Call66, VL256/start128/all-on, target retirement1245698: prefix0..127=91,
  elements128..255=32689, tail256..511=91.
- Call98, VL512/start256/all-on, target retirement1894835: first256=91,
  last256=32689; the complete original oracle and both guards return correctly.

There are38 nonempty architectural windows and60 no-op windows;25 calls
actually have selected active elements, totaling2669. Unlike ei16, vi31 has
no OOR gather index here: unused index-array values512/513 are not gather
indices for this opcode. This reference therefore does not cover ei16's
OOR/no-data end-token behavior.

For e16, logical source element31 occupies bytes62..63, the end of a64-byte
span. With VLEN1024, architectural v8 is128 bytes: element31 remains inside
v8, not at the v8/v9 physical-register boundary. Under four64-bit-lane e16
layout it is the high16 bits of lane3's second aggregate32-byte word. The
byte placement follows the layout contract; Spike raw proves the architectural
source/result, not an observed RTL lane-request waveform.

## Host Negatives and Scope Limits

Stored Host1 positive+7 negatives and five offline-negative fixtures were
read/hash-checked, not rerun. Host positive records98 calls/errors0/exit0;
each injected case records98 calls/INJECTED1/errors1/exit1. Actual DETAILs
show active VL1/start0/element0 (32689->32688), prestart VL2/start1/element0
(91->90), inactive VL1/start0/mask1/element0, and tail VL1/start0/element1.
Prestart and tail negatives thus use distinct nonempty-body scenarios.
Guard0, guard1 and returned-vstart failures are also recorded. Host uses mocks
to test the original C oracle, not hardware.

Offline fixture hashes/reports retain rejection of wrong halfword, target
encoding, nonzero vstart, missing source bytes and incomplete oracle. Their
earlier executions are not relabeled as new independent negative runs here.

Reference command/ELF agree with execution.json and command.json. ISA is
`rv64gcv_zvl1024b`; restart-capable Spike hash remains
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
Recorded elapsed3.125896011s/exit0; unchanged ceilings120s/5000000
instructions/768MiB per output file were not exhausted.

Actual1905086 retired gives **estimated**, not measured VCS, durations of
2773.05..2789.29s at prior M5 rates687..683 retired/s,6978.34s at273/s,
or8374.00s with20% margin at273/s. This is below3h, not a throughput guarantee
or permission to launch/increase a budget. A future runner requires separate
review and parent authorization.

Only first98 of2688 child calls, seed0/scalar-slot0, are accepted as reference.
VL512 sparse/all-off cases, later seeds/scalars, complete child/parent and
original Linux execution remain outside this prefix. Historical stopped tuple
remains unknown; no common-root-cause or DUT PASS is asserted.

Audit result SHA256:
`f7a31b0d7c0420ca78fb979875d38834a0cb19f064f7e77c20b37751c7c4ee22`.
