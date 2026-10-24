# VRF panel negative-result attribution

Decision: experimental QBACC remains OFF; no GGML deployment. Correctness PASS
is not performance PASS. This offline analyzer launches no simulator and changes
no runtime, experimental driver, RTL, or historical evidence.

## Reproduce

From the signoff worktree, choose a fresh output directory:

```sh
python3 verification/qbs/analyze_vrf_panel_bench.py \
  --run verification/out/qbs-vrf-panel-bench-20261023-02 \
  --image-pins verification/out/qbacc-soc-20261023-02/source-pins.json \
  --output verification/out/qbs-vrf-panel-attribution-20261023-01
```

The parser is intentionally fixture-specific: Q6_K, Q8_K M4 interleaved,
N64 as two N32 commands, full K35 versus eight K4 stripes and a final K3.
The log has no explicit K/profile field: these are checked through expected
tile, activation/weight byte, pair, dot, FP issue, update and range counts, not
claimed as independently observed descriptor fields. It requires exactly 40
ordered commands, four exact ABBA markers, one exact result marker, flags1 and
checksum90924b7e574c4d19, and agreement with the completed parent receipt.
Unknown/missing/duplicate PERF fields and malformed marker suffixes fail closed.
Built-in negative mutations run before any PASS artifact is written.

The parent receipt's evidence hashes and all benchmark source pins are checked
before/after analysis. The three reviewed RTL files are also checked against
the image's source pins. This is not a fresh audit of every historical image
build helper: run_qbacc_soc.py has since changed, while these RTL hashes match.
No existing receipt is rewritten. New result.json and receipt.json pin this
analyzer, documentation, inputs, reviewed RTL and derived result.

## Measured result

| Trial | Path | Measured cycles | Engine busy | Residual |
| --- | --- | ---: | ---: | ---: |
| A0 | DIRECT | 82865 | 80548 | 2317 |
| B0 | striped | 89804 | 85154 | 4650 |
| B1 | striped | 89449 | 85154 | 4295 |
| A1 | DIRECT | 81760 | 80544 | 1216 |

Totals: DIRECT164625, striped179253, time regression8.8856492%; average loss
7314 cycles/call. Average engine-busy increase4608 and residual increase2706
sum to that loss. Residual is not an exclusively software counter: descriptor
construction/preflight, issue gaps, final stores/drains and other time outside
QBS busy are not independently separable from this aggregate evidence.
Preparation is excluded; descriptor setup is timed. This is not model timing.

Every trial has compute+overlap75040 cycles and560 internal tiles. B0/B1 each
have setup270, activation5635, weight1863, drain702, scheduler1032, commit594,
terminal18, fault0. A0 has setup31, activation223, weight4476, drain78,
scheduler632, commit66, terminal2. A1 differs: setup30, activation276,
weight4420. Each phase partition sums exactly to its engine-busy total.
Payload drops552192 to511568 bytes/call, but this is not a cycle benefit.

## Counter and mechanism interpretation

* qbs_engine.sv:440-469 classifies RUN by compute phase; overlap means compute
  with reader busy or a weight request, not specifically useful activation DMA.
* qbs_compute_engine.sv:529-535 and659-662: seed restore has none of these phase
  flags and is counted as scheduler, not setup. K4 scheduler37 becomes61 for
  continuation commands: observed24 extra cycles each,16 seeded commands/call.
* qbs_engine.sv:1481-1486 counts context replay busy, including read pipeline and
  backpressure; overlap requires simultaneous compute phase. Per K4 REUSE the
  observed296 replay cycles and304 activation cycles imply74/76 per block.
* qbs_engine.sv:1064-1065 enables activation lookahead only for DIRECT;
  qbs_compute_engine.sv:354-375 otherwise only requests activation in LOAD_TILE.
  Thus all resident blocks are currently staged before their own computation.

## Bounded future hypothesis, not an enable recommendation

REUSE-only lookahead can at most hide the current activation-phase budget of
26 noninitial blocks/call x76 =1976 cycles, assuming no displaced waiting or
new overhead. It cannot cover the observed7314-cycle loss, even ideally.
This is an attribution bound for hiding those existing stalls, not a universal
bound on an unrelated redesign. Do not blindly remove the DIRECT gate.

For M4 the existing two activation banks could hold current/next K without
new payload storage or changing arithmetic order (compute:283-292,386-391).
REUSE currently starts and labels replay with live compute_expected_k
(engine:849-857,961-1000), however. A candidate must request the activation
cursor K and latch that identity through stalls and K transitions, update the
replay uniqueness assertion, and retire only after the final N consumer.
M5..8 already occupy both banks and are outside this proposal.

FILL already has read/completion K tags, but shares the reader with weights.
Preserve engine:746-751 weight-priority arbitration: hiding activation stalls
may expose weight stalls instead. Context SRAM is separate from compute banks,
but cannot fill and replay simultaneously (context:220-239,472-473).
Faults must cancel replay and its latched tag, drain seed ownership, clear
compute banks, abort incomplete FILL, preserve committed REUSE state, and only
release on successful commit (engine:947-960,1299-1304; context:415-454).

Before considering deployment, a separately authorized fixed M4/N32/K4 test
must show next-K replay into the inactive bank during current computation,
unchanged output/flags/work/weight traffic, and lower total busy rather than
merely shifted phase counts. Include stalled first/last replay beats with
weight fault, retry from byte0, reset, and RELEASE preservation. Only then
consider a separate FILL/shared-reader experiment and rerun real-data ABBA.
