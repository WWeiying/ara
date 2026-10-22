# Gate Successor02

READY, NOT LAUNCHED. The old script and plan01 remain byte-identical.
The new wrapper reuses the reviewed runner and all38 case records, including
ELF paths/hashes, original oracles, per-case budgets,4jobs and stop-first-fail.
Ten original host tests plus three successor tests pass;38 dry-run results
are DRY_RUN only. No terminal extended8 polling or new simulation occurred.

Plan SHA256:
`1410586ddc6e00f7c55239f807497d214c1802c5727dbfb1e0ec1d684841a3bd`.

`gate_config.json` explicitly pins `candidate02_extended8_02`, its preflight
and budget-preflight hashes, exact ELF/image identity and1800/2100 budget
contract. The worker accepts only terminal CANDIDATE02_EXTENDED8_PASS plus
CSV oracle PASS, complete same-image run and zero return code, exact input
ELF, and ALL_PRE_RUN_PINS_AND_IMAGE_UNCHANGED. It checks the recorded worker
command against the budget contract and verifies all budget-contract pins.
Old01 remains historical evidence only, never the selected terminal gate.
Missing or failed evidence refuses immediately; no fallback or gate polling.

After full terminal PASS and explicit parent review, launch with the command
below. It has NOT been executed. No short outer RuntimeMax is set; each of the
38 cases retains its pinned180-1200s inner bound and cancellation behavior.

```sh
systemd-run --user --unit=ara-memory-arithmetic-plan02 --property=Nice=10 \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration/replay_memory_regression_successor.py \
  work --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration/memory_regression_plan02 \
  --authorize-run \
  --approved-plan-sha256 1410586ddc6e00f7c55239f807497d214c1802c5727dbfb1e0ec1d684841a3bd
```

Results, if later authorized, go only under this new directory. Historical
final04 PASS does not substitute for candidate02 arithmetic acceptance.
