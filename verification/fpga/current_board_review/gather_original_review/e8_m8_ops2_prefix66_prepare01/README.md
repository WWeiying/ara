# Authentic e8/m8/ops2 VI0 Natural Prefix66

Host/Spike source preparation only. No DUT, RTL build, live-simulation query,
ZCC, Verilator or change to old sealed references/helpers.
Selection follows ../VI0_VX0_PATH_REVIEW01.md; conditional static backend
similarity to VX0 is not transferred as VI0 execution acceptance.

## Authentic Identity

Original child rvv_permute_restart_e8_m8_ops2, selected by PERMUTE_OP_MASK4,
is pinned to the partition manifest and recovery172 terminal-scene report.
All archived copies are retained in prepared/.

| Artifact | SHA256 |
| --- | --- |
| Original Linux ELF, partition and scene | cc5015d9e7838bfc4f0d4f2b0627e6a08930bd4058b12651a4f988a5c9b1d712 |
| recovery172 report | 419c4dc30fa11412c89eb16f2ba229b8e6a16ebe4390b4a6e5dee1c686531417 |
| Shared original C | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| operations.S | 6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824 |
| operations.h | 2f9fcaa9b1deab684890f5b79add2bd06ab481ec8c22e5d42db2dbab7305b4f3 |

The original C body, RNG initialization, source/index/predicate/old-output
setup and full result/guard oracle remain. Only the established Linux wrapper
is replaced; the natural prefix stops after call66's complete original oracle
and emits distinct PREFIX66/BOARD markers. Both source diffs are retained.
No new warmup, drain, per-call reset, shortened oracle or endpoint-only program.

The prefix retains65 predecessor calls and all original predicate/trial/CSR
ordering. Disabled ops0..1 retain1792 source-level empty loop iterations, not
fabricated vector calls. Endpoint [0,2,0,4,0,1] is VL512/start256, scalar-slot0.
Every call checks cap1024, including tail, for67584 results+132 guards total.
The historical stopped tuple is unknown. This is not full2688-child, Linux,
full-parent or exact historical-stall acceptance.

## Actual VI0 and Source

source_elf_proof.json compares all13 actual instruction encodings across the
archived ELF and both new software ELFs. Original target PC0x10600,
SoC0x8000071a, Spike0x8000077a; opcode30803c57,
vrgather.vi v24,v8,0,v0.t. It is OPIVI unsigned immediate0, not VX0.

The original unused index load and mv t3,a6 are retained. a1 points to ordinary
indices, not indices16; a6/t3 remain0. The target instruction selects immediate0
independently of GPR data, although this faithful prefix itself only covers
scalar-slot0 and does not measure behavior with nonzero t3.

Independent execution of the original64-bit xorshift13/7/17 yields e8 source0=185
and source31=177. All66 actual raw v8..v15 groups match the entire1024-byte
source fixture and record actual_source0=185. No VX PASS is used as a value,
encoding or timing substitute. The unused v16 group,1024-bit predicate,
old destination and every post-target result/store are also checked.

Active selected values are185; prestart, inactive and tail remain91.
The66 calls contain780 active selected elements and66804 preserved elements;
both guards remain91. Raw CSR checks require vtype3, requested VL/start,
the three vset returns per helper and returned-vstart0.

## Measurements and Negative Tests

| Observation | Measured |
| --- | ---: |
| Calls / each of13 instructions |66 /66|
| Scalar result checks / guards |67584 /132|
| Unique actual LBU result/guard reads |67716|
| Returned-vstart / vset checks |66 /198|
| Actual setup values per call |4226|
| Full vector inputs/results/stores, each |66|
| Firmware retired through successful HTIF store |2881705|
| Spike wall time / exit |4.781531983s /0|
| Full raw commit bytes |189056398|

Exactly one restart-gold Spike execution used120s/5M-retired/768MiB-per-file
limits. Binary SHA c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2.
No timeout increase or retry. Full raw reference/commits.log is retained,
SHA03682ef8fc09125b3dc66e0a142d32d3c4dece8a99343c1512730e4fe3056620.
reference/reference.json retains actual per-call arguments, targets, source0,
CSR and reconstructed console; host_expected.json retains complete fixtures.

The checker validates complete input/setup bytes, actual vectors, all1024
vector-store address/value pairs and all1026 scalar oracle reads each call.
Missing bytes/checks, unexpected trap, wrong encoding, nonzero exit or raw
DETAIL/FAIL reject. Exact PREFIX66/BOARD success and HTIF value1 are mandatory.

Host9 consists of one positive and eight detected negatives: active, prestart,
inactive, tail, guard0, guard1, returned-vstart, and wrong VI31 output177.
The VI31 substitution produces the authentic first-error line at VL1/start0,
element0: expected185 actual177. Prestart and tail injections use nonempty
VL2/start1 and VL1/start0, respectively. Host mocks test the original C oracle,
not DUT behavior.

audit01/audit.json is an offline recheck of the same reference plus seven
corrupted trace fixtures: wrong byte, invalid target encoding, valid-but-wrong
VI31 encoding, valid-but-wrong VX0 encoding, returned-vstart, missing source
byte and incomplete oracle. It does not invoke Spike again. READY.json binds
its completed status. No earlier diagnostic output is overwritten.

| Prepared software ELF | SHA256 |
| --- | --- |
| soc01/gather_prefix_e8_m8_ops2.elf | b82305d1bad45e57c70c28ed7a76b25713a943481a957bc99cada9292522e6b6 |
| spike01/gather_prefix_e8_m8_ops2.elf | b90a3ea7626e034abb7eb1d1f42d2d6528e56e2c0af9de78ad52233ba790eedf |

Spike uses its reference runtime, not the SoC ELF. All13 helper bytes match
the original; no byte-identical rebuild of the entire Linux program is claimed.

## Cost and Seal

2881705 retired at earlier M5 rates687..683/s estimates4195..4219s.
At conservative273/s:10555.70s, or12666.84s with20% margin, above3h.
These estimates are not measured VCS throughput for VI0. They do not authorize
a longer timeout, DUT launch, or transfer VX/VI31 acceptance.

READY.json pins all owned artifacts. baseline_pins.json binds282 unchanged
original/tool/helper/reference files, including e8 VX/VI31 and e16 references,
plus the static VI0/VX0 selection note. Independent Averroes source/reference
review follows this handoff; any later DUT work requires separate admission.
