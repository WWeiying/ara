# Full M8 Exact Block Representation

## Decision

**Representation feasible; prefer e8/m8 full4095 as the first implementation.**
Host-only enumeration completed with actual PID2980852, exit0,12.027426s.
No compilation, Spike, VCS, RTL modification, service query or target launch.
This is not an executable candidate, original-C Host execution, reference PASS,
DUT PASS, Linux closure or a measured <=3h runtime promise.

New evidence: `analyze.py`, `host_result01.json`, `host_exit01.json` in this
directory. All16 recorded input/script pins were checked before and after Host
enumeration. Existing artifacts are unchanged. The old e8/m4 model was imported
with bytecode writing disabled; no preparation script was imported or invoked.

## Measured Representation

| Quantity | e8/m8 | e16/m8 |
| --- | ---: | ---: |
| CAP at VLEN1024 |1024|512|
| Original calls |4095|4095|
| Original result elements |4193280|2096640|
| Guards / returned-vstart checks |8190 /4095|8190 /4095|
| Exact output bytes/call |1026|1028|
| Full 8B reads + narrow final read/call |128 +2B|128 +4B|
| 64B block IDs/call |17|17|
| Distinct exact padded blocks |3768|3598|
| Pool bytes |241152|230272|
| uint16 ID table bytes |139230|139230|
| Three physical128B masks |384|384|
| Total expected ROM |380766|369886|
| Original physical a/b/out/mask bytes |3202|6276|
| Space left after ROM, arrays,64KiB stack,64KiB code reserve |533536|541342|

Both word-ID-only alternatives require4095*129*2=1056510B before their value
pool, exceeding1MiB. Block IDs require4095*17*2=139230B. No call or duplicate
zero-length/start position is removed. Pool IDs are first-occurrence IDs assigned
by equality of all64 bytes, NOT hashes, per-call identity or result checksums.
Max IDs3767/3597 fit uint16 exactly. Pool/index hashes are recorded in the result.

The existing linker `full_e16_mf4_prepare01/runtime/replay.ld` provides1MiB L2
and a64KiB stack exclusion. The table shows a planning reserve, NOT a linked
image bound: future actual text/data/BSS/alignment and stack symbols must pass
that linker contract. The16-bit shape retains original out[1026] words (2052B
physical), but touches only(cap+2)*2=1028B per call, not its unused array tail.

## Exact E8/M8 Implementation Proposal

Keep the recovered seed -> op -> seven VL -> three masks -> original starts
loop order, all4095 calls, original capacity/helper bytes and returned-vstart
checks. Keep a/b[1024], out[1026], mask[128], all RNG updates and special inputs.
The seven VLs are0,1,2,3,512,1023,1024. Preserve original scalar mask-copy frequency
(once per seed/op/VL/mode,1575 copies), not once globally because values repeat.
No new vector operations, helper calls, reset, partitions or prefix substitutions.

Represent expected bytes starting at the leading guard, not at out+1:
`uint64_t pool[N][8]` aligned64 and `uint16_t ids[4095][17]`.
For blocks0..15, load one ID, calculate its pool base once, and unroll8 exact
comparisons at offsets0,8,...,56. Actual output base is aligned8; access through
byte pointers and fixed-size memcpy avoids aliasing/alignment UB. Do not cast
the deliberately unaligned helper destination out+1 to uint64_t.

For block16, read only2 actual bytes at out+1024 (unsigned16); compare against
the low16 expected bits. For e16 use4 actual bytes (unsigned32) and low32 bits.
ROM's remaining62/60 last-block bytes are zero solely for canonical representation.
NEVER read/write output through1088B, or even1032B. Initialization similarly
performs128 complete8B stores plus one2B/4B store, exactly1026/1028B. E16's
sentinel word is0x005b, so its64-bit repeated fill is0x005b005b005b005b, not e8's
0x5b5b5b5b5b5b5b5b. Both guard bytes of each e16 guard remain checked.

Every byte is covered: e8 total4201470; e16 total4209660. On success, retain the
original full result and call counters. On mismatch, retain the original complete
per-element oracle/reporting path, guard/vstart failure veto and nonzero exit;
do not return success after a checksum or a subset. No fflags check is invented
for this integer source. Any future DUT checker must also bind actual setup
stores, helper13-instruction windows, exact PCs and nonempty memory owners,
including op24 targets; a representation Host check does not replace those gates.

## Model And Host Evidence

Existing e8/m4 `model.py` hardcodes CAP512,SEW8,lengths,65 words and514B output.
It cannot be reused by changing a capacity constant alone. Its imported
`full_e16_mf4_prepare01/model.py:integer(op,x,y,sew)` is SEW-parametric; its
`rows()` is not (cap16, fixed lengths/output initialization). The new analysis
reuses only pure integer/selection/serialization helpers and independently
parameterizes the full loop/RNG/oracle by(SEW,CAP).

The oracle follows recovered C's per-element path, reduction modular seed,
compress cursor, prestart/masked/tail sentinels, slide bounds and gather index
width. E8 gather indices are8-bit and cannot exceed255 even though CAP1024;
e16 indices are16-bit and can exercise >=CAP zero results. E8 mask uses all128B;
e16 mask retains128 physical bytes with its upper64 bytes zero.

Host evidence includes exact context and byte comparison of all4095 e8/m4 rows
against the mature word-dictionary model, then full4095 reconstruction for EACH
m8 shape. Each reconstruction equals the original per-element-model byte vector,
with exact access-span coverage.40950 selected byte flips per shape (leading and
trailing guards, boundary/interior/tail positions) fail the byte comparison.
These are Python representation negatives, NOT compiled C checker negatives or
an independent second implementation of integer arithmetic. Later software
preparation still needs C-vs-packed Host equivalence and failure diagnostics.

## Cost, Not A Runtime Guarantee

For either m8 shape, full-word plus narrow-tail comparisons remain528255.
Only ID lookups fall from528255 to69615 (458640 fewer,86.82% reduction); expected
loads and actual loads remain528255 each. For each full block, one lhu, one
shift-by6 and one address add can serve8 ld/ld/branch comparisons. A success-path
sketch needs roughly1793610 core comparison/address instructions, before loop,
call, initialization, RNG, masking and reporting overhead. Fixed8-way block
unrolling avoids8 separate indexed pool-address calculations; no giant fully
unrolled4095-call program is proposed. The last block must have its own narrow
load path, not an8-word loop.

Initialization still costs528255 real output stores plus loop/address overhead;
mask copies retain25200 word stores and25200 corresponding ROM loads. A rough
2.8--3.6M total firmware design estimate is plausible, NOT a conservative upper
bound or measured retirement count. The mature e8/m4 READY records2646649
firmware instructions,614110B ROM and7861.917s projected with20% margin, but m8
has double source/old-vd/output vector bytes and may have different division and
gather latency. It cannot inherit that elapsed projection or imply <3h from ROM
size. A later compile, actual code inspection and ONE authorized bounded full
reference would establish software cost before any DUT admission.

## Source Identity

Archive A=`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04`.
Both original files under `A/overlay/opt/ara-tests/` were freshly compared byte
for byte with `arithmetic_restart_original/recovery22/` rebuilt ELFs and checked
against both manifest and retained recovery report:

- rvv_matrix_e8_m8 ELF: `ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f`.
- rvv_matrix_e16_m8 ELF: `68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d`.
- A/rvv_matrix_e8_m8.S: `e0dd3eb419e65813853869548fe54e278457005db90e032ed4a64ecb8aa5be08`.
- A/rvv_matrix_e16_m8.S: `a55d6f07a2f69258ffe07378baf08cf72fab2283312b76a8a8b5a5637b35d191`.
- A/e8/operations.h and A/e16/operations.h: `7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c`.
- recovery22/reconstructed_oracle.c: `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.

Original C bytes are not recovered. The accepted reconstruction's retained
report records exact Linux ELF/disassembly equality; this task freshly confirms
ELF byte equality, not a new rebuild or disassembly proof. Original ELFs are
identity evidence only, not bare-metal executables. No new SoC ELF exists here.
All source/manifest/compiler-command provenance is embedded in host_result01.
Original historical stalls, original Linux execution and other shapes remain
separate from this full-call representation feasibility finding.
