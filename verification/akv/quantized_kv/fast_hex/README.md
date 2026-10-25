# Printing-only H/S/B successor

This directory does not modify any sealed source, checker, worker, or coordinator.
It is an opt-in build factory, not a launched experiment. It preserves the six
H/S/B/B/S/H trials, all output words, lowercase hex encoding, counts, delimiters,
checks, arithmetic, and native traces. No checker change is required.

`hex32.h` exposes `static inline void fast_hex32(uint32_t)`. It writes exactly
eight characters through the same `_putchar(char)` used by the baremetal printf,
with a constant digit table and eight shifts/masks. There is no newline, division,
printf parser, global output buffer, or vector/floating-point operation in it.

`render.py` requires original main SHA256
`1c0eb4bdaca3fc171931885392c6644920877889059c3761a7a084ba0f6b758a`.
Its sole executable-source substitution is the output loop's
`printf("%08x",bits(output.data[head][d]))` to `fast_hex32(...)`. It additionally
qualifies two includes against the existing root include path and adds the emitter
include. The original common headers still resolve from their original directory.
The inverse must reproduce every original byte and hash. The complete rdcycle
measurement region is byte-identical source, not claimed byte-identical machine
code: a rebuilt main can change addresses or compiler register allocation.

## Host tests only

From the signoff root:

```sh
python3 -B -m unittest discover -s verification/akv/quantized_kv/fast_hex -p 'test_fast_hex.py' -v
```

The GNU host C test compares actual stdout against `%08x`: 18 boundary values,
all 65,536 low-16-bit values, all 65,536 high-16-bit values, and 65,536 deterministic
xorshift32 values. This is 196,626 words / 1,573,008 characters per implementation.
Other tests check inverse/drift rejection, timing source identity, includes,
private factory overrides, reused objects, and the unchanged build-reader schema
with explicitly dummy artifacts (not a native build).

## Deferred cross build

Only after parent review, the following command builds a new ELF; it never runs a
simulator. It was NOT executed as part of this implementation task.

```sh
python3 -B verification/akv/quantized_kv/fast_hex/build.py \
  --base verification/out/akv-quantkv-strided-attention-q8-build-20261024-01 \
  --output verification/out/akv-quantkv-threeway-fast-hex-q8-build-20261025-01
```

Use the corresponding q4 strided base and a fresh q4 output for Q4. The consumable
build directory is `OUTPUT/build`, not the container `OUTPUT`. Generated source
and `render.json` are retained in `OUTPUT/source` and pinned by the build receipt.

The wrapper imports the immutable `build_threeway_attention.py` under a unique
module name and changes only that instance's `MAIN`. Its original compile/link,
FP flags, dependency scan, image identity, bounds, and disassembly checks remain.
It recompiles main.o and explicitly inventories all reused objects/libraries
other than the old main.o. No old ELF is relabeled as the successor.

The report retains `THREEWAY_ENTRY_BUILT_NOT_EXECUTED` and adds `producer`,
`source_variant=FAST_HEX32_PUTCHAR_STDOUT_IDENTICAL`, `source_provenance`,
`build_factory_sha256`, `reused_link_inputs`, and `rebuilt_link_inputs`. Original
source, factory, emitter, renderer, tests, README, generated source, and render
receipt are pinned pre/post. Artifact hashes are refreshed after pin publication;
the report never hashes itself. Any post-factory failure leaves state FAIL.

The purpose is to reduce unmeasured formatting work. No kernel acceleration,
measured walltime improvement, or completion within three hours is claimed.
Choosing/replacing the pending coordinator remains a separate parent decision.
