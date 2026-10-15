# Full482 M8 Entry Handoff

Software remains frozen at `../work05/READY.json`, SHA
`06197d69f8e3767e358b0dacdb6020147f8b1dcf7c9961fd20f5929436a0941a`.
No new compilation, Spike, RTL change, or DUT invocation during worker preparation.

Actual `host02.json`: 21 tests, numeric child exit0, 51.510347403s,
test input pins unchanged. Covers synthetic complete482 RVFI and compiled ABI,
fresh per-call source/oldvd/mask initialization, actual address/BE/data/register
checks, complete packed output oracle, per-owner protocol negatives and private
monitor-boundary persistence. Synthetic rows are not measured DUT/reference rows.
Original software Host equivalence/mutations and actual reference receipt are
consumed from the frozen work05 and independent software review, not rerun.

Required owners derive from actual model: five memory owners per call (2410),
182 targets with vstart<VL, including45 actual zero-mask targets. Every such
retired owner must match its ordered architectural owner and complete its own
alloc/done. Extra uops on another owner cannot substitute. The other300 targets
may elide. Only the generic protocol's side-effect-free vector CSR-read replay
is allowed; those configuration owners cannot receive backend data uops or count
as necessary memory/target coverage. All13 PCs of every unused op1..op7 are vetoed.

65 packed output reads/call check all512 original bytes plus two guards;
only the final load's high6 bytes outside the original oracle are ignored.
Reset-known GPR values are a frozen M8 implementation fact (FpgaEn0 FF regfile),
not an ISA default; unknown source/base GPR fails closed.

Prepared plan SHA:
`2e4be5e555d14eac74877535733783ad0970eefdd376328678d3e5a837236897`.
Actual final independent entry report is still required at runtime. Expected
truthful fields: status `APPROVED_M8_FULL482_ENTRY_NOT_DUT_PASS`, plan_sha256,
source_ready_sha256, blocking_findings=[], actual_process_waited=true,
actual_review_process_exit numeric0, verified_input_pins. The existing software
review explicitly does not approve DUT entry and cannot satisfy this gate.

Fresh direct unit: `ara-macc-full482-scalar64-m8-01.service`, jobs1/reserved0.
Case10800s, worker12000s including postcheck, systemd13200s/KillMode control-group/
Restart no. Frozen M8 image reused. Actual private PRELOAD/TESTCASE/CWD and direct
MainPID/cgroup checked; resource cap24 and MemAvailable>=32GiB required. No retries.
Actual monitor tuple is durably saved before generic checks; timeout/nonzero/
failure/late abort cannot PASS. Startup needs same-generation actual CPU ticks,
closed-CSV cycle and bytes growing within the original60s (zero baseline rebased
to first positive sample without a deadline reset).

Budget proxy: 835145 scalar retired + 482*3295 measured M4 helper cycles =
2423335 cycles; /873 old cross-program cycles/s with2x margin =5551.74s.
This is neither measured M8 runtime nor a guarantee. Frozen work05's older
scalar-only2266s projection is not used as the complete DUT estimate.

Scope after eventual success is requested original natural first482 with481
predecessors and scalar optimization. Not full22400, not original Linux timing,
not unknown historical stalls. Old STOPPED attempts and source READY are retained.
