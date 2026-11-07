# Inference-chain profiling

Read-only analysis of accepted VCS/FPGA evidence. No RTL, runtime selection,
simulator, synthesis, trace, original checker or original receipt is modified.

```sh
python3 -B -m unittest discover \
  -s verification/performance/chain_profile -p 'test_*.py' -v

python3 -B verification/performance/chain_profile/profile.py \
  --board-observer /home/wangwy/fpga_runs/optimization_board_proof_20261105_01/final_e2e_observer_01 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_NEW
```

The output must not exist. The optional board input is a frozen existing
observation, not a command to connect to or execute on a board.

- `result.json`: checked measurements, exact source comparison, conditional
  budgets, evidence hashes and explicit scope limitations.
- `projection_partition.csv`: exclusive complete-slice timing partition.
- `source_comparison.csv`: original vs current source hashes, including drift.

The original numerical/activity checkers are replayed. Raw log, vector trace,
ELF, source-pin inventory and independent protocol receipts are checked before
accepting RTL measurements. Full dependencies/configuration are not certified
equivalent; the result never claims that this is a new current-SoC run.

Dot issue is not physical lane utilization. Pending/full counters are not
exclusive stalls. UART-window command counts are not timed-ROI IPC. Logical
output-update bytes are not AXI/DDR traffic. Historical board comparisons use
the same bitstream with different software, not no-QBS vs QBS hardware.

The initial engineering report is
`hardware/docs/INFERENCE_CHAIN_PROFILE_20261107.md`.

## Current Area-Baseline Measurement

`hardware/docs/INFERENCE_CHAIN_PROFILE_EXECUTION_20261107.md` fixes the new
measurement scope, production-source boundary and two real Qwen3 inputs.
The run helpers are separate from the historical evidence analyzer above.

- `build_soc.py`: build a Git-archived SoC with accepted frozen dependencies,
  passive UVM and a bounded diagnostic window.
- `q6_decode/build.py`: real M1/K2048/N64 Q6_K Decode projection and full-byte
  Q8 checks, bit-exact output, CSR, guard and work checks.
- `f16_decode/build.py`: real D128/GQA2/137 F16 Decode, uninstrumented/profile
  ABBA and native/captured numerical references.
- `run_campaign.py`: directly owned by a systemd user service, runs a checked
  ordinary-RVV smoke before the two parallel VCS profiling workers.
- `current_results.py`: only accepts finished checked workers, replays their
  numerical checks, verifies pins and independent protocol identities, and
  reconciles native busy counts against passive command lifetimes.

The initial compile worker and first smoke worker had a final JSON-print
exception after writing their artifact receipts. Their failed logs remain.
`admit_soc.py` independently audits the exact committed compile driver and
artifact identities; it does not rewrite the failed worker or relax RTL pins.
The corrected smoke was actually rerun successfully. The explicit F16
`check_successor.py` permits only whole-line zero UVM severity summaries;
it keeps its sealed predecessor's numerical/work/timing gates and original log.

After the campaign finishes successfully, use a new report directory:

```sh
python3 -B verification/performance/chain_profile/current_results.py \
  --campaign /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_runs_20261107_01 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_reconciled_NEW
```

Run all three helper test sets (root discovery does not recurse into these
non-package workload directories):

```sh
python3 -B -m unittest discover -s verification/performance/chain_profile -p 'test_*.py' -v
python3 -B -m unittest discover -s verification/performance/chain_profile/q6_decode -p 'test_*.py' -v
python3 -B -m unittest discover -s verification/performance/chain_profile/f16_decode/tests -p 'test_*.py' -v
```

`PROFILE_RUNS_CHECKED` is not final performance attribution. Exclusive call
phases, engine occupancy, issue-side timestamp intervals and bounded windows
have different meanings. Never add occupancy/stall observations to the call
partition or present these two operator slices as measured full-model cycles.
