# Remaining14 Source/Checker Short Review

**NO_BLOCKER** for the sealed source/reference and parameterized checker.
Structured binding: `result.json`, SHA256
`02dbc5d2b303d43ee190ae149a560c6b12cd15aab4363f4c359ab4d27aa10e53`.
READY SHA256:
`3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a`.
This does not count any reference as DUT acceptance or review a future worker.

## Scope And Source

Exact14: e8/sc1,2,3,5; e16/sc0,1,2,3,5; e32/sc0,1,2,3,5. No e8/sc0,
e64 repeats, scenario4, new predecessor, or full Linux parent is included.
All original singles have manifest-bound C/assembly/ELF and confirmed board
cause13 failures. Independently compared both11-instruction helpers and
capacity3 from actual original ELF against SoC and Spike ELF bytes for every
member: 700 comparisons. The SoC ABI profiles also validated against actual
ELF bytes without feeding any trace rows.

Width geometry is P-4/P-8/P-16 for sc0/1/2, P for sc3/5; vtype0/8/16 and
capacity128/64/32. Original source values11,48,85,122 are typed words.
The C pagegold64 packing and Python byte model agree with the independently
calculated last physical page words; existing Host output tables match the
typed130-element initialization/results and16-byte mask for all14.
This was a read-only table check, not repeated Host execution.

Only e16/sc0 and e32/sc0 final out[5..8] are undefined. Every initial output,
original guards0/9 and the remaining final allocation elements stay strict.
sc1/2 require four data elements followed by four typed0x5b elements;
sc3/5 require all eight typed0x5b elements. sc0 returns VL4/start0 before
helper restores VL8 for output; all other members return VL8/start0.
Full8KiB data,12KiB page tables, mask16 and CSR save/restore remain checked.

## Checker And Exit

The required DUT entry is **abi_check.analyze**, not bare source_owners.analyze.
It chains exact-ELF ABI validation, source memory ownership and full scalar
RVFI data/CSR checks. Unknown register capture remains limited to actual
first caller spills; known/business stores remain strict. Handler entry
requires the real completion ecall and exact frame; all16 restored registers
are compared against their saved values before MRET. No unknown=0 default.

Every helper has four mandatory nonempty completed memory owners, including
the alloff sc3/sc5 target. Sequence/VID/opcode/transaction checks supplement
the future generic validator; aggregate alloc/done balance alone is not an
acceptable replacement. Memory-owner VL8 is preinstruction context, with
FOF's later actual CSR read separately checked. No permitted target exception
was introduced. SoC completion is exact CTRL raw0 after full checks/restore,
not reference HTIF1. The worker must also enforce raw failure veto, actual
persisted child/monitor0, full trace extent and no-abort/first-failure behavior.

## Evidence Limits

Read Host17 actual wait0/log and its relevant wrong-ELF/profile, ABI, owner,
typed data/guard, unknown-store and CTRL negatives; did not rerun them.
All14 stored Spike/parser/preparation child receipts are actual0; reference
statuses are REFERENCE_CHECKER_PASS_NOT_DUT with HTIF1 and only the completion
S-ecall. Recorded total76726 checks and2346265 firmware instructions through
HTIF. Reference pre/post pin maps agree. No raw reference or CSV was parsed.

READY binds1253 inputs. This short audit independently hashed230 scoped
source/ELF/checker/metadata files and checked their manifest entries where
present; it does not claim a new full1253-file scan. Source/ELF/record checks
exited0 in0.746262807s (tool chunk e6f2a5). No RTL change, build, simulation,
live-query, reference rerun or worker launch. Eight-way worker execution
remains Averroes' ownership; this review introduces no further source gate.
