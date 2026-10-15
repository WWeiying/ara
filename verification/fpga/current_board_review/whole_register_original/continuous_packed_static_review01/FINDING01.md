# Packed Reference Entry Finding

Status: HOLD_REFERENCE_PENDING_NARROW_POINTER_FIX. No reference/Host/DUT run
was performed by this reviewer. Hilbert owns the implementation and correction.

Reviewed header SHA:
e5e82b21838e17884489b5e54b9d7e66a029c2bdd51f8fd34160e0c0d1c2c375.

`packed.h` uses `packed_load(in + offset - 32)`. Additive expressions associate
left to right, so this first forms `in + offset`. In original M8 active cases,
word offsets1032,1040,1048 are possible; input has1024 bytes, so that intermediate
pointer is beyond the array's one-past bound. Subtracting32 afterward does not
make the intermediate C pointer arithmetic defined. Alignment, a valid final
load address and UBSan success do not establish absence of this C UB.

Minimal correction: `packed_load(in + (offset - 32))`. The existing nonoverlap
early return guarantees offset>=32 for all admitted geometry; the maximum
overlapping word is1048, so integer subtraction gives an input offset<=1016,
and the complete eight-byte load is inside input[1024]. Do not alter masking,
source oracle, helper code, original order or budgets to address this finding.
Retain prior Host/build evidence and bind the corrected source to its actual
compiled ELF and Host result before the one authorized reference.

Other reviewed aspects show no additional blocker so far: empty/guard early
return precedes input-pointer formation; partial-mask shifts are1..7 bytes, not
64bits; byte-array/local uint64_t transfers use builtin memcpy rather than
incompatible alias casts; expected values use current post-helper input; the
byte fallback body is the original source fragment. Actual disassembly has
128 input sd and136 output sd iterations and scalar ld checking, not a memcpy
libcall. Fresh setup/read ledgers are connected to the actual audit write/read
paths and reject an omitted entire repeated setup interval.

Read Host02 result actualwait0/7.4383425s:3706506 tests,3701376 local corruptions,
864 changed-current-input cases. Read Host main/gates actualwait0, with positive
full1134 entry and explicit UB-trap negative. These were not rerun and do not
override the source-level pointer finding. Final reference-bound sealing and
complete actual ELF pin review remain required after the narrow correction.
