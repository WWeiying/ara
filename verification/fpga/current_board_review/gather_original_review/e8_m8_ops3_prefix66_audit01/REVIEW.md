# Independent e8/m8 vi31 Prefix66 Source/Reference Audit

## Decision

**ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT.** No source/reference blocker found.
This accepts the natural 66-call prefix, not the full 2688-call child, original
Linux execution, exact historical stopped tuple, or any DUT launch/budget.
No DUT, build, Host/Spike rerun, live query, or sealed input modification occurred.
The independent auditor parsed the new raw once; prior raw files were only hashed.

## Identity and Source

Reviewed preparation: `../e8_m8_ops3_prefix66_prepare01/`.
All 62 evidence pins and 218 baseline pins match actual files. READY SHA256:
`b15c7b86fa273aacbc464dca171a3cee3bc4140e701ed639ef70d7cc9aee5388`.

| Artifact | SHA256 |
| --- | --- |
| Original partition ELF and recovery173 scene ELF | `ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c` |
| recovery173 report | `1ca4e0f534d0fb804f94ba8e127a32945eb45a6de4b2bd8ab8d6ac40848ba50d` |
| Original shared C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original operations.S | `6210a2d96c74a3d15b331b1aeff3d2a1eef01fc64d7becafbc53a042b3460824` |
| SoC ELF | `88b154a9a1c68f2a25706eb7b8587237335b34d3bc69590f970fec0074fca841` |
| Spike ELF | `83045b87c11b79d8e5b53202cca094ce5380c13abe33a76ee518c25b55baf9bf` |

Archive root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Exact child: `rvv_permute_partitions01/release/binaries/rvv_permute_restart_e8_m8_ops3`;
scene: `rvv_recovery08_173/terminal_scene/`. The retained C/header/assembly match
the manifest/source copies. Disassembly independently matches all 13 helper
encodings in the original, SoC and Spike ELFs, not merely assembly text.
This is helper byte identity, not a byte-identical complete Linux rebuild.

The independently reproduced source diff contains only established baremetal
startup/I/O/exit adaptation and the stop after call66's full scalar oracle and
guards. SEW8, restart enabled and operation mask8 select op3. Original RNG,
initialization, loop order and 65 predecessors remain. Disabled ops0..2 retain
2688 source-level empty iterations; those are not vector predecessors. No added
warmup or substituted vx target. Raw OP-V PCs show only the original capacity
vset once, the three helper vsets 66 times each, and the target 66 times.

## Independent Raw Findings

[audit.py](audit.py) reconstructs 64-bit xorshift13/7/17 with wrapping, byte input
and ordinary indices, separate 16-bit indices16, masks, starts, and full oracle
without calling the producer model/parser. Its model also matches the static
Host shim arrays. [audit.json](audit.json) preserves the per-call ledger.

| Actual observation | Independently checked |
| --- | ---: |
| Calls / each original helper instruction | 66 / 66 |
| Full-capacity result bytes / guards | 67584 / 132 |
| Unique scalar LBU oracle reads | 67716 |
| Returned vstart zero / vset return and CSR checks | 66 / 198 |
| Initialized values per call | 4226 |
| Full input/index/old-vd/predicate, result and vector-store checks | 66 each |
| Active selected bytes / preserved bytes | 780 / 66804 |
| Firmware retired through successful HTIF store | 2621149 |
| New raw bytes | 165411158 |

Raw SHA256: `3f6fe246594f6957d8fa61b07598ff600673b093d74995f7f4e31777cabb64c0`.
Target `308fbc57` decodes masked `vrgather.vi v24,v8,31,v0.t`, unsigned imm31.
Original PC `0x1063e`, SoC `0x80000758`, Spike `0x800007b8`.
Actual call a1 points to ordinary `indices`, not `indices16`; a6 and t3 are zero.
All targets have requested VL/vstart and vtype3 (e8/m8, tu/mu), followed by
vstart0. Full source v8..v15, unused indices v16..v23, old/result v24..v31 and
1024 mask bits were checked. Each final store contains all 1024 ordered
address/value pairs, followed by every result and both guards read by the C oracle.

**Actual input[31]=177, input[0]=185.** This is fresh byte-width raw evidence,
not the earlier e16 value. Active results require177, including VL below32;
source bounds are capacity1024, not active VL. Wrong vx0 would return185;
incorrect out-of-VL zero would return0. Prestart/inactive/tail and guards retain91.
Element31 is byte31 within the first 128-byte architectural register v8;
static four-lane EW8 mapping is lane3/local-word0/byte7, not a register boundary
and not a measured RTL lane waveform.

Endpoint call66 is tuple `[0,3,0,4,0,1]`: seed0/scalar-slot0/VL512/mask0/start256.
Its raw target is line2605820, retired2605815; active elements256..511 are177.
Call65 is the genuine predecessor VL512/start1 (511 active bytes). The earlier
64 calls retain the original VL0/1/2/3 and all four mask modes/trials.

Console reconstructed from raw stores exactly matches runtime.log, with one
PREFIX66 success, one BOARD_CASE_PASS and one BOARD_REPLAY_PASS, no DETAIL/FAIL/
TRAP/MISMATCH. Successful HTIF value1 and recorded process exit0 both checked.
Recorded Spike elapsed4.227606456s; ISA `rv64gcv_zvl1024b`; existing restart-capable
Spike and the 120s/5M-retired/768MiB limits are pinned. Spike used its reference
ELF, not the distinct SoC runtime ELF.

## Negatives and Limits

Read retained Host results, logs, shim and pins: one positive exit0 plus seven
negatives exit1, each still completes66 calls. Active corruption: VL1/start0,
element0,177->176; nonempty prestart: VL2/start1,element0,91->90; inactive:
VL1/mask1/start0,element0,91->90; nonempty tail: VL1/start0,element1,91->90.
Both guards and returned-vstart negatives also fail the original C oracle.
Five pinned offline corrupted traces are recorded rejected: wrong byte, target
encoding, nonzero vstart, missing source bytes and incomplete scalar oracle.
These stored tests were audited, not rerun; they are not DUT results.

Historical triage records last PC0x1063e/head0x10642 and `last_trial=null`.
The opcode family is genuine; call66 is not proven to be the historical stall.
No extra recovery168 process history is imported. Later scalar slots/seeds,
VL1023/1024, and later VL512 masks/trials remain outside this natural prefix.

Cost: 2621149 retired / measured-comparable 687..683 retired/s estimates
3815..3838s. Conservative273/s gives9601.28s; plus20% is11521.53s, **over3h**.
These are estimates, not this case's DUT throughput. Preparation acceptance
does not authorize enlarging a timeout, shrinking the oracle or launching DUT.

Audit JSON SHA256: `42aee537c6eacce6f968c21e77d7e3ed77910b1cb69f51c51d7af5e5920817b9`.
Auditor SHA256: `da4a9f22f6e3c187de660e98a4edec5b5347bb7b651111e6f87117f5f7e79294`.
