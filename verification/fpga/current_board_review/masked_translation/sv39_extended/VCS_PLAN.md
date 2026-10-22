# Extended8 VCS Plan Only

No simulator, build, or parent-pipeline command was launched. Existing reference,
ELFs, production RTL and sealed helpers remain unchanged.

## Gates And Identity

Wait for Tesla's final sequencer seven local cases, the parent combined build,
and the parent's three Sv39 plus ten smoke results. Review those results and
obtain explicit launch authorization. Do not overlap the parent pipeline.

Image to bind later:
`/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image`.
The image is still the parent's build output, not an image validated by this plan.

[vcs_plan01/plan.json](vcs_plan01/plan.json) records a complete rehash of both
539-file frozen sets and the 57 reference input pins. Compared with final04,
only these three semantic inputs differ; bender/filelist changes normalize to
root relocation only:

```text
addrgen.sv       470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da
vldu.sv          4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab
ara_sequencer.sv bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655
```

Preflight still required after parent completion: image.json must bind this exact
snapshot; verify simulator/configuration/compiled source manifest hashes, 4 lanes,
VLEN1024, 2MiB L2, OS support and PMP0; verify ELF64/RISC-V entry0x80000000,
LOAD ranges, UART/CTRL interface and absence of HTIF tohost. Recheck all pins
before/after execution. Parent PASS does not replace this binding check.

## One ELF And Budget

**One unchanged SoC ELF runs eight subcases sequentially with shared initialization.**
No selection argument or eight-way parallelism exists in this ELF. Its existing
SHA256 is `a0219fef355612a36370851a6a4d3011bb30991afbc19459068c3728526ea982`.
Use [reference01/soc.elf](reference01/soc.elf), never a Linux or Spike ELF.

Calibration, not a measurement of candidate02:

- Previous candidate01 three-case runs: 275188-275326 reference commits versus
  332358-334871 measured SoC cycles, with 307.135-320.788 seconds wall time.
- Extended8: 780454 reference commit events. Linear extrapolation gives
  **942592-949243 cycles and 871-909 seconds (14.5-15.2 minutes)**.
- Changed instruction mix, extra vector/trap work, CPU contention and candidate02
  RTL can change this ratio. Allow roughly 12-18 minutes operationally; this is
  an estimate, not a performance guarantee or an architectural requirement.
- One host-VCS process, `jobs=1`, **1200-second hard runner timeout**, no full FSDB.
  A 1.35M-cycle ceiling is a diagnostic performance bound, not an RTL assertion.
  Do not automatically extend timeouts, retry, split the suite, or reduce checks.
- A timeout is INCOMPLETE/NOT PASS. Identify first unfinished subcase/stage and
  preserve artifacts before considering another explicitly authorized experiment.

Run as an independent background service in a new owned directory. Confirm the
initial process/trace is live once; for this >10-minute point, do not repeatedly
poll. Inspect completion artifacts after service completion. Wall timeout already
exists in the sealed runner; cycle and per-stage bounds below are planned
post-run/post-timeout diagnostics, not an implemented extra kill mechanism.

## Per-Case Progress

All PCs and addresses below come from **soc.symbols.json**, not Spike symbols.
Exact addresses, all13 checkpoint estimates and case-counter locations are in
`vcs_plan01/plan.json`. The following are cumulative estimates from startup:

| Case | Final checkpoint, Spike events | Estimated SoC cycles | Estimated minutes | Per-case check delta |
|---|---:|---:|---:|---:|
| 0 unit load retry | 237423 | 287k-289k | 4.4-4.6 | 630 |
| 1 unit store retry | 325212 | 393k-396k | 6.1-6.3 | 630 |
| 2 positive load retry | 412230 | 498k-501k | 7.7-8.0 | 630 |
| 3 negative store retry | 500015 | 604k-608k | 9.3-9.7 | 630 |
| 4 zero load retry | 586955 | 709k-714k | 10.9-11.4 | 630 |
| 5 zero store alloff | 635581 | 768k-773k | 11.8-12.3 | 456 |
| 6 FOF shortening | 679861 | 821k-827k | 12.6-13.2 | 448 |
| 7 FOF masked suffix | 724871 | 875k-882k | 13.5-14.1 | 456 |
| Shared final checks / exit | 780454 | 943k-949k | 14.5-15.2 | total6227 |

Final checkpoint is not itself PASS: `mx_checkpoint` can be reached after a
comparison failure. Require the expected subsequent `mx_case_checks[c]` store,
`mx_errors==0`, `mx_unexpected==0`, correct trap ledger and final architectural
oracle completion. BSS zeroing of mx_current is not case0 entry; use actual
`mx_enter_s`/`mx_s_entry` execution and the initialized case metadata.

Per-subcase order and bounded diagnostic criteria:

1. **Entry/setup:** current id in order0..7; real S entry; expected args/mask/PTE.
   First fault checkpoint is expected by ~231k cycles. Flag initialization/first
   case as overdue at 350k cycles without this checkpoint, or case0 completion
   beyond420 seconds. Do not treat initial scalar initialization as a vector hang.
2. **Cases0-4 fault:** exact cause13/15, own target PC, expected tval, VL8/vtype8,
   vstart5/5/5/5/2, fcsr117/vcsr5 and marker0. Then full fault snapshot and
   `mx_checkpoint` at phase1, before repair. Wrong values fail immediately as an
   architectural discrepancy; they are not progress toward the expected trap.
3. **Repair/retry:** correct leaf repair, addressed `mx_repair_sfence`, restored
   vstart and `mx_trap_mret`; same-PC target completes. Prefix poison must survive.
   Do not require the faulting vector instruction to retire before the handler:
   use trap CSR/record evidence and accelerator front events where available.
4. **Completion:** raw post-target CSR record, complete result snapshot, younger
   marker1, exact S ECALL, phase2 checkpoint and expected case check delta.
   Cases5-7 must have no page-fault handler/repair at all. Case6 raw VL4 is checked
   before diagnostic vsetvli; its later ECALL correctly has VL8.
5. **Bounds after first checkpoint:** mark any >160k-cycle gap between successive
   required checkpoints as stalled/slow for triage. Expected largest gap is ~59k
   cycles. Mark subsequent case completion >180 seconds after prior case completion
   as overdue when wall timestamps exist; no change to the 1200-second hard cap.
   The final shared restore/check section should fit100k cycles (estimate~67k).
   These bounds localize failure, not manufacture a functional FAIL from a slow host.

Key PCs: checkpoint0x80000308, handler0x8000119c, repair-SFENCE0x8000070a,
trap-MRET0x80001280, targets0x80001328/1330/1338/1340/1348,
younger-marker0x800013e4, ECALL0x800013f0.
State: current0x8000a090, phase0x8000a060, case-checks0x8000a098,
errors0x8000a048, unexpected0x8000a040, total-checks0x8000a050,
completion0x8000a058. Recognize scalar memory writes using CSV mem_wmask and
instruction semantics, not coincidentally matching mem_wdata in a non-store row.

Final acceptance requires all8 case deltas, all13 checkpoints, five precise page
faults/retries, eight S ECALLs, 6227 checks, zero errors/unexpected, magic
0x6d78737633390008, UART `MX_SV39_PASS`, CTRL return code0, runner/trace validation
and no simulator/assertion failure. The last subcase alone is not whole-suite PASS.

## Successor Adapter Still Needed

Current preparation created only a plan and source excerpts, not an executable
VCS launcher or CSV observer. A later new adapter in this owned directory must
create a programs manifest for one entry `extended8`, using existing prepared
provenance and the unchanged ELF, and call the sealed runner with jobs1/timeout1200.
No change to sealed `run.py`, `prepare.py` or old candidate scripts is needed.
Do not invoke their build/snapshot subcommands.

The new observer must decode the existing CSV into the milestones/CSR records
above. Spike `validate()` is not a SoC-CSV decoder. The SoC commit CSV is also not
a complete record of vector data writeback: all-byte data/oldvd/guard validation
remains the unchanged on-device scalar oracle, supplemented by trace evidence,
not replaced by counting vector retirements or searching a PASS string.

## Original Source Boundary

[vcs_plan01/ORIGINAL_EXCERPTS.md](vcs_plan01/ORIGINAL_EXCERPTS.md) retains hash-bound
original assembly and line-numbered C oracle/setup excerpts for all eight cases.
Original sources and Linux ELF hashes remain unchanged. Target instructions and
operand choices, e16/m1 tu/mu, masks, strides, boundary setup, full oldvd/output,
prefix validation, poison-before-retry and same-PC/vstart requirements are retained.

**The new C/S is not byte-identical Linux source.** mmap/mprotect/signal/ucontext
are adapted to fixed Sv39 mappings and M-mode exact trap handling; common
initialization replaces separate Linux processes. Register guards and full physical
data/page-table scans supplement the original oracle. Fault-first scenario0's
elements4-7 remain captured but unspecified as in its original oracle; no other
oldvd/guard/exception checks were weakened.

NF1/e16/m1/VL8 only. No NF segments, long maskword traversal, misalignment,
arbitrary initial vstart, Linux signal ABI, active zero-stride store, negative
load, or injected final-grant/backpressure coverage is claimed. The five retries
exercise nonzero restart vstart, but do not prove the open cross-instruction fault
epoch or delayed-final-grant cases closed. A future candidate02 result applies
only to the exact image/ELF and these eight cases.
