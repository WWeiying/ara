# Isolated unified AKV payload storage candidate

Status: implemented, pending static review and bounded VCS unit execution.
No production engine/RTL, accepted repacker, or shared-reader snapshot is changed.
Host tests validate evidence handling and source closure, NOT hardware behavior.

## Composition and exact interface

`akv_unified_context.sv` instantiates ONE unchanged `akv_v2_context` for K/V,
ONE unchanged `akv_legacy_repacker`, and ONE new `akv_q_store` for Q. There is
no instance of `akv_context` in the candidate (only in the comparison TB).

- `legacy_write_*`: accepted compact 128-bit payload fragments with low contiguous
  byte strobes. Slots 0..7 are Q rows, 8..15 K tokens, 16..23 V tokens.
  `legacy_row_bytes_i` is 9 bits and must equal 128, 192, or 256. Tags cannot
  interleave within a row, offsets are logical/even, and the first offset is 0.
  D96 exercises the adapter; this does NOT extend the legacy instruction ABI.
- `v2_write_*`: original aligned 128-bit K/V write interface, tokens 0..63,
  offsets 0..240 divisible by 16, original byte strobes. No added write register.
  A final Q fragment can be immediately followed by v2 K/V input. Pending Q
  emission and direct KV consumption use different SRAMs and may overlap.
  There is no new ready/arbiter: two input-valids in one cycle or simultaneous
  repacked KV and direct KV writes are illegal. External command serialization
  still prevents mixing legacy KV rows and v2 KV writes within a command.
- `legacy_replay_*`: 256-bit word replay, words 0..7, original slot mapping.
  V2 Q uses this same Q path and still supports all eight Q rows.
- `v2_row_*` and `column_*`: original v2 interfaces, unchanged. Legacy K/V and
  v2 replay access the SAME physical bytes. Registering the legacy Q/KV select
  alongside the SRAM read preserves one-cycle row replay, without an output stage.
- `write_busy_o`: includes accepted input, adapter pipeline, partial-row pending
  state, and unconsumed emission. A completed legacy row's last write reaches
  SRAM two rising edges after its last fragment capture, like the old context.
  Direct v2 busy remains its valid; do not invent a registered v2 write drain.
- `abort_i`: write-phase cancellation, not a replay/column cancellation. Masks
  unconsumed writes at the current edge and clears adapter pending/pipeline on
  that edge. Does not clear SRAM or roll back writes already consumed. It is
  illegal to replay/start a column, or have a column busy, during abort.

The future engine integration must pulse abort on payload fault/flush before
waiting for write-busy to clear: an incomplete row intentionally stays busy
until abort. Use the existing engine success drain (`payload_complete`) and
existing fault/context invalidation policy. The wrapper holds NO context-valid,
descriptor, generation, or command metadata. It does not make failed REFILL
replayable. Failed REFILL writes only K/V, preserving committed Q physically.
Mode changes invalidate the previous context as before; simultaneous independent
legacy and v2 contexts are not a supported ownership model.

## Storage shapes

| Store | Instances x depth x bits | Logical capacity |
| --- | --- | --- |
| New Q | 1 x 64 x 256 | 2 KiB |
| Unchanged v2 shared KV | 8 x 128 x 256 | 32 KiB |
| Old legacy reference (TB only) | 2 x 96 x 256 | 6 KiB |

Candidate payload SRAM totals 34 KiB versus the previous 38 KiB. These are
logical capacities, NOT area, power, timing, or whole-engine bit counts. Adapter
registers and the original v2 column capture registers still exist.

The generic profile uses the existing `tc_sram`, one port and latency 1. The
macro profile uses actual TT library models for
`TS1N28HPCPUHDSVTB{64,96,128}X256M1SWBSO`, with `TARGET_SRAM_MC` and the original
byte-to-BWEB convention. The 96-depth model is only for the old legacy reference.
Macro unit execution disables specify/timing checks: it tests functional wiring,
not timing signoff. No replacement/fake SRAM models are generated. `config/sram.mk`
and all model/source files are pinned.

## Unit obligations

`unified_storage_tb.sv` compares old legacy and old v2 outputs with the candidate,
and also checks an independent logical-coordinate byte scoreboard. Payloads are
deterministic synthetic storage patterns, not attention numerical/model evidence.

- 24 full legacy slots followed by every even physical alignment for all three
  row lengths and streams, with gaps, unchanged tail bytes, and chained rows.
- All 8 Q rows and 64 K + 64 V rows; immediate Q-to-direct-K transition with
  two overlap cycles; direct write control/data/byte-enable/bank-address equality.
- Every row word; legacy low-token aliases after a v2 fill; one-cycle row latency.
- Scalar and PANEL4 columns on both streams, dimensions spanning bank-word
  boundaries and token counts 1/7/8/9/63/64, including inactive output zero padding.
- Seven partial pending sizes, registered emission plus younger stage cancellation,
  and already-committed-prefix retention. All nine aborts check Q unchanged.
  Then a complete recovery row is compared against the old context and oracle.

Expected (not yet observed) terminal counts: 105 completed rows/last-write latency
checks, 1361 repacked writes, 2048 direct writes, 2704 checked row words, 72 checked
column outputs, 9 aborts, 2 Q/direct overlap cycles. TB watchdog is 500 us simulated.
This is storage composition proof only, not actual reader-fault injection, engine
ownership, metadata invalidation, SoC context survival, or performance proof.

## Prepare, review, then execute

From the signoff root:

```sh
python3 -m unittest discover -s verification/akv/unified_storage_candidate -p 'test_*.py' -v
python3 verification/akv/unified_storage_candidate/run_unit.py \
  --sram tc --output verification/out/akv-unified-storage-unit-tc-20261025-01
```

Preparation verifies the accepted repacker unit-03 source/evidence pins, records
canonical context/engine/SRAM and new candidate sources, compiler tools, exact
commands and expected counts. It invokes NO compiler or simulator. Review the
manifest and source before authorizing:

```sh
python3 verification/akv/unified_storage_candidate/run_unit.py \
  --output verification/out/akv-unified-storage-unit-tc-20261025-01 \
  --execute-reviewed MANIFEST_SHA256
```

Compile is bounded to 300 seconds; unit execution to 60 seconds. SIGTERM/timeout
cleans the child process group. Pre/post identities, exit codes, exact nonduplicate
terminal counts, and fatal/error text are checked. A terminal or partial output
cannot be rerun. Retain failures. Macro preparation uses a separate fresh output
and `--sram macro`, with its own review/hash. Do not run either until approved.
