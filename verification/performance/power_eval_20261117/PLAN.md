# Paired mapped-netlist power campaign

## Scope and gates

Use the completed all-on `870cadb9f32c79df8d30ab845e4dd2e463a00540`
DC netlist, not the current production HEAD. Find and identify the historical
RVV/no-QBS mapped baseline independently. Do not replace either netlist or
modify production RTL/SDK. No new synthesis, FPGA programming, Verilator or URG.

1. Pin netlist, DDC, libraries, frozen RTL and configuration for each side.
2. Build matching RTL simulators. Model SRAM behavior without changing memory
   dimensions or latency. Disclose simulation-only wrappers and probes.
3. Run checked RTL firmware, at most four simulator processes concurrently.
   Check numerical results, completion, memory bounds and actual execution path.
4. Only after prechecks pass, build gate simulators and run a short gate smoke.
5. Collect bounded representative gate-level VCD windows, convert to SAIF and
   report DC power using the corresponding DDC/library set in the EDA container.
   VCS runs on the host. Do not reuse incompatible historical SAIF blindly.

## Workloads

| Workload | Shape | Paths |
|---|---|---|
| Qwen3 Q4_K single-row projection | M1 N64 K2048 | Established x32 RVV / QBS |
| Qwen3 Q4_K prefill projection | M4 N64 K2048 | Established x32 RVV / QBS |
| Historical Q8_0 projection | M1 N256 K896 | Historical RVV / QBS |
| Qwen3 F16 decode Attention | D128, 2 query heads, KV137 | Memory RVV / native AKV |

The selected Q4_K M1 program is the real position-40 decode capture in
`operator_projection_real_prepare_20261115_release_01`, not the older M1
prefill-row calibration specimen. M4 selects four distinct captured prefill
rows. Historical Q8_0 fixture identity must be proved before its legacy
comparison is admitted. An alternate fixture must be labeled separately,
not silently substituted.

## Measurement contract

Capture normal compute AND memory-wait cycles across complete blocks/tiles.
Exclude startup, result printing and checking. Separate paths into separate
windows; never average an ELF's RVV and custom arms together. Save exact window
times and cycles, code/input hashes and numerical/protocol acceptance.

The primary deliverable is representative average dynamic/leakage/total power
and module breakdown. A bounded activity window alone is not whole-task energy.
Any 1 GHz estimate is explicitly a frequency assumption: the selected all-on
netlist has a negative setup slack at the 1 ns constraint and is not a signed-off
1 GHz implementation. Zero-delay mapped simulation does not prove timing closure.

Retain historical artifacts. Failed cases and truncated captures are not relabeled
as completed successful executions. Background workers own their subprocesses
directly, have bounded execution and write status/results. Do not poll long jobs.
