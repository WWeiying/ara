# Context To Production VMFPU Numerical Gate

Review successor only. No production RTL, parent reader, adapter, or original
SoftFloat corpus changes. No VRF import/queue-head ABI implementation. Host VCS,
SharedFma=0, not a SoC program, FPGA acceptance, or complete-call performance test.

## Admission And Mapping

Admission receipts under signoff `verification/out`:

- `resident_pv_cluster_fp_20261108_02/report.json`
- `resident_pv_reader_gate_20261108_02/report.json`

Both receipts, artifacts, source pins (including live documentation), and original
image pins are verified before preparation and inherited into the new seal. The
unchanged accepted numerical runner validates all 68 groups against the original
independent SoftFloat corpus and rechecks the accepted numerical log. The selected
source filelist retains that frozen `chain_soc_20261107_01/source` closure and its
production VMFPU. Only the unused TARGET_VERILATOR define is removed for host VCS.
The real context/package/SRAM hashes must agree with the reader's accepted pins.
The parent reader and adapter are copied byte-for-byte from accepted snapshots.

Original supported groups are IDs 0..32, per-lane elements 16/24/32 (D64/96/128).
All 30 synthetic groups have unequal coefficients between their matrix0/matrix1
lanes and CANNOT be broadcast unchanged. The explicit successor mapping is:

- IDs 0..2: original real3 groups 0..2, all four distinct original lanes retained.
- IDs 3..62: for each original group 3..32, first duplicate its original matrix0
  record across all four lanes, then its original matrix1 record across all four.
  Thus successor ID `3+2*(source-3)+variant`, variant 0 or 1.
- IDs 63..65: replay original real3 IDs 0..2 once with bench stalls disabled.
- Original IDs 33..67: explicitly excluded partial-lane elements 1/3/31, including
  the five special signaling-NaN groups (elements=3). No padding or invented data.

Every selected case body is byte-for-byte the original record. Only header case
IDs are remapped. The selection file is stimulus regrouping, not a new numerical
oracle. It verifies equal complete coefficient payloads across all four lanes,
zero upper 32 bits, exact common geometry, and exact original body counts. It
retains both synthetic variants, all five rounding modes, and one/two heads.
`expected.json` contains each source name, source group, variant, mode, exact
expected counters, and the explicit exclusions for parent review.

## Expected Size

| Item | Stalled gate | No-injected-stall real3 | Combined |
| --- | ---: | ---: | ---: |
| Executions | 63 | 3 | 66 |
| Lane records | 252 | 12 | 264 |
| SIMD FMA accepts/returns each | 28208 | 8768 | 36976 |
| Result words/final acknowledgments each | 2352 | 192 | 2544 |
| Context row reads/latency checks each | 4336 | 1096 | 5432 |
| Coefficient broadcasts | 677 | 137 | 814 |
| 128-bit K/V fill writes | 17344 | 4384 | 21728 |

Each lane must acquire/release 66 times and complete 330 unchanged native probes,
with no reset/cancellation. There are 6246 reader stream emissions, delivered to
each of four lanes. Seeds remain testbench imports, not a production VRF path.

## Wiring And Checks

The real context is filled solely through its aligned 128-bit write port, two
beats per 256-bit row. V rows invert the explicit independent mapping:
physical lane halfslots 0,1,2,3 correspond to natural dimensions
`16*word + lane + {0,8,4,12}`. No DUT permutation function is used. K is the
bitwise-complement sentinel at the same token/dimension. Only the selected shape
is filled; every requested row must be one of those written this execution.

The parent reader drives the existing four-lane cluster directly, followed by
four unchanged adapters and actual production VMFPUs. The bench checks real V
bank/address/order, credit <=2, actual SRAM data after issue and at capture, raw
reader emissions against the original packets (also while stalled), and exact
fanout delivery. The accepted FMA operands/tags/masks/rounding, active return
halfwords/flags, accumulator bytes, result slots/data/byte enables, and independent
final-ack checks remain. Reader completion and cluster completion are separately
retired and counted; reader done is not arithmetic/commit completion. Completion
stalls, late/same/excess final acknowledgments and maximum debt remain covered by
the stalled portion. `finish_gate()` remains after every ownership interval.

The successor calls the original normal-only numerical/native log checker without
weakening it, plus exact context counters and diagnostic-record checks. Host tests
reject incompatible broadcasts, partial shapes, body/header corruption, missing
or corrupt numerical/context/ownership records, bad spans, and live-log collection.

## Local Diagnostics

In the final three replays all bench FPU gates/result readiness are asserted,
seeds/coefficients have no scheduled gaps, and every accepted result is acknowledged
on that same edge. Normal cluster/VMFPU backpressure and adapter preflight/native
probes remain; no ownership bypass, adapter edits, or latency manipulation.

`PV_CONTEXT_TIME` uses absolute rising-edge cycle indices. Inclusive spans are
`last_return-first_coeff+1` and, separately, `last_return-first_fma+1`. It records
first/last context reads, FMA accepts, seed imports, writes/acks, reader completion,
cluster completion, and final native drain. `last_return` means an actual
accepted production FP result, not an expected latency. `PV_CONTEXT_START` and
`PV_CONTEXT_FIRST_FMA` record four-bit owned/gate/adapter-ready masks. Per-lane
ready-stall cycles count FMA valid && !ready and are partitioned by actual ownership;
owned/native-active cycle counts run through final adapter drain. They can overlap
private buffering and seed import. These are diagnostic observations, NOT intrinsic
reader/FMA cost or a complete-call speedup. FMA/write/ack totals remain independently
checked against the original records. No full-call ratio is computed here.

The parent's stronger comparison is full call 34213.5 cycles, PV sum 4411, and an
ideal 2192-cycle FMA floor, giving only about a 6.9% optimistic overall speedup
ceiling. Those are supplied comparison context, not measurements from this gate.
Actual combined diagnostics are a decision input before costly SoC ABI integration.

## Review And Run

```sh
python3 -B verification/performance/resident_rvv/pv_context_fp/test_run.py
python3 -B verification/performance/resident_rvv/pv_context_fp/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_context_fp_AGENT_UNIQUE
```

The default only prepares and seals a fresh output. Review `expected.json`, the
selected lane/schedule files, inherited admissions, and `source-pins.json` before
simulation. Do not edit any sealed live input, including this README or inherited
documentation, while its worker runs. A source change requires a fresh preparation.

Only after explicit parent hash/oracle-map review, launch `inputs/run.py OUTPUT
--execute-prepared --parent-reviewed` as the direct main process of a transient
`systemd-run --user` service. Capture stdout/stderr outside the closed-file artifact
allowlist; never hash still-open service output, even if named with a JSON suffix.
Confirm the actual compiler/simulator in its control group. Compilation is bounded
at 600 seconds, simulation at 180 seconds, each case at 100000 clocks, and existing
native drain at 8192 clocks. No prolonged polling or automatic reruns. Failure
receipts and logs are preserved; no failed case is counted as a numerical PASS.

The runner rechecks all live/snapshot/source/image identities and include-directory
inventories before compile, before simulation, and after simulation. It saves a
PASS only after the original numerical/native and new context checks pass.
