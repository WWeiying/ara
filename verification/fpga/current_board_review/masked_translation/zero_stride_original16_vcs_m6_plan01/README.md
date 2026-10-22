# Original16 frozen-M6 baseline

One continuous original `rvv_fault_replay_strided_zero_stride_e64_m4` source
program. Reuses the sealed SoC ELF `d719042343a32e41c31442bb77d4464bce3b09bb7aa3104e03726068a2d29c46`
and all61 source/reference pins; no build, reference rerun, partition reset,
retry or FSDB. M6 explicitly predates the new VLDU `DRAIN_EXCEPTION_MASK`.
Same ELF is suitable for a later separately pinned M7 comparison.

Hilbert's actual message accepted source/reference preparation for READY
`f70f17aaa945dc0c2932c8f5f549893059c07fb9e79155aa5c7f20386c7094b5`.
`REVIEW_RECEIPT.json` records that message, not a fabricated review-file hash.
It does not claim independent worker review or a new full raw reference parse.
The parent explicitly authorized one M6 run after this review and Host passes;
no further parent approval file is required.

## Execution

`replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out <owned>/prepared01 --host <owned>/host02`
creates the pinned command; `dryrun --plan-sha256 <digest>` does not simulate.
`prepared01/ready.json` contains the exact one-shot systemd command. The worker
must itself be the MainPID in `ara-zero-stride-original16-m6-01.service`.
Runtime resource checks count actual simv once, require total<=24 and available
memory>=32GiB. No obsolete reservation is carried by default.

Single simv limit **10800 s**, whole worker **12000 s**, direct service hard
limit **12600 s** (the extra time is validation/teardown, never a sim timeout
extension). No restart/retry. An unchanged deadline and sticky abort apply
through the last pin check and atomic terminal publication. Timeout alone is
not classified as an RTL bug.

The monitor's actual numeric outcome is fsynced before runner metadata and
postchecks. Runtime testcase ID and historical source name remain distinct.
The automatic terminal checker runs only after actual monitor0, childPASS0,
full console oracle and process exit. It consumes one closed CSV for the
case-specific observer; the mature generic protocol validator also runs.
There is no active-CSV terminal polling or duplicate terminal service.
`complete.json` is PASS only after exact COMPLETE runner metadata, noabort,
generic CVX/arch/uop completion, full observer and fresh image/input/plan pins.

## Strict scope and observability

Actual SoC PC/code, original capacity3 and bootstrap3-RVV instructions,
16 contiguous original ten-instruction helper windows,12 fault/retry windows,
16 ecalls,28 target attempts,8 unmapped refills,72 checkpoints,19212 scalar
comparisons. Actual scalar reads are mandatory for **1024 output uint64s,
32 guards,16384 memory uint64s, all16 result groups**, and original returned
vstart/context. Saved prestart data only is constrained at faults. No changes
to the original allowed suffix. Generic ownership checks accompany per-target
backend completion and actual handler CSR reads before diagnostic RVV.

RVFI has no vector-write payload. The observer invalidates those bytes and
uses actual subsequent scalar reads, never injected expected values. The
bootstrap copy has no scalar read: only its instruction/source identity is
checked, not its dynamic payload. A pre-cleanup checkpoint cannot independently
exclude hidden vector side effects erased by refill; no such claim is made.
The entire original FINAL memory oracle is observed. Physical MMU transactions,
AXI B handshakes, Linux signalframe/sigreturn, and the original Linux stall
are not closed by this Sv39 baseline.

Host full16 uses actual SoC instruction encodings but synthetic RVFI values,
explicitly not DUT evidence. Negative cases reject output/tail/typed-seed/guard,
active/all-off store, last-memory-byte, wrong retry, missing final observation,
truncation, raw failures and identity confusion. Runtime tests reuse the prior
accepted metadata/monitor contract, including partial-line first failure,
checker-throw durable numeric0, sticky late abort, command/ELF/plan drift.
Early Host fixture failures remain in their own directories; no simulator was
used to debug a checker.
