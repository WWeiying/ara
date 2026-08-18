# FSDB cycle trace extraction

`extract_cycles.py` converts a selected part of an FSDB database into a compact,
clock-aligned trace. It deliberately does not expand every dumped signal.

The extractor writes:

- `cycles.csv`: one row per sampled clock edge;
- `events.csv`: only signal transitions, with old and new values;
- `metadata.json`: source FSDB, time window, selected/missing signals, and command;
- `fsdbreport.raw.csv`: unmodified Synopsys output for audit;
- `fsdbreport.log`: tool messages.

## Ara example

Run the command from the repository root. Always select a bounded time window
for a large FSDB:

```bash
python3 hardware/scripts/fsdb_trace/extract_cycles.py \
  --fsdb hardware/sim_l2_16m/ara_tb.fsdb \
  --profile hardware/scripts/fsdb_trace/profiles/ara_compute.json \
  --begin 120us --end 125us \
  --output hardware/fsdb_traces/decode_attn_q_120us_125us
```

Select only the multiplier/FPU and lane data path, and inspect lane 2:

```bash
python3 hardware/scripts/fsdb_trace/extract_cycles.py \
  --fsdb hardware/sim_l2_16m/ara_tb.fsdb \
  --profile hardware/scripts/fsdb_trace/profiles/ara_compute.json \
  --group lane,compute --set lane=2 \
  --begin 120us --end 121us \
  --output hardware/fsdb_traces/lane2_compute
```

The `monitor` group contains the strict performance-monitor inputs: benchmark
phase, request operation/VL, queue and in-flight state, per-lane execution and
result fires, and each separately classified request-block reason. It is the
smallest useful group for identifying a long-cycle bottleneck before opening a
more detailed lane or VLSU trace.

Add a temporary signal without editing the profile:

```bash
python3 hardware/scripts/fsdb_trace/extract_cycles.py \
  --fsdb hardware/sim_l2_16m/ara_tb.fsdb \
  --profile hardware/scripts/fsdb_trace/profiles/ara_compute.json \
  --group compute \
  --add-signal issue_op=/ara_tb/dut/i_ara_soc/i_system/i_ara/gen_lanes[0]/i_lane/i_vfus/i_vmfpu/vinsn_issue_q \
  --begin 120us --end 120.1us \
  --output hardware/fsdb_traces/mfpu_issue
```

List available groups without opening the FSDB:

```bash
python3 hardware/scripts/fsdb_trace/extract_cycles.py \
  --fsdb ignored.fsdb \
  --profile hardware/scripts/fsdb_trace/profiles/ara_compute.json \
  --output ignored --list-groups
```

The profile uses aliases such as `mul_exec_fire` and `axi_ar_fire`, so the CSV
does not expose long RTL hierarchy names. Optional signals absent from an older
FSDB are listed in `metadata.json`; a missing required signal makes the command
fail. `cycle` is relative to the selected window, while `time_100fs` is the
original FSDB timestamp for this project's `1ns/100fs` simulation timescale.
Keep this field as a raw timestamp when comparing traces compiled with a
different timescale.

To add a diagnostic scenario, copy the JSON profile and retain only the signals
needed to prove or disprove the hypothesis. Prefer request `valid`, `ready`,
operation/ID, queue occupancy, execution fire, and result fire signals. That set
usually identifies where a request stopped without generating an unmanageable
trace.
