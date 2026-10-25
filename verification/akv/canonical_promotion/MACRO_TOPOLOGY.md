# Bound SRAM topology smoke

This supplements the generic-memory elaboration record in
`MEASUREMENT_WRAPPER.md`. The proposed wrapper itself is unchanged.

## Actual evidence

The wrapper compiled under `TARGET_SRAM_MC` with the existing functional macro
models. A separate one-nanosecond, zero-clock structural smoke binds a reporting
probe to each actual 64x256 or 128x256 macro instance. It reports exactly:

- One Q macro at `i_akv_engine.i_unified_context.i_q_store.i_q_sram`.
- Eight KV macros at
  `i_akv_engine.i_unified_context.i_kv_store.gen_context_bank[0..7].i_context_sram`.
- Q address/data widths 6/256 and KV widths 7/256. Their pinned model definitions
  contain 64 and 128 words respectively, totaling 34816 bytes (34 KiB).

The identical probe, wrapper, filelist and macro-model definitions were also
compiled without `TARGET_SRAM_MC`. That negative control emits the end marker
but zero macro records and is rejected by the same topology checker. Merely
parsing the macro definitions therefore cannot produce an accepted topology.
Missing, extra, duplicate, misplaced or changed records are rejected as well.
Seventeen packaging/static host tests pass, including three topology tests.

Receipt: `macro-topology.json`, binding both logs, executables, source graph,
models, wrapper and checker by SHA256. Compilation and smoke runs each exit zero;
the generic control's topology result is an expected rejection, not functional
hardware failure. The exact inherited TLB warning is admitted; new port-width,
missing-pin and unrelated implicit-declaration warnings are not.

The first probe attempt is retained as a failed testbench compile. Its
hierarchical memory-array `$size` expression was not accepted by this VCS.
The successor uses typed macro bindings and instance reports instead. No RTL,
memory model, expected geometry or hardware parameter changed to obtain PASS.
Compiler recompile summaries can hide inlined modules, so those summaries alone
were deliberately not used to count SRAMs.

## Limits

No clocks or computational transactions run in this smoke. It does not check
SRAM data correctness, the complete engine's numerical behavior, a vendor
timing model, synthesis mapping, measured area, timing or power. Separate SRAM
and full-engine functional tests provide their own evidence. The one-nanosecond
termination only bounds the structural probe. Production files have not been
replaced, and the live-source pin barrier still applies.
