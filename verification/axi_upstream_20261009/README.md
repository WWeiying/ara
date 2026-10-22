# Selective AXI upstream correctness audit (2026-10-09)

## Scope and provenance

This is an actual-module VCS test set, not a software counter model or a whole
dependency upgrade. Only four files in `hardware/deps/axi/src` are changed.
The parent agent owns patch registration and the final SoC integration build.
No registry, RVV/QBS/AKV RTL, existing sealed helpers, or dependency lock was
modified by this work. No DC, Verilator, URG or ZCC was used.

| Dependency | Actual local revision | Action |
| --- | --- | --- |
| axi | `a8c53cee2520d328d390c507c88818e8ac144c8c` | Four-file selective patch |
| common_cells (1.40) | `1281545696eb3fcba50ec5b4275993476a3c710e` | No interface migration |
| tech_cells_generic (0.2.14) | `3a3de73632a06826b1bd9c65a0a2e92b32016845` | Unchanged |
| apb (0.2.4) | `77ddf073f194d44b9119949d2421be59789e69ae` | Unchanged |

Baseline bytes are extracted from the parent's pre-edit archive, not reconstructed
by reversing a patch:

- `/tmp/ara-signoff-upstream-before-20261009.tgz`
- SHA256: `bbc7a77d13e5bd7832f8001b54884b35b08d18675f56e698e35d365383802601`

Official source was inspected in isolated repositories under
`/tmp/ara-dependency-upstream-audit-lxBsdcS8`. No fetch or branch switch was
performed in a live dependency repository.

## Functional changes and active applicability

### 1. Splitter support classification, upstream #437

[Official commit](https://github.com/pulp-platform/axi/commit/4da15979747f326bde2f9869c64e587ce599772c)

`axi_burst_splitter_gran.sv:109` used `len >= len_limit` for its untouched-burst
fast acceptance. With the real wrapper's `len_limit=0`, this accepted every
burst before checking WRAP or nonmodifiable constraints. The correction is
`len <= len_limit`. Unsupported bursts now receive SLVERR rather than escaping
to a peripheral as incorrectly transformed transactions.

Active path: `hardware/src/ara_soc.sv:385,458` -> `axi_to_axi_lite` ->
`axi_atop_filter` -> `axi_burst_splitter` -> `axi_burst_splitter_gran`.
This matters to peripheral protocol correctness, not a claim of faster LLM math.

### 2. Demux transaction accounting, upstream #440 and narrow local extension

[Official commit](https://github.com/pulp-platform/axi/commit/da8793b0e3f14c9186c94fac9ed6ec06375c254e)

`axi_demux_simple.sv:69` now includes MaxTrans in its count range and explicitly
compares the W-open count against MaxTrans. Both ID-counter instances receive
MaxTrans. `axi_demux_id_counters.sv:128` compares against that threshold and
retains occupancy when the overflow bit is set. Local `cf_math_pkg` and register
macros are retained; common_cells 2.x is not needed. The extra upstream
simulation-only assertion was not required for this functional backport.

Measured extension beyond the upstream patch: MaxTrans=1 needs a minimum
two-bit counter delta. Legal distinct complete AXI IDs can alias in AxiLookBits;
simultaneous AR and returning ATOP therefore increment one index by two.
With a one-bit `cnt_t`, `cnt_t'(2)` is zero. The test uses AR ID=0, ATOP ID=2,
two-bit complete IDs and one lookup bit. It does **not** reuse an outstanding
complete AXI ID for an atomic transaction. Minimum counter width two fixes this
without changing arbitration, pipeline stages or interfaces.

MaxTrans is a per-index admission threshold here, not a proof of a global
transaction ceiling. Two independently admitted channels can transiently cross
the threshold. Both accepted responses must remain counted, and further
requests must stall until the counter falls below the threshold.

Active path: `ara_soc.sv:138` sets crossbar MaxMstTrans=4, UniqueIds=0;
`axi_xbar_unmuxed` -> `axi_demux` -> `axi_demux_simple`. The MaxTrans=4 capacity
fix is directly relevant. The MaxTrans=1 extension covers reuse of the same
dependency at other supported limits; it is not an observed SoC deadlock claim.

### 3. Bank read-response mask, upstream #426

[Official commit](https://github.com/pulp-platform/axi/commit/e55ae2a7ee606ee3cfd4257f63982a971b704407)

`axi_to_detailed_mem.sv:508` had precedence errors in both the byte offset and
range end: `addr % DataWidth/8` and `offset + 1 << size`. Parenthesizing the byte
word modulus and transfer size makes only accessed banks contribute error and
exclusive-success status. This is the exact upstream two-line functional patch.

Baseline actual-module failures:

- Offset 2, size 0, error only from bank 0: got SLVERR, expected OKAY.
- Offset 2, size 0, exclusive success only from bank 0: got EXOKAY, expected OKAY.
- Normal reads and partial/zero-strobe writes passed before the patch.

The independent checker enumerates accessed bytes and maps them to banks. It
does not copy the RTL range-expression formula. Four banks, 64-bit data, delayed
bank grants and upstream response backpressure are exercised.

Active wrapper: `ara_soc.sv:218` -> `axi_to_mem` -> `axi_to_detailed_mem`.
However `axi_to_mem.sv:111-112` ties error/exokay inputs to zero. This is a
preventive dependency fix for real bank-status users; it is not evidence that
the current L2 wrapper produced these erroneous statuses.

## Test contract

`axi_audit_tb.sv` instantiates the actual splitter, demux and filter. Its
scoreboard checks public-channel handshakes and independently generated
addresses/data, not internal counter equality alone. It checks payload stability,
destination/order, response identity/status/last, completion, and queue drainage.
All cases have bounded cycle watchdogs, and RTL assertions remain enabled.

| Cases | Coverage |
| --- | --- |
| 0-15 | Actual len_limit=0; single/four-beat INCR and FIXED; unsupported WRAP and nonmodifiable bursts; AW/AR/W and B/R backpressure; filtered AtomicStore |
| 101-104 | Read admission and release at MaxTrans 1/2/3/4 |
| 111-114 | AW admission; W completion does not forget outstanding B; independent W/B stalls |
| 121-124 | Same-ID cross-destination ordering, cross-ID response reordering |
| 131-134 | Same-edge AR+ATOP with legal distinct full IDs and aliased lookup index; both responses counted |
| 141-144 | W routing follows AW order until last beat; different-ID B reordering |
| 151-154 | Selected-target AW/AR stalls and complete-payload stability |
| Bank 0 | 15 aligned read shapes, three masked/zero-strobe writes, full readback |
| Bank 1 | 15 read shapes x four one-hot bank-error masks |
| Bank 2 | 15 read shapes x 16 exclusive-success masks |

These are directed protocol regressions, not exhaustive AXI verification. No
unaligned/burst bank-memory coverage, complete SoC runtime, or performance/PPA
signoff is implied. Parent integration must still compile and run representative
SoC traffic against the registered source hashes.

### Earlier test corrections retained as evidence

The initial 40-case experiment produced baseline 24/40 and upstream-only 38/40.
Those totals are **not final signoff**:

1. Bare ATOP case 13 bypassed the required filter and used an atomic burst. Its
   assertion is a wrong-stimulus result, not a new splitter bug. The final case
   is a one-beat AtomicStore through the actual filter, matching system topology.
2. Initial cases 131-134 reused a complete ID for AR and ATOP. The final tests
   use legal distinct IDs with identical low lookup bits. The remaining
   MaxTrans=1 defect was remeasured with that legal stimulus before modifying RTL.

Evidence for the decisive legal pre-fix experiment:
`/tmp/axi-upstream-legal-atop-before-20261009/`: case 13 PASS, case 131 FAIL
(`AR/ATOP count lost or over-limit`). Source copies and pins are retained.
Initial test sources are additionally archived at
`/tmp/axi-upstream-upstream440-20261009-01/inputs/original_*`.

Bank setup attempts `axi-bank-baseline-20261009-01` and `-02` were compile-filelist
corrections, not DUT failures. `-03` is the first valid bank baseline run.

## Reproduction and final evidence

Use a fresh output directory for every invocation, on the host with VCS available:

```sh
python3 verification/axi_upstream_20261009/run.py \
  --source baseline --output /tmp/axi-baseline-new --jobs 4
python3 verification/axi_upstream_20261009/run.py \
  --source current --output /tmp/axi-current-new --jobs 4
python3 verification/axi_upstream_20261009/run_bank.py \
  --source current --output /tmp/axi-bank-current-new
```

The runners check pins at completion, keep compiler commands and logs, and require
an explicit completion marker without a fatal message. `run.py` uses independent
per-case working directories. A simulator exit code of zero alone is not PASS.

Final output directories:

- `/tmp/axi-upstream-final-baseline-20261009`
- `/tmp/axi-upstream-final-current-20261009`
- `/tmp/axi-bank-baseline-20261009-03`
- `/tmp/axi-bank-final-current-20261009`

See each `summary.json`, `pins.json`, `compile-command.json`, and `case-*.log`.
Small logs, summaries, pins, and AXI source snapshots are also copied into the
adjacent `evidence/` directory; simulator executables and generated C are not
duplicated. Paths inside archived pins refer to the original measured runs.

| Final identical-stimulus comparison | Baseline | Patched |
| --- | --- | --- |
| Splitter/filter, cases 0-15 | 10/16 PASS | 16/16 PASS |
| Demux, 24 protocol cases | 15/24 PASS | 24/24 PASS |
| Bank response, three case groups | 1/3 PASS | 3/3 PASS |
| Total | 26/43 PASS | **43/43 PASS** |

Final baseline failures are exactly `6,7,8,9,10,11,102,104,112,114,122,131,132,134,142`
plus bank groups 1 and 2. There are no final patched failures/timeouts. Both
40-case runners completed their input-hash checks; the bank runner also checked
all its input hashes. RTL `git diff --check` passed.

Bank final groups reported 96, 300, and 1200 checker assertions, respectively.
Legal MaxTrans=1 simultaneous accounting reported 58 checks, AR=2, AW=1, W=1,
R=3, B=1, with every expected response consumed and the scoreboard drained.
All four RTL files and the test inputs are frozen at these results. The next
action belongs to the parent: register the selective dependency patch and build
the complete SoC. No unmeasured whole-SoC acceptance is claimed here.

## Reviewed but not upgraded

- common_cells FIFO usage-width work requires caller auditing rather than an
  interface-wide update. The active CVA6 fork already guards full separately in
  `core/acc_dispatcher.sv:223-226` and `cache_subsystem/std_cache_subsystem.sv:231-232`.
  These existing parent-owned fixes are not modified here. No additional
  demonstrated common_cells FIFO failure justifies changing its interface.
- tech_cells_generic blackbox/synthesis and FPGA clock-mapping changes are not
  evidence of a missing functional fix in the current ASIC simulation path.
  They remain a separate synthesis/FPGA review, not a library upgrade here.
- No demonstrated missing APB functional fix was identified for the active
  peripheral path. Testbench/version churn alone is not a backport reason.

## Frozen RTL hashes

| File under hardware/deps/axi/src | SHA256 |
| --- | --- |
| axi_burst_splitter_gran.sv | `1f2b0ffc2b8d72fd467349e49ff10e195a7f9cbd45947c406d9aaec1e52afc3e` |
| axi_demux_simple.sv | `910936bc31ae1dd2f15f9e61a33a46bf80c74d603d936934f744fd7fa00c3f61` |
| axi_demux_id_counters.sv | `f5a5e5ce65757bcdd731f50f0a5984c2d990ec461f86aaa3c413d26088c8b10a` |
| axi_to_detailed_mem.sv | `1f71f1702323228af459919d86096d8c6eb37c170276346452d42191cfd9ee7c` |
