# Next Authentic Failure Preparations

This preparation queue follows the current source-identity gap audits. It does
not authorize new DUT simulations, change RTL, or count prepared cases as PASS.
Existing frozen candidate04 campaigns continue unchanged.

| Preparation | Historical link | Required preservation | Owner directory |
| --- | --- | --- | --- |
| Disjoint vmacc e8/m4 | Printed completed481, VL512/start256 | Recover source or reproduce original ELF; map the counter before selecting482 calls; retain accumulator patterns, RNG, masks and CSR oracle | `arithmetic_restart_original/` new artifacts only |
| vsmul.vv e8/m4 | Printed completed776 | Prove source/binary identity and exact prefix mapping; preserve vxrm, sticky vxsat, data and predecessor calls | `fixed_restart_original/` |
| vfmerge e16/m8 ops0 | Printed completed194 | Check195-call mapping against original partition, including scalar boxing, mask, fflags and complete oracle | `fp_merge_original/` |
| Whole-register predecessor edges |59 original adjacent-call edges absent from op partitions | Derive actual call pairs and intervening source control flow; preserve original assembly/setup and1088-byte output checks | `whole_register_history_edges/` |
| Gather stalls |11 historical records separate from83 passing numerical singles | Recover exact last-call/sequence evidence and identify source-preserving bounded replay; do not invent a shared root cause | `gather_original_review/` new artifacts only |

Host/reference preparation must establish exact source identities and counts,
full oracle behavior, and realistic execution cost before launch review.
Original C recovery and binary-equivalent reconstruction are different claims.
An unrecovered source or unknown last trial stays explicitly unresolved.

The59 whole-register pairs provide bounded predecessor-effect checks, not
equivalence to the complete1134-call history. The potential18.6-hour continuous
run is an estimate, not a launch plan; measured partition costs and user budget
consideration are required before such a run.

Current floating-point comparison plan08 is already separately launched under
`ara-fp-original-restart-candidate04-02.service`, with two130-call prefixes.
Its682-call prefix remains held. See `../fp_comparison_original/PARENT_LAUNCH08.md`.
