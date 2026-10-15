# Pre-Execution Reference Cost Review

Full contiguous programs: cap16, 4095/5985 calls, 65520/95760 results and
8190/11970 guards. Source loops, three seeds, predicate and restart ordering
are unchanged. FP data replacement occurs inside the original every-call
FP loop, not a separate/reset phase. All25/35 helpers have13 original
instructions; capacity has3. Host full-source positive2/negative17 pass.

The initial stripped-symbol provenance preflight is retained separately.
All helper windows now match the original ELF instruction stream uniquely.
No original Linux ELF rebuild or new golden has occurred at this review point.

Conservative successful-path charge (instruction counts, not cycle estimates):

- Per `(seed,op,VL,mode)` group: mask clear128*4 (e32 PCs80000386..390),
  predicate construction16*32 including `selected`, and80 control/setup.
- Per call: result/oracle paths16*160 including jump-table dispatch, signed
  division, selection and counters; extra16*50 for reduction/packing;
  FP setup16*32 (e32 PCs80000402..42c); output initialization18*8
  (actual four-instruction loop80000444..44a);160 call/loop/guard overhead;
  13 original helper instructions.
- 500000 extra for boot/BSS, all three RNG initializations, text/decimal
  completion and exit. Successful calls do not enter failure-print paths.
- This deliberately charges both reduction and packing and FP setup on every
  call, including integer-only e8. The largest original nested variable loops
  are bounded by cap16; no recursive path exists. Division is a native scalar
  ISA instruction, not an unbounded software loop.

Totals generated in `bound.json`: e8 below24M, e32 below32M steps. The exact
compiled disassemblies are retained. These are conservative manually reviewed
path charges, not a formal WCET proof or predicted actual instruction count.
Unexpected behavior still terminates at the enforced ceilings.

One reference attempt per final ELF: 120 seconds,24M/32M debug steps,
6GiB/8GiB RLIMIT_FSIZE (each raw/stdout file), VLEN1024 `rv64gcv_zvl1024b`,
existing restart-capable non-ZCC Spike. Full commit raw is retained. Scalar
records are short; vector records occur only in the bounded original windows.
Even256 bytes per scalar step plus4096 per10 vector-related records per call
fits these hard file ceilings. Current filesystem had10TiB free at preparation.
The file/step/time ceilings are fixed before either run; no limit extension,
retry or oracle reduction is permitted. Failure or truncation is NOT_ACCEPTED.

Reference runtime is host execution, not a DUT budget. Existing original
prefix5 actual VCS rates span roughly619..687 firmware instructions/second;
those runs are candidate04 large shapes/op0 only, not a promise for full small
integer+FP programs. Final cost estimates will use actual new reference
firmware counts and retain this hardware/path/version limitation.
