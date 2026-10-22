# Measured Active NaN Min/Max

2026-10-12: **PASS_84_REAL_RTL_NAN_MINMAX**. One campaign, two topology
compiles/runs, no retries, no production RTL changes. The active all-NaN
module-level evidence gap identified in `../review_current_nan_minmax01.md`
is now covered for the explicit cases below. That earlier review is preserved.

## Actual Execution

| Real topology | Cases | Compile rc / seconds | Sim rc / seconds | Per-case cycles |
| --- | --- | --- | --- | --- |
| 4 lanes | 42/42 PASS | 0 / 42.315445 | 0 / 12.394000 | 51..93 |
| 1 lane | 42/42 PASS | 0 / 41.316737 | 0 / 11.794147 | 83..266 |

VCS `V-2023.12-SP1`, same current hardware inputs for both runs. No full-SoC
build, reference simulation, Verilator, ZCC or URG. Every actual run console
contains `REDUCTION_COMPLETE cases=42`; the runner requires exact case names,
bitwise result match, all-five-flags match, successful exit and no fatal/error.

Each topology contains min/max x FP16/32/64 x seven profiles at VL35:
all-qNaN sparse element33 and unmasked all35; all-off qNaN and sNaN payloads;
mixed qNaN/sNaN sparse element33 and unmasked all35; sNaN seed with only a
remote qNaN source selected. These are84 new directed module points, **not
84 archived source cases**, and not a full-SoC/Linux signoff.

The independent IEEE-bit oracle and normative source links are in README.md.
All active all-NaN results are canonical 7e00/7fc00000/7ff8000000000000.
Both operations set NV16 iff a participating seed/source is signaling.
Both all-off seed types retain their exact negative payload55 with flags0.

## Actual Cycle Evidence

Cycle values below are absolute TB rising-edge counters within the respective
topology run; per-case duration also includes inherited settling/accounting.
`trace.csv` contains arithmetic handshakes and per-slot/collapsed exceptions;
`probe.csv` contains queue input/output, actual neutral, activity and writeback.

| 4-lane actual case | Internal per-result NV first seen | Published flags | Accepted lane0 write / epoch |
| --- | --- | --- | --- |
| min_fp16_qq_remote | none | all lanes00 | cycle43:7e00 / 1 |
| max_fp32_qq_remote | none | lanes1..3 at235:00; lane0 at237:00 | cycle237:7fc00000 / 1 |
| max_fp64_qq_all | none | all lanes at879:00 | cycle879:7ff8000000000000 / 1 |
| max_fp32_alloff_s | cycle1535 | lanes1..3 at1579:00; lane0 at1581:00 | cycle1581:ff800055 / 0 |
| max_fp32_mixed_remote | cycle2011 | lane1 at2027:10; all others00 | cycle2029:7fc00000 / 1 |
| max_fp32_seed_snan_remote | cycle2879 | lane0 at2925:10; all others00 | cycle2925:7fc00000 / 1 |

For `max_fp32_alloff_s`, actual full write bus is `7fc00000ff800055`, BE0f:
only the low32 bits are written. This is exact seed preservation, not a
canonical result or a full64-bit write. Internal NV is correctly suppressed.
For mixed_remote, lane1 publishes NV before lane0's final result; OR-ing the
real flags interface yields16, proving that checking only lane0 would be wrong.

One-lane counterpart timings: max_fp32_qq_remote writes472; alloff_s has
internal NV3411 then writes3538 with flags00/epoch0; mixed_remote has NV4545
then writes4560 with flags10/epoch1; seed_snan_remote has NV6477 then
writes6604 with flags10/epoch1.

Offline `audit.py` checked actual seed/source push values, all source packet
counts, queue seed acceptance,84 writebacks and84 epoch decisions, addresses/BE
through the inherited DUT test checks, and exactly one flag pulse per lane/case.
It verified910 accepted neutral observations for4 lanes and868 for1 lane;
all are canonical qNaN words. Source words are independently unshuffled before
comparison with the original prepared inputs, including tail-slot inputs.
`run01/probe_audit.json` retains all per-case write/flag cycle records.

An initial ad-hoc post-run inspection incorrectly required qNaN `ntr_val`
during idle cycle5, before an instruction was accepted; the idle value is0.
The final offline audit qualifies neutral checks by actual operand acceptance.
This was an observer qualification error, not a DUT/oracle failure. No DUT
rerun, stimulus change, expected-result change or old evidence rewrite occurred.

## Source And Result Identities

All60 campaign pins and current hardware identities remained unchanged.
The55 hardware files were checked against the existing accepted preserve80
snapshot before freezing and again against current source after execution.

| Artifact | SHA256 |
| --- | --- |
| Current/frozen VMFPU | `e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12` |
| Current/frozen operand_queue | `eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d` |
| run.py | `46c8645f6e5083cd55665e4b41e3dfee6ade57cad6ca87a0f92ec3932938be06` |
| Frozen successor TB | `20420c5404c79f59fa6a4ff00aef54fe780532c9a1e72c1facb5013038adae59` |
| run01/cases.json | `a5e451cac9b978f705bb619251dbfc946013eeb2044de5bba7cb7c77a23f3fde` |
| run01/pins.json | `5ee68ac68035afaf3d82dea6c4b0bc5877d09a164d08350568870fdafd136c3e` |
| run01/status.json | `085de37ba7ede3ad810231a0cee27d3b0118c9dd19cfd68c8e3b70d7328f7177` |
| lane4/results.csv | `18fcdc05505458b7714fff99ceef55abad930a7af8e13a2af2f3c5a3b19d7fb0` |
| lane1/results.csv | `b8def0c64a0933279536ace8f6d57f54bc09597eab528161c7821c2593454df5` |
| run01/probe_audit.json | `89cc3c759d39337760051a09e142280f537f565326b929c1cb93d42c85430c42` |
| audit.py | `e3be22552526fea098458eba9ab5f0a574d7eda4342b2913cbc980e19d6902e2` |

The offline audit also hashes both complete traces, probes and raw consoles.
Their identities are in its `hashes` object; no trace rows were dropped.

## Limits

Real operand queues, VMFPU and FPnew are under test; predicate supply and the
buffered SLDU rotation are modeled. The one-lane rotation uses the established
epoch-test topology. No CPU/dispatcher/MASKU/real SLDU/VRF arbitration/CSR
execution is claimed. The test checks the complete enabled result and exact
write mask, not a memory dump of architectural destination tails.
Only VL35/vstart0, these NaN patterns and two lane counts are covered.
There is no newly reproduced defect in the tested current min/max paths.
