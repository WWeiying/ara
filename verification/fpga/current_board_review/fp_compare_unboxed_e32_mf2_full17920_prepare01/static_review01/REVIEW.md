# E32/MF2 Full17920 Static Review

Decision: **STATIC_SOURCE_PLAN_NO_BLOCKER**. This permits the next source
implementation under the parent's conditional authorization, not execution or
FP32 acceptance. No generator, numerical Host, compiler, reference, DUT or raw
trace was run/read by this review. Only source/document inspection and small
input/ELF byte hash checks were performed.

## Independent Checks

- All44 INPUT_BINDINGS input hashes match. Original manifest explicitly names
  the e32/mf2 parent and ELF1bc4201a..., with UNBOXED/unmasked/DK0/restart0.
  Original C03cc5031... is present, unlike the separate boxed UNKNOWN case.
- Read original C, e32 assembly, operations and fixture literals. Original ELF
  executable-segment slices for all11 helpers match the recorded hashes:
  696 bytes, concatenation65b70e2c1ffbd45e348055099d00f1bbb4705f4e9817e0a95252bbfcf91887d2.
  This checks retained original bytes, not a rebuilt full Linux ELF identity.
- CAP16 follows VLEN1024/e32/mf2; vtype0x17 and physical group1 are correct.
  Both original uint32 banks are4096B, with only64B refreshed per call. Preserve
  the untouched4032B per bank as BSS, rather than table/scratch storage.
- Original loop order is32 seeds/10ops/7VL/4modes/2sticky/1trial=17920.
  There is no RNG or nonzero vstart here. All mask setup still executes despite
  unmasked targets. Every helper stages A/B at CAP, loads old-vd/mask, restores
  saved fflags and stores the result at CAP, including VL0 targets.
- FP32 literals must remain32-bit patterns; signed zero/subnormal/infinity/
  qNaN/sNaN are not e16 data. LWU then FMV.D.X preserves zero-extended raw32,
  including nonzero seeds. The invalid box is consumed as qNaN, not repaired.
  The source oracle's vf rhs-index14 substitution is separate from raw input.
- DK0 is16 old destination bits0x5b5b, not a typed32 sentinel. VL0 requires old;
  nonempty tail permits exactly the source set {old,1,wanted}. Must-zero/one
  masks can represent these independent bit sets without choosing one tail.
  Every wrong bit counts, vstart and flags each add one, and both guards jointly
  add one. Preserve details++ ordering, first20 diagnostics and later totals.
  Bytes4..129 must be freshly initialized but are not original result checks.
- 49 fresh stores/16 planned ROM loads per call and aligned4-byte output LWU
  are consistent with the proposed packing. Neither VL0 nor repeated constants
  authorizes fresh-store deletion. Original helper signatures/order stay intact.

## Cost And Remaining Obligations

No static-plan blocker found. Cost2941812 is an analogy from measured e16
2653044 plus286720 input LD/SD instructions and2048 additional BSS instructions;
it is NOT a compiled e32 upper. The two inherited-upper analogies2957810 and
2971630 likewise cannot prove the3M gate. Address generation, relocation, spills,
record-load hoisting and startup layout must be charged in actual linked CFG.
Four extra instructions/call already exceed the measurement-based margin.

The48 source periods/3072B and2240 records/17920B are plausible mathematical
geometry, not generated-model acceptance. Future implementation review must
check FP32 packing before shifts, aligned defined memory access, record fields,
per-call mask/A/B/output freshness and eight mode/sticky uses of each immutable
record. Numerical Host must independently invoke the original C/fixture oracle,
not use one generated model for both expected and simulated helper results.
Include malformed-box raw payloads, signed-zero/sign-extension mistakes, VL0,
tail allowed/disallowed outcomes, two bit errors, both guards, CSR and details20/21.

Committed FPR writeback can reuse the pinned M9 wire contract, not e16 runtime
evidence. Future e32 checks must derive their own linked PC, validate LWU/t2 and
FMV.D.X rd0/full64 payload, and never write that FPR result into GPRx0. Numeric
qNaN equality alone cannot establish the original raw payload was transported.

Parent's latest conditional sequence: source implementation -> independent source
review -> one generation and original-C numerical Host (each child<=120s) ->
only on numerical success, fixed-flags dual compile once each and full CFG
analysis<=600s. Preserve any failure; no blind trial. Cost>3M means HOLD.
No reference/DUT authorization follows from this review.

## Binding

| Artifact | SHA256 |
| --- | --- |
| SOURCE_PLAN.md | b45af593a2d972c030ca925360543c170510edda532cf3defbd4136312c27e98 |
| COST.md | f3caeb49172163212ee59c2eafc7304263e9352b6a6c80d75a4625ebb1874d69 |
| shape.json | 87a77abb0a3422bea11049029dabba06205fb87f8525f28cc483afdfbb5a47c0 |
| INPUT_BINDINGS.json | 1245adb28fe0c6042837573950b2c1261fb130507497932010814c4f0267bfff |

The FP16 result remains only a cost/implementation precedent. Neither this
review nor a future bare source port closes original Linux execution scope.
