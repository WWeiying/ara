# Candidate02 Extended8 Successor

Implementation: `successor.py` and `csv_check.py`. The original eight-case
`reference01/soc.elf`, fixtures, oracle and sealed helpers are unchanged.

Preflight output: `candidate02_extended8_01/preflight.json`.
It binds the built image, all539 frozen sources, the original ELF, symbols,
reference pins, new scripts and a sealed-runner DRY_RUN. The parent gate observed
all3 Sv39 plus all10 smoke cases PASS with the same simulator image hashes.
The worker rechecks the gate once immediately before launching; missing, running,
failed, duplicated or mismatched parent evidence is an immediate refusal, never
an unbounded wait or retry loop. Each parent's per-test inputs.json and input.elf
must agree with its program manifest and the current image.

Offline evidence: `adapter_tests01/tests.json`. A synthetic full eight-case CSV
exercises the state machine and all6227 comparison calls; it is not DUT evidence.
Sixteen CSV corruptions and nine parent-gate corruptions are rejected. In addition,
7956 scalar stores from a real archived passing SoC CSV were decoded, including
1111 with shifted byte-lane masks. This validates the monitor convention that
mem_wmask is lane shifted while mem_wdata remains an unshifted source value.

CSV acceptance checks every executed `check(got,want)` from committed GPR values,
per-case and total counts, setup args/mask/denied leaf, all13 checkpoints, actual
handler CSR reads versus records, exact cause/PC/tval/vstart, repair PTE/SFENCE,
unchanged retry mepc, restored vstart and prefix poison, target opcode/order,
raw post CSRs, younger marker, S ECALL record, completion magic and CTRL0.
The runner separately requires its architectural PASS marker and validated CSV.
Vector memory writes are not invented from scalar RVFI: the unchanged full-data
software oracle supplies that evidence, and the CSV checker verifies each actual
comparison. FOF's original unspecified elements4-7 remain the only original
shortening exclusion. Cycle limits are diagnostic; a slow/incomplete run is never
promoted to PASS.

The authorized background invocation is a single worker/ELF, jobs1, with a
1200-second simulator timeout. A systemd user-service RuntimeMaxSec=1200 and
KillMode=control-group provide an outer bound and descendant cleanup. If the outer
deadline fires before postprocessing, preserved CSV must be analyzed separately;
absence of complete.json is not PASS. No automatic rerun/rebuild is implemented.

```sh
python3 -B verification/fpga/current_board_review/masked_translation/sv39_extended/successor.py worker --out verification/fpga/current_board_review/masked_translation/sv39_extended/candidate02_extended8_01 --authorize-run
```

This command requires successful saved preflight and a fresh worker owner file.
It blocks on the bounded runner process, not on repeated parent-status/trace
polling. Analyze only after completion. Relevant outputs are worker.json,
worker.log, run/summary.json, run/tests/extended8/commit_trace.csv,
csv_analysis.json and complete.json. Any PASS applies only to this exact
candidate02 image and the eight selected cases, not Linux or open fault-epoch
and delayed-final-grant families.
