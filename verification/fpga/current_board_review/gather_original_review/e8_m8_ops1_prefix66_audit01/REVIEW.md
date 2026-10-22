# Independent e8/m8/op1 Prefix66 Source And Reference Audit

Date: 2026-10-11. Audited sibling `e8_m8_ops1_prefix66_prepare01` read-only.
Only this report was created. No preparation, build, Host/Spike execution, DUT
launch, simulator-status query, or sealed input edit was performed. Offline
parsing of existing traces is not a new simulation.

## Decision And Limit

**Source and Host/Spike reference accepted; no source/oracle blocker found.**
This is not DUT admission. At the stated conservative273 retired/s, the actual
2,745,395-retirement cost implies10,056.39s; with20% time margin it implies
12,067.67s, exceeding3h. No timeout increase, prefix reduction or oracle reduction
is approved by this review. Budget/resource/runner admission needs a separate
parent decision. The nominal estimate is not measured performance of this case.

The archived child has2688 calls and no identified stopped tuple. This natural
66-call source prefix is not an exact historical-stall reproduction, full-child
acceptance, parent-matrix acceptance, or Linux closure.

## Identities And Provenance

Original child:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01/release/binaries/rvv_permute_restart_e8_m8_ops1`.
Scene/report:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery08_171/terminal_scene/`.
The shared original C is retained from
`rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c` within that
campaign. The e16 directory name does not select this child: its original
partition assembly/header and SEW8/restart/op-mask2 build definitions do.

| Artifact | SHA256 |
| --- | --- |
| Original shared C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original Linux child ELF | `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf` |
| SoC ELF | `791d817193c9b46eec48e6feee8b1d9c8ecf289b588253b21c1f59a54314d2c6` |
| Spike ELF | `b0c09970aa48d9c96951f5e724cacfcabbb25eb7a32c009ff35d5048b346298b` |
| Final READY.json | `d05ff6b45d69a05b41d3558aa5e8d148cfd085b6f17f017a5b81b6cf78006af3` |
| Baseline pins | `360ac308bb26627b35e0db6a9e31fb8cfa86ebafbc3a0fee51964a98afd6995a` |
| Source/ELF proof | `b0c456ac9fe56c01931e55e9f45b9182a3fc573866ec637031e83bf295d64a05` |
| Host expected model | `7aa7ff8dd987d51508dfbc8d32097e1ac05d698437596431708beac862878bea` |
| Host gate | `aeed5fbe77bcf6cacf9cc83b872ff161941338fadc894d05a0ca84cf4a7cb2b8` |
| Raw reference report | `d67980f7b02df28317ec8745535a9901d82433cf64a95f823336d22308f728c4` |
| Raw commits | `5142c4d33cc38de9ac62c057f557d683e35e5ed1c960d18eff3bfde439a3fd3f` |
| Producer audit02 report | `acb8f69e04acbf34e1baf6d5f1e59816b69e29718a8a5d5614d35c83c46fb58d` |

Independently verified all85 baseline pins, all9 prepared-provenance hashes and
all69 final READY evidence pins, including the existing e16 reference dependencies.
Rehashed both ELFs, Host logs, reference linkage and raw commit log. Re-disassembled
the archived13-instruction helper window and both ports: all proof records match
actual bytes. Full original Linux binary rebuild equivalence is not claimed.

The SoC and Spike case-C objects are byte-identical (SHA256
`fb7644f3f9fb9e817f6be945ce23af50227535551a1419d86389db8ae91d8b86`),
as are their assembly objects (SHA256
`a21e3c89b8a4dd1fab319cc216c7b25c315c1fa8bcb101f488a4e890ec6420e9`).
The separate runtime/link variants produce different ELFs; Spike did not run
the SoC ELF itself.

## Source Sequence And Oracle

Reconstructed actual adapter/prefix diffs and matched the retained diff files.
The port changes Linux startup/output/exit plumbing and omits TIOCOUTQ; the prefix
adds its stop only after call66's complete scalar oracle, both guards and count
increment. It also requires exactly66 calls and uses prefix-specific markers.

All65 prior vector calls remain. Original loop order, seed0 xorshift initialization
with shifts13/7/17, all1024 source elements, masks, old-vd91, full-capacity loads
and stores, and scalar oracle remain intact. E8 data/indices use original byte
truncation; indices16 retains the original untruncated16-bit values. Disabled-op0
iterations have no vector helper/RNG effect and are not fabricated predecessors.

Actual helper remains e8/m8/tu/mu: fullcap source/index/old-vd loads, mask load,
target VL setup, scalar move, vstart write, masked gather, returned-vstart read,
fullcap VL restore and fullcap result store. Target opcode is `308e4c57`,
`vrgather.vx v24,v8,t3,v0.t`: archived PC0x105dc, SoC PC0x800006fa,
Spike PC0x8000075a. All13 instructions execute66 times.

Trial66 is source tuple `[seed,op,scalar_index,length_index,mask_mode,trial] =
[0,1,0,4,0,1]`: cap1024, VL512, start256, scalar0, all-on predicate. Independent
expected output is91 for elements0..255,185 for256..511, and91 for512..1023;
both guards remain91 and returned vstart is0. Trial65 is the same VL/scalar/mask
with start1. Neither is claimed to be the archive's unknown stalled tuple.

## Actual Evidence Rechecked

The retained Host report/logs establish one positive exit0 and seven corruptions
rejected with exit1: active, prestart, masked-off, tail, guard0, guard1 and CSR.
As with the e16 preparation, prestart/tail negatives share the first VL0/start1
element; they are not two independent nonempty-body boundary tests. This does
not weaken the real program's complete result checks.

Pure read-only re-parsing of the full raw Spike trace exactly reproduces every
field of the recorded reference result. An additional independent vector/CSR
parser checks the actual input/index/old-vd registers and all1024 predicate bits
at every target, then all1024 result bytes and all1024 vector-store values. It
also verifies target-entry vstart, actual vset scalar returns/VL updates and
vstart reset. No acceptance rests on console markers alone.

| Observation | Verified value |
| --- | ---: |
| Calls / each original helper instruction | 66 / 66 |
| Full helper retirements | 858 |
| Source/setup values checked per call | 4226 |
| Independent full1024 input/mask/old-vd, result and store checks | 66 of each |
| Fullcap/target/fullcap vset results | 66 of each,198 total |
| Returned vstart0 | 66 |
| Scalar result checks | 67,584 |
| Scalar guard checks | 132 |
| Distinct scalar output/guard loads | 67,716 |
| Actual target VL distribution | 0/1/2/3:16 each;512:2 |
| Firmware retirements through successful HTIF store | 2,745,395 |
| Last target retirement | 2,728,269 |
| Recorded Spike elapsed / process exit | 4.530458820s / 0 |
| Observed HTIF value | 1, successful firmware exit |
| Raw commit bytes | 177,751,012 |

ISA remains `rv64gcv_zvl1024b`; the pinned restart-capable Spike is SHA256
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
The existing5M-retirement/120s/768MiB limits were not increased. Exact PREFIX66,
case PASS and BOARD_REPLAY_PASS are reconstructed from raw stores, with no failure
text. CSR coverage here is original returned-vstart plus reference VL observations,
not invented additional fflags/vxsat testing.

## Audit01 Versus Audit02

Audit01 must not be reported PASS. Its missing-oracle fixture ended before the
per-call finish check and correctly raised `Incomplete calls/asm/oracle/exit`,
where the harness expected `Missing oracle/guards`. The failure note and original
fixtures are preserved. This is a diagnostic expectation mismatch, not an accepted
bad trace or evidence of a DUT failure.

Audit02 changes only its fresh output directory and that expected rejection text
(plus trailing whitespace). All five fixtures are byte-identical to audit01 and
their recorded hashes match. Independently re-parsed those original fixtures:
wrong output, wrong target encoding, nonzero returned vstart, missing initialized
source bytes, and incomplete oracle all reject for the recorded reasons. The
reference checker, source, ELF, positive trace and numerical oracle did not change.

Final producer audit02 and READY evidence agree with this independent recheck.
**Reference accepted; no DUT launch approval or full historical closure.**
