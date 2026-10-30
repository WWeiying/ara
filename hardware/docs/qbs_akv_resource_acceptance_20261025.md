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
| Integrated 71-command owner/context handoff | Worker and independent raw audit PASS; all command counter records equal the original baseline | `verification/akv/results/shared-storage-handoff-20261025.json` |
| Integrated 14-command AKV-fault/QBS-reuse/retry sequence | Independent paired raw audit PASS; all command records equal the original dual-reader baseline | `verification/akv/results/shared-storage-reverse-fault-20261025.json` |
| Engine suites through the future canonical-source interface | Both original suites PASS; archived port contracts and explicit copied source graph independently rechecked | `verification/akv/results/canonical-layout-standalone-20261025.json` |
| Shared-reader-only real Decode | All 12 calls and 3680 command records match original output/CSR/counter evidence | `verification/akv/results/shared-reader-real-decode-20261025.json` |

The handoff worker includes source identity, software output checks, independent
protocol checking and settled-negedge waveform checks. A separate offline raw
handoff audit completed under `shared-storage-handoff-audit-20261025-01.service`;
its receipt independently confirms all 71 command records are identical.
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

After a runtime worker has completed, use the independent raw auditor:

```sh
python3 -B verification/akv/shared_reader_integration/audit_real_runtime.py \
  --run verification/out/shared-storage-real-prefill-20261025-01 \
  --output verification/akv/results/shared-storage-real-prefill-20261025.json
```

Use a fresh receipt path. The auditor checks both terminal runs, their matching
ELF/build association, current source/evidence pins, raw output/CSR records and
independent protocol receipts. It reports every measured call separately; a
faster aggregate cannot conceal one slower call. Counter differences require
review rather than being silently accepted as equivalent. The existing Decode
fixture has no complete-call cycle measurements, so it can establish per-call
hardware-counter equivalence, not whole-operator performance. Prefill has actual
complete-call cycles. The original checker scope remains part of each receipt;
protocol independence is not an independent full-Attention numerical oracle.

A separate full-call timing successor now runs the complete original Decode
matrix (D64/H3/T1, D96/H3/T65, D128/H6/T7, D128/H2/T64; OFF/ON/OFF each).
Only the timer and its output protocol are added; no original numerical or
guard check is removed. GNU disassembly confirms the two cycle reads bracket
the public native call and the original drain/fence. The two images consume
one ELF with SHA256
`9eb83100b745d0d70a7f9493d04feafca90365030830c38c6f219163fb98b5b8`.
Actual simulator PIDs 1138904/1139013 were confirmed at launch. Outputs are
`verification/out/akv-timed-decode-{baseline,unified}-20261025-01/`.
Here baseline means the original full QBS+AKV resource implementation, NOT
ordinary RVV. These are pending performance tests, not passing evidence.
Use `audit_timed_decode.py` to require exact command ledgers and no slower
individual call before accepting the paired performance result.

## Bounded attribution scheduling

The accepted four-trial strided runs took about 2.3 hours each. Completed logs
show 3.76--3.78 million cycles outside the timed calls, including preparation,
checking and output. Extending to six H/S/B/B/S/H trials risks the unchanged
10800-second simulator bound; none of this residual is a disjoint stall counter.

The successor `verification/akv/quantized_kv/fast_hex/` replaces only per-word
`printf("%08x", ...)` with eight direct `_putchar` operations. It emits exactly
the same 36,864 lowercase hex characters over six trials. Inverse source
transformation and the timed source region match exactly. Host tests compared
196,626 values (1,573,008 characters), including boundaries, all 16-bit values
and deterministic 32-bit samples. This is an output-cost optimization, not a
hardware or kernel acceleration result; identical source windows do not prove
identical machine code or promise a run below three hours.

Both Q4/Q8 successor ELFs cross-built and passed scheduling-input inspection;
this does not assert the pending tail gates passed.
`akv-quantkv-tail-fasthex-coordinate-20261025-01.service` now owns preparation
and the event-driven dependency queue; it must observe all four checked tail PASS
results before combining, checking both preflights and launching either H/S/B
simulator. The actual simulator bound remains 10800 seconds. The coordinator's
larger outer bound covers waiting and preparation, not a longer simulation.

The superseded pending-only coordinator was intentionally stopped with no
children/downstream jobs; existing VCS runs were left running. Its original
receipt reports `TimeoutError` because Python's selector swallowed the old
`InterruptedError` signal handler. This is not evidence of a timed-out RTL
simulation. The original receipt is preserved; `coordinate_v2.py` uses a distinct
stop exception and retains the monotonic deadline across empty selector returns.
The fresh launch receipt records the replacement and original receipt hashes.

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
