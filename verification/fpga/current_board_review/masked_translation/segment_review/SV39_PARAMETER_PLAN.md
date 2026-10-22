# Bounded Real-Sv39 Port Plan

Proposal only. No fixture edits, new binaries, compilation or simulation.
Exact source/ELF provenance and original oracle: `SELECTION.md`.
No NF7/indexed work is included.

## Parameters

Use the existing Aquinas `../sv39_extended/` startup, page tables, trap/retry
and marker infrastructure, with owner-controlled NF2 adaptation. Emit actual
segment instructions, not NF1 or scalar emulation.

| Parameter | Primary load | Companion store |
| --- | --- | --- |
| Original tuple | u0,s0,b5,m2,f1 | u0,s1,b5,m2,f1 |
| Instruction | vlseg2e16.v v24,(a0),v0.t | vsseg2e16.v v24,(a0),v0.t |
| SEW / LMUL / NF / VL | 16 / 1 / 2 / 8 | same |
| vtype / registers | 8 (tu,mu) / v24,v25 | same |
| VA mapping base | 0x40000000 | same |
| Base offset | 4074 (0xfea) | same |
| Unit segment stride | 4 bytes | same |
| Predicate | all 16 source mask bytes 0x24 | same |
| Initial vstart | 0 | 0 |
| Expected restart vstart | 5 | 5 |
| Protected page | VA+4096, page1 | same |
| Fault field / mtval | 1 / 0x40001000 | same |
| Expected page-fault mcause | 13 | 15 |

Keep NF2 only. Start with the load trial; the store is the same geometry and
independent memory oracle. Neither is claimed to fail archived hardware.
For the next discriminating negative point use the archived b3 load single:
offset=4082 (0xff2), expected restart=5, admissible fault field addresses
0x40001006/0x40001008. An early fault at inactive segment3/VA+4096 is a failure.
This is an optional third selected trial, not a request for full-loop replay.

## Required Adapter Changes For Its Owner

The current fixture config contains offset,stride,op,mask,start,cause,page,vl.
Its `start` is expected fault/restart index, not initial vstart. It currently
has no NF2 op. Preserve this distinction when adding segment selection.

1. Add real NF2 load/store dispatch and labels for precise mepc matching.
   Initialize both v24/v25 over all 64 halfwords with the original formulas;
   capture both fields and write both fields to the final output. Current
   v25 guard becomes field1 data; v23 can remain a neighbor guard.
2. Retain original mask and all-register tail checks, both output guards and
   the entire two-page memory oracle. Existing 130-halfword output storage
   can hold 128 field-major data halfwords plus guards, but its NF1 loops and
   field1 seed must be extended. Use original store field seed +29, not a
   cloned v24 pattern.
3. Make trap-address validation field-aware. The current NF1 segment-base
   expression would incorrectly expect P-2 for the b5 trial. Expected mtval
   here is P. Do not weaken general exception checks to accept any page address.
4. Check original saved prefix i<5 in both fields before page repair/poison.
   The existing NF1 rule that i>=start retains seed must NOT be imposed on
   faulting segment5: field0 may already have completed. Preserve the original
   unconstrained fault-segment snapshot and exact final oracle, rather than
   changing expected final values to observed DUT values.
5. Repair the PTE, perform the existing sfence/fence, poison only element2 in
   both fields, restore vstart5 and retry identical mepc. Do not advance PC or
   reset vstart0. The later scalar marker stays zero at the fault and becomes
   one after successful completion. Check one page fault, expected later ecall,
   and vstart0 on completion.

## Explicit Port Limitations

The Linux original uses mprotect(PROT_NONE), SIGSEGV/SEGV_ACCERR and a Linux
vector signal frame. Existing baremetal fixture protection uses an invalid
Sv39 leaf PTE, then repairs it to mapped flags0xc7, and snapshots vector state
in its M-mode handler. This preserves page-fault/restart geometry but is not
identical permission-fault or Linux signal-frame coverage. Label this difference;
do not claim the original Linux ELF runs in the baremetal fixture.

No focused ELF exists yet for b5. A future port is a selected original-source
semantic derivative; its C/S/ELF hashes must be captured after owner preparation.
The original 96-trial aggregate failure is not this bounded port's pass/fail
oracle. The proposed data formulas, exception metadata, prefix poison and final
full-memory checks are independently specified in SELECTION.md.

Read-only fixture identities at review time (SHA256):

| File under ../sv39_extended/ | SHA256 |
| --- | --- |
| fixture.c | f444737ddcb48c867e4461fb12e5184e20ade8cc90acb8ca0ddd6b1d8f55d000 |
| fixture.S | 4dab24a085758c1f227a4311e96039e13377e4e59cccb2c7a4a7587645928b16 |
| fixture.h | 06a74a5cd3a61f3c1aadd830053bc6cb57a7f971cc5ad867ac218ede25a56385 |

These identify the inspected adapter, not a newly frozen or approved build.
