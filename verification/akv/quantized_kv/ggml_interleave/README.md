# Persistent Projection AQ Across Quantized Attention

## The Integration Risk

A projection may retain its quantized activation for another projection later
in the same GGML graph. An intervening Attention must not wait for that
reservation to be released: its consumer cannot run until Attention finishes.
Nor should Attention invalidate the retained activation merely to use QBS.

This test constructs three actual GGML nodes in a checked order:

```text
Q4_K projection, using activation A
    -> real captured quantized Decode Attention, using distinct Query B
    -> Q4_K projection, reusing the same A
```

The projection is a synthetic finite control fixture, M1/N64/K256, not a
performance workload. Attention uses unchanged real captures for K=Q8_0 or
Q4_0, V=Q8_0, D128, 12 Query heads, 2 KV heads and 128 visible tokens. This
combines a discriminating ownership test with real Attention operands.

N64 is intentional. The current runtime refuses activation-context plans whose
entire N dimension fits in one command. Such an ordinary operation cannot both
FILL and RELEASE with one access mode. N32 therefore cannot establish this
software reservation test; increasing N to two N32 tiles selects the existing
policy without changing the runtime or hardware.

## Required Evidence

Each profile first runs the graph with context/cross-op/quantized-Attention
disabled, then repeats twice with all three enabled. The expected native order
is:

1. `fill_keep` reservation, followed by FILL and REUSE projection commands.
2. Complete quantized Attention: 16 DIRECT commands, two KV groups, 256 V decodes.
3. `reuse_release`, skipping activation quantization, followed by REUSE and
   RELEASE projection commands.

All four projection commands must use the same generation and activation
sequence; the ownership source and graph epoch must agree. Every projection
output must equal the baseline bit for bit, both projection results must agree,
and all1,536 Attention outputs must satisfy the original per-element tolerance.
Repeated Attention outputs and FCSR must agree; final VCSR must match the
ordinary production graph at3. The test starts at5, but the existing Q8_K
quantizer explicitly emits `csrwi vxrm,1` for RNE `vnclip`, retaining sticky
VXSAT=1. Source and the linked library's disassembly confirm that change; it
must not be mislabeled as an Attention failure or forced back to5. Inputs and
packed weights must remain unchanged. All outputs are poisoned before each run.

The binary deliberately prints `NUMERICAL_PASS`, not full acceptance. The
parent additionally checks actual lifetime/command traces and their ordering.
Three checker tests include missing work, false reuse, generation mismatch,
unexpected native execution, CSR errors and failed guest status.

## Execution And Scope

The worker reuses the already tested native GGML static libraries without
rebuilding or changing them, and pins those archives alongside the accepted
live-graph inputs. It builds only this separate test and packages the same real
capture files and guest init. Linux QEMU is used for functional custom-opcode
and graph-lifetime checks, never for RTL performance.

`...ggml-interleave-20261024-01` and `-02` retain compile failures caused by
missing internal-header paths and external-header warnings. `-03` retains the
N32 context-ineligible fixture failure. `-04` retains the mistaken initial-VCSR
preservation assertion failure on the ordinary baseline. None is accepted or
relabeled. The N64 successor with the production quantizer CSR contract uses
`verification/out/akv-quantkv-ggml-interleave-20261024-05`.

This does not prove arbitrary concurrent graphs, OS migration, direct-command
fault recovery, whole-model generation or RTL timing. Those remain separate
gates even after this focused lifetime test passes.

## Accepted Result

The `-05` successor passes all six actual GGML graphs: one baseline and two
native runs for each real K format. All four native lifetimes show the expected
FILL/REUSE, Attention, REUSE/RELEASE ordering, unchanged ownership/generation and
activation sequence, and skipped activation quantization on the second
projection. Across the suite there are24 projection commands and64 native
Attention command attempts. No wait-for-reservation cycle occurs.

Projection outputs are bit-identical to the baseline before and after
Attention. Attention passes every output's original tolerance and repeats
bit-identically. Its reported ordinary/native digests also match, but digest
equality alone is not used as proof of bitwise identity against the baseline.
FCSR is1 for the Q8_0 capture and3 for Q4_0; both match their baseline. VCSR is3
in all six graphs, as required by the production quantizer contract above.
Inputs and packed weights remain unchanged.

Independent replay in `...ggml-interleave-audit-20261024-01` additionally checks
every command's graph epoch/context ID and separately emitted quantization
records. There are exactly8 real quantizations and4 skips; saved quantized
activation storage is1,168 bytes across the suite. This is a software preparation
count, not a measured DDR traffic reduction. Three additional mutation tests
reject wrong epochs, context IDs, activation links and missing/extra
quantizations. The original worker result remains unchanged.
