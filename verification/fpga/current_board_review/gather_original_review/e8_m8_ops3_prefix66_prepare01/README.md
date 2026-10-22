# Authentic e8/m8/ops3 Natural Prefix66

Host/Spike preparation only. No DUT, RTL build, live-simulation query, ZCC,
Verilator or modified frozen helper/reference. Independent source/reference
review precedes any separately authorized DUT work.

## Authentic Identity and Scope

Original child rvv_permute_restart_e8_m8_ops3 is selected by PERMUTE_OP_MASK8
in rvv_permute_partitions01. The original partition ELF and recovery173
terminal-scene ELF match. Historical last_trial is null: no exact stopped tuple
or Linux replay is claimed, and no additional process history/warmup is added.

| Original artifact | SHA256 |
| --- | --- |
| Linux ELF, partition and scene | ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c |
| recovery173 report | 1ca4e0f534d0fb804f94ba8e127a32945eb45a6de4b2bd8ab8d6ac40848ba50d |
| Shared C | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| operations.S | 6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824 |
| operations.h | 2f9fcaa9b1deab684890f5b79add2bd06ab481ec8c22e5d42db2dbab7305b4f3 |

All originals are retained in prepared/. The port applies only the established
Linux startup/I/O/exit wrapper adaptation and a stop after the complete oracle
of call66; source_diffs/ records both transformations. Original loop body,
RNG initialization, predicate/old-output initialization, call order, scalar0,
vstart, unused index load and mv t3,a6 remain. Disabled ops0..2 retain their
source-level filtering (2688 empty loop iterations, not vector predecessors).

Exact scope:66 selected calls,65 predecessor calls, cap1024,67584 result
checks +132 guards,66 returned-vstart checks and13 original instructions/call.
Endpoint [seed0,op3,scalar-slot0,length4,mask0,trial1] is VL512/start256.
Every call still checks all1024 elements, including the full tail.
This is not full2688-child or full-parent acceptance.

## Actual Helper and Source31

source_elf_proof.json compares all13 actual encodings across the archived
Linux ELF and both prepared ELFs. Original target PC0x1063e, SoC0x80000758,
Spike0x800007b8; opcode308fbc57, vrgather.vi v24,v8,31,v0.t.
The unsigned immediate is31, not a vx source. Actual a6/t3 remain0;
a1 points to ordinary indices, not indices16.

The e8 oracle independently executes the original64-bit xorshift13/7/17,
truncating input and ordinary indices to8 bits while keeping indices16
16-bit. It computes input[31]=177 and input[0]=185. All66 raw targets
verify the full actual v8..v15 group and explicitly record actual_source31=177.
Thus177 is measured against the original RNG, not copied from an earlier case.
Full old destination, unused v16 index group and1024-bit predicate are checked.

At VLEN1024, byte element31 lies within the first physical register v8
(128 bytes), not across registers. For the four-lane EW8 layout it maps to
lane3, local word0, byte7. This is the static layout discriminator relative to
e16 source31, not a measured RTL lane waveform or a new common-root claim.

Active selected values require input[31]=177 even when VL<32, since source
range is capacity. Prestart, inactive and tail retain91. Across the66 calls,
780 active selected results are177; the other66804 results remain91.
Both guards remain91.

## Full Reference Evidence

| Observation | Actual |
| --- | ---: |
| Calls / each of13 helper instructions |66 /66|
| Scalar result / guard checks |67584 /132|
| Unique scalar LBU output/guard reads |67716|
| Returned-vstart zero / vset checks |66 /198|
| Setup values per call |4226|
| Full vector input/result/store checks, each |66|
| Firmware retired through successful HTIF store |2621149|
| Spike elapsed / exit |4.227606456s /0|
| Full raw commit bytes |165411158|

The sole Spike execution used the existing120s/5M-retired/768MiB-per-file
limits; no retry or larger limit. Its restart-capable binary SHA is
c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2.
Full reference/commits.log is retained, SHA
3f6fe246594f6957d8fa61b07598ff600673b093d74995f7f4e31777cabb64c0.

The raw checker verifies all initialized bytes, actual call arguments,
13-instruction order/encoding, target VL/vtype/vstart, source/predicate/old-vd,
complete target result/reset, all1024 vector-store address/value pairs and
all1026 unique scalar oracle reads each call. PREFIX66/BOARD markers and
zero HTIF exit are mandatory; missing data, trap, DETAIL or FAIL rejects.
reference/reference.json keeps full per-call ledgers; host_expected.json
keeps all input/index/predicate/result values.

Host oracle tests: one positive plus seven detected negatives (active,
prestart, inactive, tail, both guards, returned-vstart). Prestart corruption
uses nonempty VL2/start1; tail corruption uses nonempty VL1/start0.
Host mocks test the original C oracle, not the DUT.
audit01/audit.json separately rechecks raw/source and five corrupted traces;
it performs no second Spike execution. READY.json records the completed audit.

| Software ELF | SHA256 |
| --- | --- |
| soc01/gather_prefix_e8_m8_ops3.elf |88b154a9a1c68f2a25706eb7b8587237335b34d3bc69590f970fec0074fca841|
| spike01/gather_prefix_e8_m8_ops3.elf |83045b87c11b79d8e5b53202cca094ce5380c13abe33a76ee518c25b55baf9bf|

Spike uses its reference-runtime ELF, not the SoC ELF. Helper byte-equivalence
to the archive is proven; an entire byte-identical Linux rebuild is not claimed.

## Cost and Handoff

2621149 retired at earlier measured M5 rates687..683/s estimates3815..3838s.
At conservative273/s it is9601.28s; plus20% is11521.53s, **above3h**.
These are estimates, not this case's measured VCS throughput. No DUT budget
is increased, runner created or launch authorized by this preparation.

READY.json seals the owned evidence. baseline_pins.json binds218 unchanged
source/tools/helpers/reference files, including e8ops1 and e16vi31 references.
Independent Averroes source/reference review is pending at producer handoff;
source acceptance is not DUT admission.
