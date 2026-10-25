# Shared reader and unified AKV storage: integration checkpoint

This is a successor evidence note. It does not rewrite the historical execution
plan or any source pinned by a running worker. Work belongs to
`ara_dsa_signoff_integration`; canonical production RTL has not been replaced.

## Hardware change

The isolated snapshot combines one physical QBS/AKV read engine with one AKV
context implementation. Command ownership, outstanding capacity, computation,
translation and terminal handling retain the existing controller behavior.

The context contains a separate 2 KiB Q store and one 32 KiB K/V store. Legacy
unaligned fragments pass through the checked repacker; direct v2 K/V writes
retain their existing path. Compared with the old 6 KiB legacy plus 32 KiB v2
payload stores, this removes 4 KiB of logical storage. This is not measured
cell area, timing, power or a whole-model speedup.

## Completed evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Generic SRAM and TSMC functional-model storage units | PASS in both configurations; each checks 105 rows, 2704 row words, 72 column outputs and 9 aborts | `verification/akv/results/unified-storage-unit-20261025.json` |
| Original QBS standalone suite through the extracted-reader composition | All 36 functional cases and four fault classes PASS | `verification/out/shared-storage-standalone-qbs-20261025-01/` |
| Original AKV standalone suite | v1 D64/D128, v2 D64/D96/D128 and segmented D256 row/column cases PASS, including tails, counters and faults | `verification/out/shared-storage-standalone-akv-20261025-01/` |
| Source, testbench and build audit | Exact inverse TB transformation; no changed expected data/assertions; 124 full-SoC warning blocks unchanged | `verification/akv/results/shared-storage-component-audit-20261025.json` |
| Integrated 71-command owner/context handoff | Worker PASS; all command counter records equal the accepted shared-reader predecessor | `verification/out/shared-storage-handoff-20261025-01/` |
| Integrated 14-command AKV-fault/QBS-reuse/retry sequence | Independent paired raw audit PASS; all command records equal the original dual-reader baseline | `verification/akv/results/shared-storage-reverse-fault-20261025.json` |

The handoff worker includes source identity, software output checks, independent
protocol checking and settled-negedge waveform checks. A separate offline raw
handoff audit is owned by `shared-storage-handoff-audit-20261025-01.service`;
its receipt must exist and pass before claiming that additional audit complete.
PMA read faults are covered here; this is not proof of every translated Linux
page-fault restart or a held-AR fault condition at SoC level.

## Real-input regressions now executing

The unchanged accepted real-input ELFs run on the new storage image in separate
direct-owned services. Actual simulator processes were confirmed once:

| Gate | Service | Simulator PID at launch confirmation |
| --- | --- | --- |
| Decode | `shared-storage-real-decode-20261025-01.service` | 1126479 |
| Prefill | `shared-storage-real-prefill-20261025-01.service` | 1126591 |

Outputs have the corresponding names under `verification/out/`. Launch evidence
is not a passing result. Acceptance requires terminal PASS, unchanged source and
image pins, independently checked output/CSR/protocol results, and comparison
with the recorded baseline cycles and command counters. No long-run polling is
needed. Previous shared-reader-only regressions remain independent evidence and
must not be relabeled as tests of unified storage.

## Remaining production and objective gates

1. Finish the actual unified-storage Decode/Prefill gates and their raw audits.
2. Review the completed four quantized-KV prefix tests. The event-driven
   coordinator launches same-ELF H/S/B attribution only after all four checked
   PASS results; partial logs and timeouts are not accepted coverage.
3. Before canonical source promotion, inventory live source pins and preserve
   their closures. Promote the reviewed reader/storage RTL and source graph as
   one coherent change, then test that canonical graph, not only this snapshot.
4. Preserve standalone interface compatibility deliberately. The present
   test-only composition reads the old canonical engine header; archive that
   contract or migrate the benches before replacing that header. Do not weaken
   post-terminal counter checks to accommodate an interface migration.
5. Continue full-runtime/model and operator-level attribution obligations in
   `qbs_akv_efficiency_execution.md`. Passing component tests does not complete
   the overall prioritized goal. No synthesis or physical closure is included.

Version checkpoints: `602d730b` records storage integration helpers, original
engine-suite compatibility and the component audit; `c859a834` records the
event-driven quantized-KV acceptance/attribution coordinator. Neither checkpoint
changes canonical hardware or the external llama.cpp worktree.
