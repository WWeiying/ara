# Original RVV-02 Arithmetic Restart Prefixes

**READY: host + Spike only. No DUT launch, RTL edit, or full-matrix acceptance.**
Five contiguous original prefixes contain 262 distinct original configurations.
These are arithmetic `vadd.vv` prefixes, unrelated to the separately accepted
262 mask-alias trials. The broader original 22 whole matrices remain pending.

- SoC runner input: [prepared02/soc/programs.json](prepared02/soc/programs.json).
- Reference and exact ELF identities: [prepared02/status.json](prepared02/status.json).
- Independent pins, boundary/PC audit and budget: [readiness01.json](readiness01.json).
- Original 22-shape source/ELF/command inventory:
  [original_identity.json](prepared02/original_identity.json).
- Frozen sources/runtime and file hashes:
  [prepared provenance](prepared02/prepared/provenance.json).

## Historical Identity And Limits

Archive root:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
The original matrix is `rvv_extended04/manifest.json`; original generation used
`rvv_matrix/build.py` and `oracle.c`. `rvv_matrix/ISSUES.md:19` records 19 passing
shapes and three no-retirement failures, not three numerical mismatches.
`rvv_extended04/report.json`, `m8_report.json`, `resume02_report.json`,
`resume03_report.json`, snapshots and `HARDWARE_FINDINGS.md` preserve the board
history. Some initial reports retain `running`; do not relabel those raw files.

| Original ELF | SHA256 | Selected boundary evidence |
| --- | --- | --- |
| rvv_matrix_e8_m4 | `5b77ae16b4316cb33e507d488103b9a31a12db6e371e60cec95092858f382ad8` | Shape stalled; later trace explicitly confirms trial55 |
| rvv_matrix_e8_m8 | `ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f` | Shape stalled; trial37 is source-derived prediction, not a captured tuple |
| rvv_matrix_e16_m8 | `68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d` | Shape stalled; trial55 is source-derived prediction, not a captured tuple |

The drained e8/m4 diagnostic ELF in `rvv_trace02/overlay/opt/ara-tests/` has
SHA256 `00b5b0915c06221afe5432044f3824ab89e347c9ec2d93d515a18f46a2685c1b`.
Its assembly is byte-identical to extended04 e8/m4. All 56 printed tuples match
the selected prefix, ending at `seed0/op0/VL512/mask0/vstart256/completed55`.
This is a pre-call trace followed by no retirement, not an internal handshake
capture. Linux tty-drain timing is not reproduced by the bare-metal port.

### C Recovery Evidence

Old C text bytes were not found beside the archived manifests. The current
successor `oracle.c` has changed, so it was not falsely labeled the old source.
`recover.py` reconstructs the original basic C from its surviving functions
and original basic loop/oracle structure. With the **original manifest compiler,
flags, archived assembly and header**, all **22 complete Linux ELFs rebuild
byte-for-byte to their original SHA256**, not merely equivalent disassembly:
[recovery22/report.json](recovery22/report.json).

- Manifest original C hash: `b2c21801fc8186d30fbe67d23f31bf5fb89dde1f838314e93c1224b6fdc58c44`.
- Reconstructed C hash: `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
- This establishes binary-equivalent recovered C semantics, **not recovery of
  the original C whitespace/text**, nor execution of 22 full matrices.
- The surviving generator reproduces all22 archived assembly files exactly;
  its own current Python bytes are not claimed to equal the original generator.
- The trace ELF is hash-verified; no separate trace-C reconstruction is claimed.

## Prepared Scope

Every case executes the original seed0 initialization once and all original
operation calls from trial0 through the listed terminal trial, in order.
There is no direct-tuple substitute, reset between calls, hint or filtering of
unexecuted full-matrix trials. e8/m8 reaches the boundary at trial37 because its
`cap/2` is512, so a fabricated 55-trial prefix is not used for that shape.

| Program suffix | Capacity | Original trials | Terminal VL / vstart | Historical role |
| --- | ---: | --- | --- | --- |
| e8_m4_prefix56 | 512 | 0..55 | 512 /256 | Confirmed e8/m4 trace boundary |
| e8_m8_prefix38 | 1024 | 0..37 | 512 /256 | Failed shape, predicted boundary |
| e16_m8_prefix56 | 512 | 0..55 | 512 /256 | Failed shape, predicted boundary |
| e8_m2_prefix56 | 256 | 0..55 | 256 /128 | Prefix of historically passing shape |
| e16_m4_prefix56 | 256 | 0..55 | 256 /128 | Prefix of historically passing shape |

All names in the runner manifest begin with `arithmetic_`. All execute original
`vadd.vv v24,v8,v16,v0.t`, encoding `00880c57`. Original PCs are `0x1087c` for
e8 and `0x108ae` for e16; SoC port PCs are `0x80000818` and `0x80000852`.
The archived assembly is copied unchanged, including full-capacity source and
old-vd loads, `vlm.v`, `tu,mu`, target VL, `csrw vstart`, target instruction,
returned-vstart read, full-capacity result store and return.

The only prefix change is `if(checks==N) goto prefix_complete` **after** the
original scalar checking loop and check-count increment. Each case retains
its exact [two-line prefix diff](prepared02/prepared/arithmetic_e8_m4_prefix56/prefix.diff)
and separate runtime adaptation diff. Runtime changes replace Linux entry,
write and exit with the existing immutable integration startup/runtime.

The original xorshift seed, input special values, predicates (all-on, odd,
`i%7==2`), `0x5b` destination/guards, arithmetic oracle and all-capacity checking
remain. Prestart, inactive and tail values must remain undisturbed; **no
agnostic allowance was added**. Both guard elements and the full unsigned-long
returned vstart are checked. The original summary literal `seeds=3` denotes
the original matrix setting, **not three seeds executed by these prefixes**;
the additional exact `ARITHMETIC_PREFIX_PASS ... trials=N` marker disambiguates
the scope. All prepared prefixes actually execute seed0 only.

## Host And Spike Results

[Host status](prepared02/host/status.json): 10 positive runs, comprising the
bounded port and an unbounded recovered-original host capture for each shape.
The latter stops at the next call after N complete original scalar checks.
Both must match independent Python tuples and FNV digests of complete a/b,
all128 predicate bytes and full old destination plus guards. All40 negative
checks reject injected active, prestart, masked-off, tail, left/right guard,
returned-vstart-low and returned-vstart-high corruption. Host models are never
linked into the vector ELFs.

[Spike status](prepared02/reference/status.json): 5/5 PASS, using
`rv64gcv_zvl1024b`, vlenb128 and the existing nonzero-vstart-capable Spike.
The [separate vstart probe](prepared02/reference/vstart_probe/spike_probe.json)
also passes. Exact oracle/count markers, wrapper markers, raw failure veto and
exit0 are required. Spike and SoC ELFs share frozen case C/S but have distinct
HTIF/UART runtime builds and separately recorded hashes; Spike PASS is not a
claim that the SoC ELF has executed.

103 external/input pins, prepared file hashes, original/SoC/Spike ELF hashes,
all56 drained trace tuples and original/port target identities were rechecked
by `audit_ready.py`. SoC programs manifest SHA256:
`165c5c4d7dc83da93480b5389eda711aebd0af9928560f0aa5e0c0ea57e0da08`.

## Budget And Future Acceptance

| Program suffix | Spike instructions to exit | Estimated VCS wall seconds | Proposed inner budget |
| --- | ---: | ---: | ---: |
| e8_m4_prefix56 | 1,180,150 | 1443..1569 | 4000s |
| e8_m8_prefix38 | 1,474,919 | 1803..1961 | 4000s |
| e16_m8_prefix56 | 1,103,733 | 1349..1468 | 4000s |
| e8_m2_prefix56 | 602,560 | 737..801 | 1800s |
| e16_m4_prefix56 | 565,161 | 691..752 | 1800s |

These are **cross-suite host-time estimates**, using the three completed
candidate02 mask-alias prefix measurements (1.223..1.330ms per Spike instruction),
not RTL cycles or a throughput guarantee for another image/resource load.
Estimated jobs1 total:6023..6551s, approximately100..109 minutes. Proposed
jobs1 outer budget16800s exceeds the sum of inner budgets15600s and leaves
teardown/check time. No jobs, capacity reservation or image build has started.

The standard integration runner accepts this programs directory. A future
authorized launch must separately freeze the chosen image/source/ELF inputs,
require exact-five runner COMPLETE/PASS/exit0, exact markers/counts and firmware
success, and veto raw `RVV_MATRIX_FAIL`/`RVV_MATRIX_FAILED`, board failures,
traps and fatal errors **even if PASS markers also appear**. Do not use the
shared runner's marker-presence check alone as terminal acceptance. No new
launch wrapper or generic scheduler was added in this preparation task.

## Preserved Preparation History

`recovery01` retains the first successful e8/m4 byte-identical reconstruction;
`recovery22` applies that same reconstruction to all22 identities.
`prepared01/failure.json` and compile log retain a host-only `-Wclobbered`
error for the `setjmp/longjmp` capture result variable. Declaring that variable
`volatile` fixed the fixture; source oracle/expected data were unchanged.
All final positive, negative, build and Spike results are in fresh `prepared02`.
The first readiness postprocessor used the wrong probe filename `status.json`;
it was corrected to the helper's actual `spike_probe.json`, without rebuilding
or rerunning any test. No failed record was rewritten as PASS.

## Successor Replay Plan: Candidate04, Jobs2

This appended plan supersedes the earlier **proposed jobs1/16800s** scheduling
and the historical statement that no replay wrapper had been added. The
earlier preparation history, `prepared02` inputs, ELF bytes and oracle remain
unchanged. The isolated [replay driver](replay_candidate04.py) and
[candidate04_plan01/plan.json](candidate04_plan01/plan.json) now specify:

- Existing frozen candidate04 image, jobs2, exactly five prefixes with counts
  **56/38/56/56/56**, retaining all original scalar checks and exact markers.
- Per-case inner limits4000/4000/4000/1800/1800s; sum15600s. The jobs2 timeout
  schedule is8000s, with a10000s outer service limit. The measured-comparable
  estimate is3231..3514s (approximately54..59 minutes), not a DUT measurement.
- Parent-only launch after `integration/candidate04_regression38_03` reaches
  accepted terminal PASS and releases its four slots. No polling/wait worker.
  A fresh one-shot gate retains the other20 reservations, adds these two slots,
  counts unreserved live simulators, and enforces cap24 / available RAM32GiB.
- The parent **must launch under systemd with `RuntimeMaxSec=10000` and
  `KillMode=control-group`**. Use `Restart=no`; allow teardown with
  `TimeoutStopSec=60`. The Python driver's manifest records the outer budget
  but does not itself impose a service deadline. Do not launch it as an
  unbounded foreground command.
- Explicit parent authorization and the approved plan SHA are required.
  Exact-five terminal acceptance rechecks private ELF/image identities,
  original marker counts, firmware success and raw failure veto. Checker
  errors cancel peers; refusal/failure is not automatically retried.

Plan SHA256:
`34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`.
[Preflight](candidate04_plan01/preflight.json) retains17 host checks and5 dry
runs, **not five DUT passes**. The [independent static review](PLAN_REVIEW01.md)
rehashes the top-level manifests and all992 plan pins with zero mismatch.
At that review no attempt, launch, replay or complete record existed. No DUT
launch or resource-progress polling was performed; wait for parent approval
and the38 terminal gate.

Source provenance remains unchanged: reconstructed C reproduces all22
archived complete Linux ELFs byte-for-byte; the original C text is not
recovered. Neither this plan nor its preflight closes the22 whole matrices.
