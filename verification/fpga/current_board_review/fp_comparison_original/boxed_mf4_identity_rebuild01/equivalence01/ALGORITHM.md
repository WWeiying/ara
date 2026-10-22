# Strict Static Mapping Feasibility

Scope: the two existing ELFs only, using the previously saved disassembly.
No compilation, program execution, numerical Host test, or new disassembly.
One analyzer invocation, wall timeout 120 seconds. Preserve identity failure.

1. Verify exact ELF/disassembly hashes. Parse ELF sections and verify every
   decoded instruction byte against its ELF and contiguous coverage of .text.
2. Construct a full instruction CFG, retaining both conditional successors,
   direct call target plus continuation, return instructions, indirect calls,
   and ecall boundaries. Reject malformed targets/gaps. Export unresolved
   indirect/return/system boundaries rather than inventing edges.
3. Check the 10 pointer-table words at the exact offsets 280..352 in .rodata.
   Each must point to its actual corresponding helper. Compare every other
   .rodata byte, BSS geometry, and exact helper suffix. This is not arbitrary
   section-address normalization.
4. Starting at both ELF entries and the 10 verified helper pairs, traverse
   paired CFGs. Permit direct no-link j stutter only; retain self-loop
   divergence. Require opcode, registers and non-address immediates identical.
   Direct branch/call destinations must recursively map, not merely belong to
   the same section. Calls also require continuation mapping.
5. A differing adjacent lui/addi address materialization is admitted only if
   both actual constants select the identical offset in byte-verified rodata
   outside the pointer table. Record the exact PC/address pair. Do not infer
   arbitrary registers contain relocated addresses.
6. Inverted predicates, add-to-addi substitutions, unproven indirect targets,
   ambiguous relocation provenance and unmatched PCs are proof obligations,
   NOT automatically normalized. A frontier mismatch stops that paired path;
   continue independent queued paths only to report coverage, not to claim
   they bridge the gap. Never suppress an error/failure path.

This bounded analyzer is a feasibility checker, not a full ISA/ABI theorem
prover. A complete proof would additionally require link-address/return-stack
relations, external syscall contract and all indirect target provenance. No
SEMANTICALLY_EQUIVALENT_RECONSTRUCTION label can be emitted while any of these
or any reachable instruction/edge remains unresolved. Existing known add/addi
and branch-opcode differences are expected to make this strict proof UNKNOWN.
