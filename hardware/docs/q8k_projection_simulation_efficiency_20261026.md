# Projection experiment harness efficiency

The original projection runs were intentionally stopped before accepting any
performance result:

- `q8k-decode-projection-pair-20261026-02.service`
- `q8k-context-qkv-pair-20261026-01.service`

Their evidence directories and original sources are preserved. Their status
files may retain the last VCS phase because service termination does not run
the Python worker's normal completion path. Neither is a completed result.

## Measured cause of excessive simulation time

After approximately 30 minutes the first run's scalar commit trace was still
at PC `0x8000017a` through `0x8000018e`. The ELF disassembly identifies this
as the initial weight-buffer FNV loop, loading one byte and multiplying the
running hash on every iteration. The pointer was approximately `0x80033a76`,
against weight range `0x80005340` to `0x80149340`. The vector trace remained
empty. This is measured harness overhead, not a QBS or quantizer stall.

## Successor scope

`projection_pair_fastcheck.c` and `context_qkv_pair_fastcheck.c` preserve the
original measured bodies. Buffers at least 16 KiB use `integrity_words.h`:
RVV accumulates a word sum and an index-weighted sum, with a scalar remainder
for non-word-aligned lengths. Smaller buffers, including numerical output
digests, retain the original FNV computation. The check is non-cryptographic,
as was the original in-simulation FNV check; it is not a proof against all
possible corruptions. Host SHA256 artifact pins, full captured-output checks,
exact paired outputs and memory canaries remain independent safeguards.

A scalar-versus-vector checksum self-test covers 12 lengths, including empty
input, byte tails and partial vector groups. It runs before the experiment.
The checksum is outside the timed regions. Its vector-state changes precede
explicit trial CSR resets and the tested quantizers' own vector configuration.

`test_fastcheck_scope.py` reverses exactly the additional header, large-buffer
dispatch and self-test initializer, and requires byte-for-byte recovery of the
original experiment source. Thus projection work, original/candidate selection,
descriptor construction, timing samples and output checking are unchanged.
The builders reuse the original quantizers and native-command implementation.

New independent runs:

- `verification/out/q8k-decode-projection-fastcheck-20261026-01`
- `verification/out/q8k-context-qkv-fastcheck-20261026-01`

Both run independent QEMU functional preflight before VCS. The expected
benefit is shorter experiment wall time, not improved measured processor
performance. Do not mix partial measurements from stopped predecessors with
the successor's completed paired results.
