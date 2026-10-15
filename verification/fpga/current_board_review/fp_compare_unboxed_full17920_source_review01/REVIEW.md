# Full17920 Unboxed Source Candidate Review

Decision: **SOURCE_CANDIDATE_NO_BLOCKER_STATIC_ONLY**. No blocking source/oracle
discrepancy found in Tesla's static proposal, SHA
`4de4b7b69f4d2f8c4e3241ed9df160a5c2bb1df77bc7d3bd0a83749d28169a76`.
This is not an implemented harness, cost admission, reference PASS or DUT approval.
Only small source/metadata files and identity hashes were read. No model execution,
Host/build/reference/DUT/raw read or live query; the e32 terminal observer was untouched.

## Identity and Geometry

Fresh hashes of archived Linux ELF and existing original_rebuilt.elf both equal
`404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152`.
The saved rebuild command binds SEW16, UNMASKED1, UNBOXED1, RESTART0, DK0 to
the full parent.c/scenario.S, not prefix.c. Existing independent audit verified
all original helper bytes; this review does not rebuild or repeat disassembly.
`source_elf_proof.json` execution scope remains prefix265, not full17920.

The actual capacity helper selects e16/mf4/tu/mu: vtype14 and CAP16 at VLEN1024.
Each source occupies32B within one128B physical register; vd24 does not alias
v8/v16. Parent lines44-48 preserve seed/op/length/mode/sticky/trial order:
32*10*7*4*2*1=17920, lengths0/1/2/3/8/15/16, including2560 VL0 calls.
There are7168 vv and10752 vf calls. Static helpers=3+4*17+6*19=185 instructions;
dynamic op helpers=7168*17+10752*19=326144, plus the one capacity3 window.
The old265 reference/DUT evidence cannot replace this complete history.

## Scalar and Oracle Semantics

Parent lines37-39,54-56 and scenario op4..9 bind raw scalar to original b[0]:
LHU then FMV.D.X, without boxing OR. Seeds0/16 are zero, NOT all seeds nonzero;
the other30 use nonzero fixture bits (seed1/17 gives0x8000,14/30 gives0x7e55,
15/31 gives0x7c55). Upper48 bits remain zero for every vf call. All32 seed paths
must be checked; the prefix265 all-zero ft0 observation is not a full-scope rule.

Parent lines68-70 substitute fixture rhs14 only in the oracle, never in input
b. DK0 old bits are fixed0x5b5b, not post-helper a[]/b[] or an alias golden.
Fixture EQ/NE qNaN comparisons add NV only for an active sNaN lhs; ordered
LT/LE/GT/GE-vf adds NV for every nonempty active range. VL0 adds no new flags;
sticky0/1 is ORed with the union over active fixture flags. Tail sNaN contributes
no flags. Full fixture bits/flags, not host floating arithmetic, remain authoritative.

For VL0 every bit must equal old. For nonzero VL, active bits equal wanted and
each tail independently permits {old,1,wanted}. Therefore Z=bits permitting only0,
O=bits permitting only1, and neither mask marks unconstrained bits; Z&O=0.
`popcount16((actual&Z)|(~actual&O))` exactly counts original per-bit errors.
This does not select one Spike tail outcome or import masked-inactive semantics.

Parent lines64,90-98 add separately low32(status)!=0, high32(status)!=flags,
and ONE combined guard error even if both guards fail. Maximum19 errors/call,
340480 total. Preserve prior/errors/cases, details++ short-circuit and the first20
DETAIL records with all original fields; do not collapse two wrong bits to one.

## Packing and Remaining Proof Obligations

Source lines24-25,52-58 require fresh a32B+b32B, mask128B, output130B each call.
The proposal's8 input SD +16 mask SD +16 output SD +SH is41 stores/call
(734720 total). It changes scalar lowering, not original helper instruction identity.
Upper1008 halfwords of each original1024-halfword backing array stay untouched.
Use defined memcpy/scalar accesses and verified alignment, not uint64 pointer punning.
No cross-call input reuse, missing same-value write, or VL0 setup elision is allowed.

One aligned unsigned4B output load covers guard0, result bytes1/2, guard3 exactly;
post-oracle checks are286720 bits,35840 guard values,17920 flags and17920 vstarts.
Bytes4..129 are initialized but NOT additional original post-result constraints.
Do not widen the last SH to overwrite outside130B or load from misaligned output+1.
At most48 immutable32B input periods and2240 eight-byte oracle entries are
mathematically sufficient; this is not a generated table or linked footprint proof.

## Cost and Next Stage

The incomplete floor is17920*51+326144+3=1240067 instructions, not total cost.
The160/call allocation plus100000 fixed is2967200 with32800 margin: planning
only, NOT an upper bound. ABI spills/reloads, loop/address work and failure
popcount/DETAIL paths are unresolved. No <=3h walltime guarantee follows.

Next stage, subject to parent authorization: implement this one source candidate
and independently prove all17920 tuples against the original fixture/oracle,
including all32 raw scalar inputs, VL0/tail alternatives, sticky/NV, exact multi-bit
and combined-guard error counts, diagnostics and full fresh byte coverage. Then
review actual compiled helper bytes/no extra RVV, scalar41 stores/LWU, ABI/stack/map
and complete all-correct CFG cost before any bounded reference admission. A failing
run must retain failure/partial status, never turn step truncation into full PASS.
If actual cost fails the unchanged gate, HOLD; no shrink, timeout increase or DUT
launch is authorized by this review. Full17920 and original Linux closure remain open.

Evidence paths/hashes and derived counts are recorded in REVIEW.json. Source line
references above refer to `fp_compare_unboxed_prefix265_prepare01/software/original/parent.c`.
