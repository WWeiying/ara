# Bounded Original Partitions And Candidate02 Handoff

## Terminal Candidate02 Acceptance

**Six bounded source partitions PASS on candidate02**, independently accepted
by the standalone strict terminal checker after completion. Tuple stage3/3 and
prefix stage3/3 are COMPLETE, with the exact six names, all statuses PASS and
runner exits0. This is **262 distinct original trials**, or265 calls including
the three repeated exact tuples, not three complete5376-case parent matrices.
It is candidate02 evidence, **not candidate03 acceptance or original Linux
closure**. No new RTL fix or internal root-cause proof is inferred from PASS.

| Shape | Tuple result / cases / seconds | Prefix result / cases / seconds |
| --- | --- | --- |
| e8/m4 | PASS /1 /68.65 | PASS /98 /2227.38 |
| e8/m8 | PASS /1 /106.47 | PASS /66 /2688.33 |
| e16/m8 | PASS /1 /61.31 | PASS /98 /2490.03 |

Sequential runner wall times:240.668688 seconds for tuples and7489.963443
seconds for prefixes. Each case completed within its300/6000-second inner
budget. These are host simulation timings, not RTL performance comparisons.

Evidence: [original terminal record](vcs_candidate02_01/complete.json) and
[independent strict postcheck](terminal_audit01.json). The latter retains raw
per-case success lines and console/ELF hashes. Every console has its exact
SEW/case-count/errors0 marker, case/replay success, historical VL512/vstart256
marker and `Core Test *** SUCCESS *** (tohost = 0)`; no failure/trap/fatal
marker survives the mandatory veto. All119 plan pins, prepared files, reviewed
ELFs/private inputs, actual command/image identities and snapshot-ledger binding
passed verification with zero mismatch. No process/service polling or new
simulation was used for this terminal postcheck.

- Candidate02 image ledger SHA256:
  `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`.
- Terminal complete.json SHA256:
  `83364b4221aaa84d5bd7d5e41ce566413359cac76b2df00f1afff6404de5940c`.
- Standalone checker SHA256:
  `09cb120e4a551da718a2ae01ed39d0df65473f2718af5610074efb83fb8a5649`.

## Retained Preparation And Launch History

The initial reference status was six partitions HOST + SPIKE PASS, NOT DUT
PASS; the later startup confirmation also did not establish acceptance. The
terminal checks above now supersede those pending statements. Original full
matrices, prepared01, bounded01 and launch evidence remain unchanged. No RTL
modifications or full-matrix DUT replay were performed.

## Exact Partition Boundary

The historical last printed `VL512/vstart256` tuple is source-derived:
seed=0, raw_op=0, mode=0 (predicate bytes ff), start-choice=1,
target `vmand.mm v8,v8,v16` / opcode `66882457`.
Historical records establish stalls, not numerical mismatches or a captured
last internal acceptance. See [original provenance](README.md).

| Original suffix | Prefix original zero-based trials (inclusive) | Executed configurations | Exact tuple original trial |
| --- | --- | ---: | ---: |
| e8_m4 | 0..97 | 98 | 97 |
| e8_m8 | 0..65 | 66 | 65 |
| e16_m8 | 0..97 | 98 | 97 |

`partition.py` changes only four loop headers in the existing full-source
port: seed and raw_op stop after zero, length/mode/start loops end immediately
after the historical tuple. Tuple partitions also begin at that exact length
and start-choice. Selection is in loop bounds, before scalar setup/oracle;
there is no expensive full-matrix filtering loop.

Prefix partitions retain every preceding original operation call and its
order, input generation, source loading, predicate setup, output poisoning,
register assignments, vstart writes, result stores and scalar checks. Every
cap bit, original guard and returned-vstart check remains. Archived assembly
is byte-identical. Compiler addresses/timing and Linux UART drain behavior
are not preserved. Tuple-only partitions omit predecessor state and cannot
replace prefix acceptance. The three tuple calls overlap the prefix coverage;
265 total calls across six ELFs represent 262 distinct original trials.

Each `bounded01/prepared/<name>/partition.diff` records only the loop changes;
`runtime_adaptation.diff` retains the earlier Linux-to-runtime adaptation.
[partition_provenance.json](bounded01/partition_provenance.json) binds original
source/ELF/report identities, full prepared parent and exact interval membership.
The original complete 5376-case matrices are retained but are **not launched**.

## Reference Checks And Cost

| Suffix | Prefix Spike instructions | Tuple Spike instructions | Prefix / tuple Spike seconds |
| --- | ---: | ---: | ---: |
| e8_m4 | 1821876 | 33593 | 0.317 / 0.034 |
| e8_m8 | 2183688 | 57275 | 0.368 / 0.034 |
| e16_m8 | 1872552 | 37161 | 0.317 / 0.035 |

ISA `rv64gcv_zvl1024b`; runtime/toolchain match prepared01. The original-source
nonzero-vstart model acceptance is inherited from the pinned full reference.
All six require original error=0 and correct case-count markers, wrapper
success, historical printed tuple and successful firmware exit.
Counters measure Spike instructions to replay_exit, not RTL cycles.

All 18 host runs passed (six partitions, three permitted tail policies).
Input hashes and complete invocation ordering match independently generated
original rows AND retained prepared01 full host log slices. All 30 negative
checks are rejected by the unchanged original oracle: six per prefix and
four per tuple (active, prestart, guard, returned-vstart). No-body and tail
negative checks are included in prefixes, not fabricated for a no-tail tuple.
See [host status](bounded01/host/status.json) and [reference results](bounded01/status.json).

## VCS Budget

Planning calibration uses earlier actual multi-case SoC observations:
[NF2](../masked_translation/segment_review/sv39/DUT_REPORT.md) ran 1189205
reference instructions in 1590.94 simulation seconds; the previously supplied
extended8 observation was 740000 instructions in 1200 seconds, recorded in
[VCS_ADAPTER.md](../masked_translation/segment_review/sv39/VCS_ADAPTER.md).
These imply about 617..747 instructions/s, not a guaranteed alias throughput.
The candidate02 arithmetic matrix replays separately took approximately
453..1026 seconds for extension matrices; those are different workloads,
not evidence that a full historical alias matrix fits a similar budget.

| Suffix | Estimated prefix seconds | Estimated tuple seconds |
| --- | ---: | ---: |
| e8_m4 | 2437..2954 | 45..55 |
| e8_m8 | 2921..3541 | 77..93 |
| e16_m8 | 2505..3037 | 50..60 |

Fixed inner budgets: **300 seconds per tuple**, **6000 seconds per prefix**
(100 minutes, below the authorized 3-hour/ELF limit). Workload/host variation
remains possible; a timeout is not automatically an RTL failure. No automatic
budget adjustment or retry. Overall sequential service outer limit is
19800 seconds, exceeding 3*300 + 3*6000 = 18900 seconds plus teardown margin.
Only three tuple PASS results unlock prefixes; a failed stage stops the chain.

## Launch Identity And Capacity

Authorized service: `ara-mask-alias-candidate02.service`.
Output: `mask_alias_original/vcs_candidate02_01`.
Collision check before launch: service not-found/inactive, output absent.
One slot, jobs=1 throughout; NF7 retains two reserved slots. Existing external
processes are not stopped or modified. No full-image build or full-matrix run.

Earlier inventory showed at least13 external RCE simv processes and was
initially refused under a self-imposed eight-slot assumption. Parent explicitly
superseded that assumption with **24 total live/reserved simv** and **at least
32 GiB available memory**. This scheduling-only change did not alter software,
ELFs, test membership, oracle, or budgets. No autonomous capacity retry occurred.

One fresh gate under the new authorization recorded **12 live + NF7 reserved2
+ alias1 = 15/24**, **172.6689 GiB available**. The accounting conservatively
adds both NF7 reservations even if some are already among live processes.
See [resource_gate.json](vcs_candidate02_01/resource_gate.json).

The fixed [run_candidate02.py](run_candidate02.py) invokes the proven
`integration/run.py` checker, with fresh tuple/prefix output subdirectories.
The runner rechecks prepared/ELF, image, snapshot and compiled-source identity,
and requires original/full-partition oracle completion. The wrapper adds only
one-shot capacity checking, fixed stage order and a strict three-PASS gate.
There is no generic scheduler, recompile, retry, or external-process control.

| Pinned artifact | SHA256 |
| --- | --- |
| candidate02 image.json | 384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810 |
| candidate02 actual simv | 6fcdf53ecf2df4526e9d35372ea6bf9d2c49fdd2fc7a6bc3b57044124aeb13b7 |
| bounded01/soc/programs.json | daf65942945329b9d2ee3a846ed9f4674de05c32feead6c3257e894ccb43a397 |
| bounded01/partition_provenance.json | 73a1c488d75082ab0cd901f8f3d7e59e529372b147728caec4c77b5a713d3dc1 |
| integration/run.py | c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78 |

Exact six SoC ELF hashes are in [programs.json](bounded01/soc/programs.json);
source/helper/image pins and scheduling configuration are in
[plan.json](vcs_candidate02_01/plan.json). Service launch returned0. One actual
process observation confirmed **PID4014768**, candidate02 image's
`campaign/image/_build/vcs/simv`, running `rvv_masks_alias_restart_e8_m4_tuple`
with the fresh output input. Full argv/cwd are retained in
[actual_simv_confirmation.json](vcs_candidate02_01/actual_simv_confirmation.json).
No further polling was performed. Startup confirmation alone was not DUT
PASS; the subsequently completed strict terminal acceptance is recorded above.
