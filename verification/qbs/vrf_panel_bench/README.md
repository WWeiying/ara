# Real Long-K Matrix Comparison

This test compares two full-K QBS commands against a two-output-tile,
nine-stripe traversal using QBEXEC then QBACC. Both schedules produce the same
256 outputs from real Q6_K FFN-down data, M4/N64/K8960. They share C preflight,
capability discovery, the assembly leaf and the final eight output stores.
DIRECT/striped/striped/DIRECT run from one ELF and one SoC image.

The timed boundary includes descriptor/record construction, validation, native
capability reads, fences, command dispatch, activation reuse, architectural
partial-sum reads, intermediate VRF commits and final store drainage. Input
activation quantization/packing and offline weight repacking are excluded.
This is a matrix-phase result, not full production preparation or model speedup.
The two weight layouts contain exactly the same logical blocks. Their physical
addresses and burst splits can differ; record AR/beat/range counts rather than
attributing every cycle change solely to the arithmetic engine.

Data is produced by `verification/qbs/vrf_panel_data/prepare.py`. Its packed
activations are reference-derived and match the previously accepted complete-K
vector. Its monolithic expected bits also match captured llama outputs for all
256 selected outputs. The benchmark checks raw bits, flags and guards after
every timed call; it never sums independently accumulated stripe totals.

```sh
python3 verification/qbs/build_vrf_panel_bench.py \
  --data verification/out/qbs-vrf-panel-data-20261023-01 \
  --panel-build software/qbs/experimental/vrf_panel/build-gnu-02 \
  --output verification/out/qbs-vrf-panel-bench-build-NEW

python3 verification/qbs/run_vrf_panel_bench.py \
  --gate verification/out/qbacc-soc-accept-20261023-02 \
  --build verification/out/qbs-vrf-panel-bench-build-NEW \
  --output verification/out/qbs-vrf-panel-bench-NEW
```

Every output directory must be new. The worker waits on the prerequisite's
process-exit event, not a status polling loop. It runs only after the actual
QBACC instruction/CSR/layout/fault test and unchanged RVV/QBS-AKV neighbors
pass. It then checks the original image/source manifest, unchanged inputs and
independent UVM protocol/backend/AXI observations. Simulation is bounded to
three hours and does not launch synthesis, Verilator or URG.

Hardware records must show 40 total commands, 32 seeded continuations, 20480
VRF result bytes and 16384 source-seed bytes over the four calls. Each striped
call has nine successful FILLs, nine reuses including final RELEASE, and saves
40880 external activation bytes. Logical read payload, including descriptors,
is 552192 bytes per DIRECT call and 511568 per striped call. These are expected
traffic budgets, not measured speedups. `test_vrf_panel_bench.py` checks parser
rejection of missing/duplicate work, wrong traffic, flags, source masks and
missing VRF writes.
