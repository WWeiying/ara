# Source-queue import acceptance

Accepted host VCS run:
`ara_dsa_signoff_integration/verification/out/resident_pv_import_agent_20261108_01`.
The parent independently inspected the scoreboard and rechecked source, image
and artifact identities after completion: no drift.

| Item | Result |
| --- | ---: |
| Scenarios | 170 PASS |
| Normal imports, including post-cancel reuse | 108 |
| Cancels during seed/coefficient/unused-source drain | 18 |
| Invalid configurations rejected before queue admission | 44 |
| Consumed owned source words, across all lanes | 12096 |
| Owned source command completions | 504 |
| Intact following-command sentinel words | 504 |
| One-cycle operand returns checked | 12600 |
| Host checker tests | 10 PASS |

All D64/D96/D128, one/two heads and T1/8/9/63/64 combinations are covered with
unstalled, deterministic-stall and reproducibly randomized-stall consumers.
Unequal lane arrival, held coefficients, seed ordering, inactive seed suppression,
source credit bounds and full 24-word-per-lane drainage are checked against a
natural-order raw-bit reference. The four real production operand queues retain
their normal command/data FIFOs. There is no new coefficient payload array in
the importer.

The following-command test observes queue preservation by switching the bench
consumer after import reaches held Done. It does not implement a production
VLSU owner switch or prove the actual store path executes. Likewise, these are
transport tests, not FP numerical or architectural-instruction tests.

The next integration must combine this importer with the context/FPU path and
require successful source drainage before authorizing any architectural write.
The existing isolated cluster barrier does not yet receive this prerequisite.
It is insufficient to hold external ready low after commit has already been
authorized: cancellation must remain legal until all precommit conditions pass.
Source owner release also waits for floating-point completion and final writes.

Fixed source geometry, source/destination alias rejection, register reshuffling,
CPU issue/retirement, CSR/exception handling, SharedFma=1 and complete-call
performance remain separate acceptance requirements. The production fast path
has not been enabled by this test.
