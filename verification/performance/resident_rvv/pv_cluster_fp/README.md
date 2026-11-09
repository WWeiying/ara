# Four-Lane PV Numerical Gate

This bounded host-VCS gate combines the existing `pv_cluster` wrapper with four
actual production VMFPUs through byte-identical `pv_vmfpu/adapter.sv` instances.
Each adapter retains its native-baseline miter. This is numerical integration,
not SoC integration, FPGA acceptance, synthesis, or a performance measurement.
The final-ack interface remains experimental, not a production LDU connection.

The parent-owned `corpus.py` and `test_corpus.py` are snapshotted unchanged.
The 68 common-shape groups include three real tiles with four distinct model
lanes and token counts 64/64/9, followed by normal shapes, tails, rounding modes,
and signaling-NaN cases. All arithmetic expectations originate in the previously
accepted independent-SoftFloat corpus; the runner verifies every regrouped body
byte-for-byte, allowing only case-ID remapping. Prepared-input flags are not
recounted: group completion is the OR of accepted FMA flags only.

The bench checks every accepted FMA's complete operands, tag, mask, and rounding
mode; each actual return's enabled halfwords and flags; actual fanout delivery;
and final slot, full data (including preserved disabled bytes), and byte enable.
Raw masked-off FPU result halfwords are not architectural outputs. They are not
compared to golden arithmetic, while their accumulator bytes must remain intact.
Independent final-ack accounting covers same-cycle, delayed, and rejected excess
acks, maximum debt of 16, debt after lane completion, and stalled group completion.
Lane-specific FPU admission and write-accept stalls create asymmetric progress.

All four `finish_gate()` tasks run after every completed group, with cluster busy
low, before the next start, and again before `$finish`. The separate normal-only
log checker requires exactly one acquire/release and five completed native probes
per lane per group, zero resets/cancellations, and balanced private arithmetic.
The older reset-inclusive checker is neither edited nor weakened.

## Run

Preparation validates accepted04 and cluster02 receipts, snapshots explicitly
selected inputs, checks the current adapter/RTL against their accepted hashes,
and pins the generator, tests, corpus, runner, bench, README, tool, and dependency
inputs before compilation. No live dependency tree is compiled. Include directory
inventories are also checked before and after execution. The source-import design
proposal is deliberately not a dependency. Use a fresh direct child of signoff
`verification/out` for every attempt; reports and failed attempts are immutable.

```sh
python3 -B verification/performance/resident_rvv/pv_cluster_fp/test_run.py
python3 -B verification/performance/resident_rvv/pv_cluster_fp/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_cluster_fp_agent_20261108_01 \
  --prepare-only
```

Run the resulting `inputs/run.py OUTPUT --execute-prepared` directly as the main
process of a transient `systemd-run --user` service. Capture stdout/stderr with
`StandardOutput=append:.../worker.log` and `StandardError=inherit`; confirm the
compiler/simulator in that service's control group. Do not use a short launcher
that backgrounds the worker. Compilation is bounded at 600 seconds, simulation
at 180 seconds, each case at 100000 clocks, and adapter drain by its existing
8192-clock gate. Only SharedFma=0 is the initial target; `--shared 1` creates a
separate explicitly requested follow-up collection.

`report.json` is PASS only after exact numerical/native log checks and post-run
source, include-inventory, and executable-image identity checks. `prepared.json`
is explicitly not an execution result. No stall-test cycle count is reported as
performance evidence. Reset, abort, and malformed-command coverage remain owned
by the previous protocol and VMFPU gates.
