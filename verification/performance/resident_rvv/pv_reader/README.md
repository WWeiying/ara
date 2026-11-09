# Resident V Reader Gate

Host VCS transport gate for the experimental `akv_resident_pv_reader.sv`.
Only the testbench, runner, documentation and host tests are owned here by the
gate author. The parent-owned reader is an input, never rewritten by this gate.

## Frozen Inputs

Admission is `resident_pv_vmfpu_20261108_04` under the signoff worktree's
`verification/out`. Its accepted filelist and source pins select only the package
closure, real `akv_v2_context`, and real `tc_sram` from the same frozen
`chain_soc_20261107_01/source` tree. No local dependency substitutions, mock
memories, bus changes, synthesis, Verilator, URG or coverage reporters are used.
The unused inherited `TARGET_VERILATOR` define is excluded for this VCS top.

Every invocation requires a fresh signoff output directory. All selected frozen
files and all five local inputs (including this README and tests) are copied and
hashed. The original live paths remain pinned too. Identities are checked before
compile, before simulation and after simulation; the compiled image is pinned.
Do not edit these inputs while a consumer is running. Failure receipts are never
overwritten. Unselected historical inputs are not claimed to be revalidated.
Artifact collection is an explicit allowlist of closed gate logs/receipts and
pinned input snapshots. Service stdout, `worker.log`, and arbitrary added files
are excluded, even when a launcher places them inside the output directory.

## Checks

- The real context is filled with 2048 aligned 128-bit writes, two halves per
  256-bit row, across all 64 tokens and 8 words for both K and V. `write_busy_o`
  mirrors write-valid, not a ready handshake; read traffic starts after filling.
- V is a natural `[token][dimension]` raw-halfword array generated independently
  of the DUT; K is its bitwise-complement sentinel. Output lane halfwords use
  `16*word + lane + {0,8,4,12}`. The checker never calls the DUT shuffle helper.
- All nine `words={4,6,8}`, `tokens={1,9,64}` combinations run without stalls and
  with deterministic coefficient/value/final-word stalls. Accepted order and
  counts, stable valid/data/kind, busy start rejection and latched metadata are
  checked. Illegal words and token counts 0/65/127 produce held error completion.
- Three cancels target an actual outstanding SRAM read, one per word count,
  then immediately reuse the context without reset. Completion is held six
  cycles. External issued-minus-delivered credit never exceeds two.
- Each request checks the actual single-bank V address; no K or column reads
  are allowed. Raw SRAM data is checked after the request's active edge and
  again at the next capture edge, directly verifying configured latency one.
  A different latency fails the gate instead of changing the reader assumption.
- Completion means the last stream beat was accepted, not that FP execution or
  accumulator commit finished. There is no FP unit in this gate.

Expected receipt: 40 cases (21 successful, 16 invalid, 3 cancelled), 2829 reads,
2826 delivered V words, 474 coefficient broadcasts, and 2829 SRAM latency checks.
Patterns test raw transport, not numerical FP semantics or real-model accuracy.

## Run

```sh
python3 -B verification/performance/resident_rvv/pv_reader/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_reader_AGENT_UNIQUE
```

`--prepare-only` snapshots without compiling. The runner has a single 540-second
wall budget for host tests, compilation and simulation, killing its process group
on timeout. The bench also bounds each transaction and the entire simulation.
Longer follow-up work requires a separately owned background worker, not repeated
foreground retries. Reports are `report.json`, `source-pins.json`, `image-pins.json`,
`source-selection.json`, `commands.json`, and test/compile/run logs.

This gate does not establish immutable-area cost, SoC integration, performance,
FPGA acceptance, or NORMAL_MEMORY eligibility. Those remain separate reviews.
