# Full17920 Unboxed E16/MF4 Source Candidate

Status: **source/model prepared, independent implementation review pending**.
This is neither C Host execution nor reference/DUT/Linux acceptance. No compiler,
Spike, VCS, generic checker stream, RTL edit or live simulation query was used.
The parent authorized this source/model stage after Aquinas's earlier static
`SOURCE_CANDIDATE_NO_BLOCKER_STATIC_ONLY`; that does not pre-approve this new code.

## Review Entry

- Candidate: [source_model02/software/case.c](source_model02/software/case.c).
- Scalar implementation: [packed_core.h](source_model02/software/packed_core.h).
- Exact transformation: [source.diff](source_model02/software/source.diff).
- Generated input/oracle ROM: [generated_tables.h](source_model02/software/generated_tables.h).
- Generator and independent Python comparison: [prepare_source.py](prepare_source.py).
- Counts, short counterexamples: [model_checks.json](source_model02/model_checks.json).
- All original ordered tuples and allowed sets: [model.json](source_model02/model.json).
- [helper_identity.json](source_model02/helper_identity.json),
  [input before](source_model02/inputs_before.json),
  [input after](source_model02/inputs_after.json),
  [artifact pins](source_model02/artifact_pins.json).
- Actual process wait receipt: [MODEL_EXECUTION02.json](MODEL_EXECUTION02.json).

Aquinas received the concrete source and artifacts before any compile. They are
held unchanged for this review; a requested correction must retain these results.

## Identity and Exact Scope

Original Linux ELF and prior byte-equivalent rebuild:
`404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152`.
Original full C:
`03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad`.
The pinned prior `fp_compare_unboxed_prefix265_prepare01/software/original/`
contains the full parent, not a 265-call truncation. All four original source
files are copied unchanged under `software/original/` in the new candidate.

Full seed/op/length/mask/sticky/trial order remains
32*10*7*4*2*1 = **17920**, with no reset partitions or prefix stop.
CAP16, VLEN1024, e16/mf4/vtype14, vd24, DK0 fixed old bits `0x5b5b`.
Lengths are 0/1/2/3/8/15/16; 2560 calls have VL0. Scope is 286720 result bits,
35840 guard values, 17920 returned vstarts and 17920 flags checks.
There are 7168 vv and 10752 vf calls. Original helper instruction count is
326144 dynamically, plus the one 3-instruction capacity call.

All 185 static helper encodings were read from prior actual SoC/Spike metadata
and checked against original ELF PT_LOAD bytes (capacity sequence uniquely
present). `scenario.S` is copied unchanged, including `lhu; fmv.d.x` with no
boxing repair, all CSR save/restore and vector setup/store instructions. This is
an identity check of existing ELF bytes, NOT proof of an uncompiled new ELF.
All raw scalar inputs remain original b[0]: seeds0/16 are zero and the other30
are nonzero. Only the oracle uses rhs qNaN index14; no input is substituted.

## Implementation and Evidence

The source-derived generator independently classifies all 1536 original FP16
fixture pairs. For all 17920 calls it compares original allowed sets with the
packed masks at both possible values of every bit (573440 checks). Both minimum
and maximum legal tail selections pass the complete oracle (35840 positive
call checks). Per-bit equivalence plus additive error counting covers arbitrary
combinations, not merely one preferred tail vector.

The 11 targeted error examples cover VL0 preservation, active result, a forbidden
tail zero, each guard, both guards as ONE error, two bit errors as TWO, vstart,
missing NV, spurious VL0 NV and missing sticky. Diagnostic logic preserves
`errors!=prior && details++<20`: the first20 failing calls print, failure21 does
not, and intervening passing calls do not increment details. Thirty nonzero raw
seed records document rejection of both zero substitution and boxing correction.
These are Python source/model checks; compiled C/asm and diagnostic transport
remain future proof obligations, not claimed as tested here.

Every call executes 16 SD mask writes, 8 SD input writes (4 to each array), then
16 SD output writes plus one final SH. No same-value/cross-call reuse eliminates
stores. Arrays retain their original sizes: each input is 1024 halfwords with
the upper2016 bytes untouched after startup BSS zeroing, mask128 and output130.
Word packing changes the scalar interleaving within initialization, not the
values, helper order or cross-call history. All initialization precedes each
original helper. The new source performs no vector/FP/CSR instruction in these
scalar access routines. Actual linked lowering/no extra RVV is still untested.

One aligned LWU observes guard0, result bytes1/2 and guard3. Output4..129 remain
freshly initialized but are NOT new post-result constraints. The 16-bit zero/one
required masks permit exactly the original tail alternatives; nonempty tails
can be old/1/wanted, while VL0 requires old. Wrong result bits are counted, not
collapsed. Low32 status, high32 flags and the combined guard error remain separate.
First20 DETAIL strings/fields and final original summary are retained verbatim.
The Linux syscall/entry is replaced with the existing scalar replay runtime and
main return; capacity16 is explicitly required for this specialized source.
This does not reproduce Linux process/signal/environment behavior.

Tables contain 48 immutable 32-byte input periods (1536 bytes) and 2240 eight-byte
records (17920 bytes). Each record packs Z16/O16/baseflags8/VL8/Arow8/Brow8;
mask modes and sticky variants share immutable records but still execute every
call/fresh store. Record input unpacking is checked little-endian against every
original input value. Original fixtures remain copied for provenance; compiler
dead-data elimination/linked layout has not been assumed or measured.

## Process and Remaining Gate

`source_model01` preserves the first tool failure (actual exit1): this host's
Python lacks `int.bit_count`. Its initial pins and exact failed script remain.
`source_model02` changes the Python population count to `bin(...).count('1')`
and uses fresh outputs. Actual wait exit0; internal model duration7.874091s,
under the explicit120s model-process bound. Original inputs were hashed before
and after and remained unchanged. This was not a failed/repeated Spike run.

Next only after independent source/model review and parent authorization:
one fixed-flags dualcompile, actual helper/no-extra-RVV/scalar-store/LWU/ABI/map
checks, then complete CFG cost assessment. `compile_proposal.json` is only a
configuration proposal, not an executed command. No reference admission follows
automatically. The earlier 2,967,200 planning allocation has only32800 margin and
is NOT a compiled upper bound. Full all-correct CFG must meet the unchanged3M
gate; otherwise HOLD without reduced scope or increased limits.

## Handoff Hashes

| Artifact | SHA256 |
|---|---|
| case.c | `e975710b72861dec5adb117b353915898693fd3d716414a8f025c4d116fe03db` |
| packed_core.h | `1c9405da52af070ef6511767e04f2389618e5201f2a55cb8711bbb84907f308e` |
| generated_tables.h | `95b2a66bf573e5c14d2d387fc9bbe9bbce8d44997cc703f9cf9a2a15845ff63e` |
| model_checks.json | `531bd1f261a914a53a458d46ba01e220c1c7415e643417d9a6f45ae156581267` |
| report.json | `e36a55103750f628f5128e3727b82602e511ea3a29a132f6ac47dfa0a0701a45` |
| artifact_pins.json | `53061a91be4325db281841f51fc732955684c76b1db9274d270fb9350b6b45aa` |
