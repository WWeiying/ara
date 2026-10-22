# Independent e16m8 ei16 Prefix98 Reference Audit

2026-10-11. **ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT. No blocking finding**
in the frozen source/Host/Spike preparation. This is not DUT launch approval,
measured DUT performance, full2688-child acceptance, or original Linux closure.

Reviewed preparation: `../e16_m8_ops20_prefix98_prepare01/`.
READY SHA256: `1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149`.
All62 evidence pins and85 baseline pins matched their actual files before
parsing. Original files, shared helpers and prepared inputs were not changed.
No Host/Spike rerun, software/image build, DUT execution or live e8/48 query.

[audit.py](audit.py) independently reconstructs the oracle and parses the full
existing raw trace once. It does not call the producer's `model()` or
`audit_trace()`. It uses the existing pure source-adaptation helpers only to
check the exact C transformation; objdump reads existing ELFs. The full trace
hash is also checked within that single parse. [audit.json](audit.json) retains
every call's tuple, target retirement/line, terminal index and OOR count.

## Original Identity and History

Campaign root is `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Original child `rvv_permute_restart_e16_m8_ops20` is bound by
`rvv_permute_partitions01/manifest.json`, its `operations.S`/`operations.h`,
`release/binaries/rvv_permute_restart_e16_m8_ops20`, and recovery178's scene
ELF/report. Manifest selects SEW16/m8/op20, configurations2688. Archived
`last_trial` is null; last printed DETAIL after a returned VL256/start128
call does not identify the subsequent unreturned/stalled call.

| Identity | SHA256 |
| --- | --- |
| Original partition/scene/copied Linux ELF | `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888` |
| Original shared C, also manifest's permutation_oracle.c | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original operations.S | `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` |
| Original operations.h | `886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4` |
| Prepared SoC ELF | `c4d681ad58bf1e46e121ffc3c3652cabc1b2a62100fc3987012c502e53fc89fd` |
| Prepared Spike ELF | `893422ed87ef3a2fcc91440ea9c9fd57b0f4284c794087d6884fcda6f2844181` |

The copied original C is unchanged. Recomputed adapter and prefix diffs exactly
match the retained diffs and prepared C. Changes are the established Linux
startup/output/exit adapter and a stop **after** call98's full result and guard
oracle; prefix result naming is explicit. The omitted Linux output-drain call
was only in op0's diagnostic branch, not this selected op20. Original loop,
RNG, input/index/predicate/output initialization, oracle and error accumulation
are retained. The source still contains disabled ops0..19's17920 empty loop
iterations; these are not vector predecessors or an invented warmup.

Actual calls retain all97 vector predecessors: seed0/scalar-slot0, VL
0/1/2/3/256/511 each16 times, followed by VL512 twice. Masks and restart trial
order are unchanged. Call98 is `[0,20,0,6,0,1]`, VL512/start256/mask0/scalar0.
The independent xorshift13/7/17 reconstruction agrees with every prepared
input/index and every row of `host_expected.json`, not just its digest.

Actual disassembly of the original, SoC and Spike ELFs contains one matching
13-instruction selected helper each. Target is opcode `38880c57`,
`vrgatherei16.vv v24,v8,v16,v0.t`: original PC0x10994, SoC0x80000aac,
Spike0x80000af8. All setup loads, unused scalar move, vstart write/read,
fullcap restore/store and ret encodings match. Actual a1 is the `indices16`
symbol, not the separate ordinary `indices` symbol (their values happen to
match at e16). These are source ports, **not** byte-identical rebuilds of the
entire original Linux ELF. The actual reference runs the Spike runtime ELF,
not the SoC runtime ELF.

## Independent Raw Results

Trace `reference/commits.log`:137442674 bytes, SHA256
`b3e3f0ed6de57569f11038ec552be1da278b38440504469381fa4c311274a860`.
Single full raw parse completed successfully on its first invocation.

| Independently checked actual observation | Count |
| --- | ---: |
| Calls and target retirements, with exact original order/arguments | 98 |
| Each of13 helper instruction retirements | 98 each;1274 total |
| Initialized scalar input/index/index16/predicate/output values | 2178 per call |
| Full512 input/index/old-vd vectors and low512 predicate bits at target | 98 groups |
| Complete512-element target result vectors | 98 |
| Complete512-element vector-store addresses and values | 98 |
| Scalar result checks from actual LHU loads | 50176 |
| Scalar guard checks from actual LHU loads | 196 |
| Distinct result/guard loads, exactly once per element/call | 50372 |
| Fullcap/requested/fullcap vset return and actual VL/vtype state | 294 |
| Target-entry actual vstart and post-target reset/returned-vstart0 | 98 each |
| Firmware retirements through successful HTIF store | 2134409 |
| Last target retirement | 2122012 |

The independent parser checks actual register groups before and after target,
including no-op calls where no destination register update is emitted. Exact
tu/mu91 preservation is required for prestart, tail and inactive elements;
the golden result is reconstructed from original input/index/mask, never from
the DUT/reference destination. Upper unused mask bits are not overconstrained.
The archived oracle checks vstart, not additional fflags/vxsat conditions.

All target retirements/trace lines agree with the producer's recorded call
details. Reconstructed raw console exactly matches `runtime.log` and
`reference.json`, with exactly one each of PREFIX98/errors0, case PASS and
BOARD_REPLAY_PASS. No FAIL/TRAP/MISMATCH/DETAIL or misleading full-child
RVV_PERMUTE_PASS appears. Actual HTIF store value1 denotes successful firmware
exit; recorded Spike process exit is0. Neither marker alone is the acceptance.

## OOR and Data Terminals

These are **actual architectural reference** checks, not observations of RTL
request FIFOs or internal no-data tokens. Of98 target calls,60 have an empty
architectural window (`vstart>=VL`);38 have a nonempty window. All-off masks
are still nonempty windows for this classification, not proof of data requests.

- Eight nonempty-window calls have terminal OOR index512:65/66,69/70,73/74,
  77/78, all VL256, starts1/128, covering all four mask modes.
- Thirty nonempty-window calls have an in-range terminal index; these include
  VL1/2/3/511/512. Exact call lists remain in audit.json.
- Call66: target retirement1426615, VL256/start128/all-on, index[255]=512;
  actual final result0, and44 selected active OOR elements all correctly zero.
- Calls69/70's odd mask selects element255, so its OOR result is0.
  Calls73/74's sparse mask and77/78's all-off mask leave element255 at91.
- Calls97/98: VL512/start1 or256/all-on, index[511]=1, actual final result538
  equals original input[1]. Call98 contains85 selected active OOR indices,
  independently checked as0 while the in-range results and full prefix remain
  exact. It is not a constant-source substitute for ei16.

Thus both OOR-terminal and data-terminal architectural cases are present and
complete. A later DUT test still needs to establish its own forward progress;
Spike PASS cannot prove the RTL no-data/end-token protocol.

## Host and Negative Evidence

Existing Host8 and offline-negative5 reports/logs/fixture hashes were inspected,
not rerun. Host positive has98 calls/errors0/exit0. All seven injected runs have
98 calls, INJECTED1, PREFIX_FAIL/errors1 and recorded exit1. Raw DETAILs locate:
active at VL1/start0/element0; prestart at VL2/start1/element0; inactive at
VL1/start0/mask1/element0; tail at VL1/start0/element1. Prefix and tail negatives
are therefore distinct nonempty-body cases. Guard0/guard1/vstart failures are
also recorded. Host mocks test the original C oracle, not a hardware execution.

The five retained raw negative fixtures report rejection for wrong halfword,
target encoding, nonzero returned-vstart, missing initialized source bytes,
and incomplete oracle. Their report hashes agree with actual fixtures. This
review does not relabel those stored executions as newly run independent tests.

## Cost and Limits

Recorded reference ISA is `rv64gcv_zvl1024b`, using the pinned restart-capable
Spike SHA `c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
Actual execution command agrees with `command.json` and uses the pinned Spike
ELF. Recorded elapsed3.476708207s/exit0; limits remain120s,5000000 instructions,
768MiB per output file. This audit did not rerun any command from that manifest.

Measured reference retirement cost2134409 yields the following **estimates**:
3106.85..3125.05s at prior M5 rates687..683 retired/s;7818.35s at273/s;
9382.02s with20% margin at273/s. This is under3h but exceeds9000s. There is no
measured VCS duration for this prepared case here and no guaranteed completion
bound. A runner/timeout/resource/pin review is separate from reference acceptance.

Remaining scope: exact historical stopped tuple unknown; only first98 of2688
child calls, only seed0/scalar-slot0; fullVL512 sparse/all-off cases and later
seeds/scalars are outside this prefix. No full parent/Linux acceptance, DUT PASS,
or claim that every original stall shared the fixed gather origin cause.

Audit result SHA256:
`5fd1d2e3add1f801d1d8f3ad9cd708848b41f445080ff63629231cc49897ae79`.
