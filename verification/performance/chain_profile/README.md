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
