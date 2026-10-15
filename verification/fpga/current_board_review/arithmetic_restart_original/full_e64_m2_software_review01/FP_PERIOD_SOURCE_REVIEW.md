# FP Period Proposal Static Review

Verdict: SOURCE_NO_BLOCKER. This accepts only the exact source proposal below for the parent's next-stage decision. No Host, compilation, reference or DUT was executed or authorized by this review. Existing software01 budget HOLD remains.

## Source Findings

Actual diff contains only the fp_period.h include and replacement of the original op>=25 input refresh loop by refresh_fp_period(a,b,fp_inputs,seed). The call remains inside every trial, after start selection and before output initialization. It is not conditional on VL, vstart or whether previous input contents match. The outer three-seed loop and next-seed RNG, mask, fallback, helper calls, expected table and CSR behavior are unchanged.

Independently inspected the actual header and enumerated its literal store declarations using a readonly source parser (not Host execution): each seed 0/1/2 has exactly 64 calls, ordered a[0],b[0],...,a[31],b[31]. Each a value uses (i+seed)%8 and each b value uses (3*i+seed)%8. The identity for i=8q+j justifies the repeated eight-element period. All 1,890 original FP calls therefore retain the intended 120,960 destination writes; no trial or equal-value store is intentionally removed.

Eight uint64 volatile-qualified reads occur inside each refresh call from the existing aligned uint64 immutable input table. This is not cross-call caching and does not use floating arithmetic or change bit patterns. Reducing repeated immutable table reads is a scalar implementation change, not original instruction identity. Destination/source objects are distinct. memcpy copies one valid uint64 object at a time into existing array elements, with an empty memory-clobber asm after each copy. No alias-punning cast, out-of-object pointer, shift or arithmetic UB was found. Invalid seeds trap, while the retained caller generates only 0..2.

Memory barriers express compiler ordering; the future actual ELF must still prove all 64 ordered eight-byte destination stores on every FP path, no extra RVV/fence and unchanged helper bytes. Source declarations alone do not prove GCC lowering. No original fflags oracle is introduced.

## Cost Qualification

The old linked FP region costs 11 setup/return plus 32*15 loop instructions =491 per FP call. The unassembled witness can load eight values into caller-saved registers, use at most five selection instructions, perform 64 SDs in order and return: 78 leaf instructions. Offsets 0..248 fit SD immediates and the branch spans are small. Adding a proposed 50-instruction caller allowance gives 128; (491-128)*1890=686070.

That 50 is a constructive caller allowance, not a proven bound on GCC register allocation, spills, frame changes or changed main CFG. Neither 128 nor the resulting 2388132 whole-cost projection is an actual compiler result. The projection assumes all other costs unchanged. No budget admission follows from it.

Future admission must account for the complete actual compiled successful-path CFG, including caller/setup/spills and any changes outside this function: net saving >=75000 against the existing 3074202 upper, and final upper <=3000000. If all other costs are unchanged, 451 per FP call would save 75600 and yield 2998602; this is only an illustrative sufficient condition. Neither the gate nor timeout is raised. Firmware retired cost remains unknown.

Future authorized Host should retain prior negatives and additionally observe the exact 64-store sequence, rejecting missing equal-value writes, reordering/duplication, stale seed values and omitted VL0 refresh. These are future checks, not evidence claimed here.

## Exact Reviewed Identities

Root: ../full_e64_m2_fp_period_source_proposal01/

- PLAN.md: f8aebf6fa2381f420521fe4f679a592165c79a54db0e7f0af7131c4345ce715d
- STATIC_PROOF.json: dc33807b0849bc4689b71cc841a71e15e552557dc9ebd7565f7aea05ae42259d
- fp_period.h: fb1386ff59ccd08e8f7803bdd1a12e9a3446459b9f9ea75e9a738da6d8d9de4c
- case_proposal.c: 8201fec405038b5a399acf130da91e3a580495be856bc43c949a902ce9e057f5
- lowering_witness.S: d66c5cc1db0a4a2125499ff41ff969947c5ca687ae08d0ead6c279e00337bcc9
- Baseline software01/case.c: 14814418f676a643d24a9762e464e10c4986dfdef5d7f044eb425aeddc39ef23

This review does not change the sealed proposal, software01, RTL, or any running task.
