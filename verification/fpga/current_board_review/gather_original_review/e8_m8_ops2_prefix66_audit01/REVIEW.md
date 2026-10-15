# Independent VI0 Natural Prefix66 Source/Reference Review

## Decision

**ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT.** No source/reference blocker found.
This is exactly66 calls, not112, not the full2688 child, not original Linux
execution or proof of the unknown historical stopped tuple. No DUT admission
or increased budget follows from this acceptance.

Only the new audit directory was written. No DUT, build, Host/Spike rerun or
live query occurred. New reference raw was parsed once; old raw was only hashed
as pinned input, not re-parsed. [audit.py](audit.py) independently reconstructs
RNG/input/masks/results and checks trace semantics without the producer model
or parser. [audit.json](audit.json) contains the full66 per-call ledger.

## Identities

Reviewed preparation: `../e8_m8_ops2_prefix66_prepare01/`.
All **65 evidence pins +282 baseline pins** match actual files.

| Artifact | SHA256 |
| --- | --- |
| READY.json | `e8d50733d13cb8182a177bd4849be6ebf75f2f888e9eb838e03afcd243721a2b` |
| Original partition/scene Linux ELF | `cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712` |
| recovery172 report | `419c4dc30fa11412c89eb16f2ba229b8e6a16ebe4390b4a6e5dee1c686531417` |
| Original shared C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| operations.S | `6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824` |
| SoC ELF | `b82305d1bad45e57c70c28ed7a76b25713a943481a957bc99cada9292522e6b6` |
| Spike ELF | `b90a3ea7626e034abb7eb1d1f42d2d6528e56e2c0af9de78ad52233ba790eedf` |
| Full new raw | `03682ef8fc09125b3dc66e0a142d32d3c4dece8a99343c1512730e4fe3056620` |

Archive root `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`:
`rvv_permute_partitions01/release/binaries/rvv_permute_restart_e8_m8_ops2`
equals the recovery172 terminal-scene ELF. Manifest selection is op2/SEW8/m8,
2688 calls; source/port/Host define `PERMUTE_OP_MASK=4`, not VX's mask2.
Archive triage last-PC0x10600/head0x10604 identifies VI0, but `last_trial=null`.

All13 actual helper encodings match archived ELF and both prepared ELFs, with
target `30803c57`: masked `vrgather.vi v24,v8,0,v0.t`, OPIVI unsigned imm0.
Original PC0x10600, SoC0x8000071a, Spike0x8000077a. This is neither a copied VX
binary nor a whole-Linux byte-identical rebuild claim. The shared operations.S
contains multiple helpers; selected executable helper and actual trace establish
which one ran. Original unused index load and `mv t3,a6` are retained.

Independently reproduced source diffs contain only established baremetal
startup/I/O/exit adaptation and stop after the66th complete scalar oracle/guards.
Original RNG, loop body, initialization and65 predecessors remain. Disabled
ops0..1 retain1792 empty source-level iterations, not vector calls. No warmup,
drain or per-call architectural reset was inserted.

## Actual Reference

| Independent raw checks | Count/value |
| --- | ---: |
| Original helper calls / each of13 instructions |66 /66|
| Full-capacity results / guards |67584 /132|
| Unique actual LBU result/guard reads |67716|
| Zero returned vstart / helper vset returns and CSR |66 /198|
| Original capacity vset, return1024/vtype3 |1|
| Initialized values per call |4226|
| Full source/index/predicate/old-vd, result, vector-store checks |66 each|
| Active-selected results185 / preserved results91 |780 /66804|
| Firmware retired through successful HTIF store |2881705|
| Raw bytes |189056398|

Actual a1 is ordinary byte indices, not indices16. a6 and t3 are0; target
immediate is0. Full actual1024-byte v8..v15 source matches the independent
64-bit xorshift13/7/17 model: **source0=185, source31=177**. Byte indices and
16-bit indices16 initialization are separately checked, as are full v16..v23,
1024 predicate bits and old v24..v31. Each target uses requested VL/vstart and
vtype3 (e8/m8, tu/mu), then resets vstart to0. All1024 vector-store address/value
pairs and all1026 scalar readbacks are checked each call. No additional OP-V
instruction beyond the original capacity vset and13-helper sequence appears.

Call65 is VL512/start1 (511 selected results); call66 is tuple `[0,2,0,4,0,1]`,
VL512/start256 (256 selected results), raw line2864328/retired2864323.
Active bytes require185; prestart/inactive/tail and both guards retain91.
VI0 and faithful scalar0 VX0 would have equal values here: actual opcode,
archived identity and encoding negatives distinguish them, not value inequality.
This prefix does not test VI0 with a nonzero unused scalar GPR.

Raw console stores reconstruct exactly one PREFIX66 success, BOARD_CASE_PASS,
BOARD_REPLAY_PASS and the expected case-begin, matching runtime.log. No DETAIL,
FAIL, TRAP or MISMATCH; HTIF store value1 and recorded process exit0 agree.
Recorded Spike4.781531983s, ISA `rv64gcv_zvl1024b`, binary SHA
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
Command retains120s/5M-retired/768MiB-per-file limits. No new execution/retry or
limit increase. Spike reference and SoC runtime ELFs remain distinct identities.

## Negatives and Scope

Stored Host9: positive exit0 plus eight detected negatives exit1, all66 calls
still checked. Verified fixtures/logs/pins and independently matched all static
Host arrays to the new model. Active VL1/start0 gives185->184; wrong-VI31 gives
185->177. Nonempty prestart VL2/start1 and tail VL1/start0 corruption fail, as
do inactive data, both guards and returned-vstart. These are Host oracle tests,
not measured DUT outcomes, and were not rerun.

Seven retained offline corrupted traces are pinned/reported rejected: wrong
byte, invalid target, valid-but-wrong VI31 `308fbc57`, VX0 `308e4c57`, nonzero
vstart, missing source bytes and incomplete scalar oracle. Their mutation code
and stored rejection records were reviewed; no second raw/reference execution.

**66 is not112.** Calls1..64 cover VL0/1/2/3 with all masks/trials. Only the
first two VL512 calls follow. VL512's remaining14 and all16 each for target
VL1023 and VL1024 are untested by this prefix. A future natural112 would retain
these46 additional calls and complete the first scalar-slot's seven VLs, but
has not been prepared or accepted by this audit. Later slots/seeds and Linux
behavior also remain outside scope; the historical stall tuple stays unknown.

Cost:2881705/273=10555.70s; +20%=12666.84s, **above3h**. Older measured-comparable
687..683 retired/s suggests4195..4219s, not actual VI0 DUT throughput. Neither
estimate authorizes launch, oracle shrink or automatic budget enlargement.

Audit JSON SHA256: `014628cd0d3324d127fa3986fcacbd11d9fe1732a2eb697b1753ba3f84ccf7aa`.
Auditor SHA256: `4ae51427a6ec907727eed09f84224ef387b121468734bd5086997dddddbf2792`.
