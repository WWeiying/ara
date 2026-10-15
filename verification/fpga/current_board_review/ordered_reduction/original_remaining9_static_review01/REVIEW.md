# Remaining Nine: Pre-Implementation Static Contract

Status: **source-derived recommendations, not generic-helper approval**.
Tesla confirmed `original_remaining9_prepare01` is still at source-reading
stage; no new prep/spec/check or compiled case evidence exists for review yet.
This review reads original sources, existing inventory and sealed e16/mf4
evidence only. No reference/Host/DUT execution, compilation or live query.

## Membership And Geometry

Exactly these nine original reduced records, not nine new roots. Canonical root:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verified_handoff03/rvv_small_redspecial02`.
Do not repeat accepted e32/m1 or the separately prepared e16/mf4 reference.

| Shape | cap | VL | Fullcap input bytes | Actual mask-load bytes | Requested vtype |
| --- | ---: | ---: | ---: | ---: | ---: |
| e16/mf2 | 32 | 16 | 64 | 4 | 15 |
| e16/m1 | 64 | 32 | 128 | 8 | 8 |
| e16/m2 | 128 | 64 | 256 | 16 | 9 |
| e16/m4 | 256 | 128 | 512 | 32 | 10 |
| e16/m8 | 512 | 256 | 1024 | 64 | 11 |
| e32/mf2 | 16 | 8 | 64 | 2 | 23 |
| e32/m2 | 64 | 32 | 256 | 8 | 17 |
| e32/m4 | 128 | 64 | 512 | 16 | 18 |
| e32/m8 | 256 | 128 | 1024 | 32 | 19 |

All use VLEN1024, scenario3/l4/mode3/rm0/op0/sticky0, bank1 row1545,
flattened row4905. Within-scenario cursor is285, not1545. Full fixture table is
2*3360 pairs and must match each shape's own archived JSON/header. Expected
bank1 result is e16 `0x7e00` or e32 `0x7fc00000`, flags exactly16.
Do NOT generalize the old smallest-case assertion that bank0 expects Inf/0:
for these nine that distinction applies to e32/mf2, while larger bank0 shapes
already include selected index5 and can have the same NaN/NV as bank1. Therefore
bank identity must be checked by actual fixture load addresses and capacity,
not only by the numerical result or a universally assumed wrong-bank mutation.

## Required Generic Checks

1. Bind per-case metadata, source headers, original/scenario ELF, compiler,
   adapted sources, both compiled ELFs, symbols/disassembly and actual command.
   Recover all21 op_0 encodings from that case's archived ELF and match both
   new ELFs; SEW changes load/store/vset encodings although vfredosum's encoding
   itself remains `0c881c57`. No fixed e16/mf4 PC constants in generic extraction.
2. Preserve scenario8*length7*mask4*rm5*op3*sticky2 traversal and original inner
   selector. There is one helper, but3360 mask fills and6720 fixture-field loads,
   8*cap input-word writes,512 seed-word writes,215040 mask-byte writes,144 old
   output-byte writes. Verify code equivalence and the actual ordered fixture
   traversal, not just these aggregate counts. Do not shorten skipped loops.
3. Capture selected setup at helper entry. All scenarios after the selected
   call still reinitialize input/seed/mask. Final memory is not selected setup.
   Walk the complete compiler CFG: a scalar loop/backedge found first in address
   order does not delimit all scenario initialization. Switch cases and memcpy
   blocks can be placed after other loops or reached via backward jumps.
4. With B=SEW/8, input object is512*B bytes. Validate all cap input words and
   all64 seed words (128 bytes e16,256 bytes e32), plus all64 initialized mask
   bytes. e16/m8 exactly fills its1024-byte input object and64-byte mask; e32/m8
   uses1024 bytes of a2048-byte input object. No size assumption inherited from
   e16/mf4 may silently truncate either.
5. The seed and old-vd vector loads remain m1 and128 bytes regardless of data
   LMUL. e32 initializes64 seed words but loads32; e16 loads all64. Source v8
   fullcap loads must concatenate every written register v8..v15 as applicable,
   with exact element addresses/width and only the defined fractional prefix
   required for fractional LMUL. For m8 the entire1024-byte group is required.
   The original source group v8..v15 does not overlap seed v16 or destination v24.
6. Verify fullcap vset/load/mask before requested VL=cap/2. Mask load uses
   ceil(cap/8), NOT ceil(requestedVL/8), because the original helper loads it
   before lowering VL. Then bind frm/fflags save, requested zero/zero, reduction,
   vstart0 and exact returned NV16, save/restore CSR values, and final m1 vset.
   m1 vtype is8/16 and m1 VL is64/32 for e16/e32 respectively, always tu/mu.
7. Exactly144 output bytes: eight left guard,128 destination, eight right guard.
   e16 result bytes `00 7e`,126 unchanged destination-tail bytes; e32 result
   bytes `00 00 c0 7f`,124 unchanged destination-tail bytes. All unchanged bytes
   are0x5b. Full destination store emits64 halfwords or32 words, not cap stores.
   Require all144 original LBU oracle reads, full vector payload and exact store
   footprint; do not mistake the e32 result's zero low half for a missing write.
8. Normal HTIF1 must follow complete exact original and board success markers,
   restored CSR and return. Reject any trap, extra helper, skipped oracle,
   firsterror, abnormal exit, bound hit or partial log. Post-exit park is not
   firmware work. Shape-specific symbol/PC maps must be pinned before reference.

## Cost Admission

The accepted e16/mf4 binary measured1,858,335 firmware instructions; its mask
body alone is1,612,800, and seed initialization is122,368 (512 calls to32-byte
memcpy plus surrounding code). These are facts about that binary, not constants
that can automatically be imposed on all newly compiled shapes.

The source always has3360*64 mask-byte iterations. Derive actual per-mode loop
cost from every compiled ELF before admitting reference. Account separately for:

- Eight scenarios' input initialization:8*cap iterations; scenario4/5 each
  declares a six-unsigned indices array. It may lower to a24-byte memcpy per
  element, direct stack stores, or another bounded sequence. The seed's
  eight-unsigned local array is32 bytes, independent of SEW. Do not confuse
  those copies with the2/4-byte final input/seed stores.
- Entire fixture/mask/sticky/outer-loop control, including after the target;
  all callsites and bodies of memcpy/reduction_input/reduction_seed if not
  inlined; changed32-bit code generation and BSS size; complete oracle and exit.
- All144 output checks and single fullm1 store remain constant-size in bytes;
  vector element count does not equal Spike retired instruction count.

A useful **provisional allocation, not a certified bound**, is2.1M for unchanged
mask/control/seed/startup/oracle/exit plus64 instructions per input iteration,
plus180 per possible24-byte copy in scenarios4/5:
`2,100,000 + (8*64 + 2*180)*cap = 2,100,000 + 872*cap`.
It ranges2,113,952 (cap16) to2,546,464 (cap512), so3M is plausible with slack.
Each assumption must be discharged against the new ELF: more expensive mask
code, duplicated copies or loop overhead invalidates this allocation. No
per-shape3M admission is issued by this report before those disassemblies exist.

Keep exactly one reference per ELF, actual ISA
`rv64gcv_zfh_zvfh_zvl1024b`,3M steps/256MiB/120s, at most2 concurrent. Record
that full ISA string in spec, command and approval, avoiding the previous
minimum-versus-actual mismatch. Bytes/time are separate hard bounds, not
guaranteed by instruction cost. A failure or bound hit preserves evidence and
stops the batch; no automatic additional allowance or source shortening.

## Static Host-Negative Review Checklist

Review forthcoming tests for wrong-SEW NaN/store size; e32 first/last result byte;
first/last tail and both guards; missing middle m8 source register; truncated
fullcap input or mask; last e32 seed-initialization word even though unconsumed;
wrong bank/address even when both banks' results coincide; missing post-target
initialization/traversal; missing/extra flags; vstart; restore failure; duplicate
helper; truncated raw and missing HTIF. This is a proposed review checklist,
not a request to rerun tests or expand architectural stimulus.

## Source Identity Checked Now

Fresh hashes of all nine scenario.c files are identical:
`fd6870fa4eed43bd660136c9d90577f5cfbe99d7ba834a14fedad96237cd251a`.
The per-shape assembly and fixture hashes below were freshly read, not inferred
from that common C. Full metadata/ELF pins remain in `original11_inventory01`.

| Shape | operations.S SHA256 | fixtures.h SHA256 |
| --- | --- | --- |
| e16_mf2 | 468713e2051d76602d28b5a66ad5793535c965d536d8e0541a9f1087af25ad96 | 68a394a73fdfb4264fb8aa998766b47c003f49da21b06d2b32318fe964424fb4 |
| e16_m1 | 6a5ad396eb3f7e89cf84dadfc63243100d99bae0ba2dbb9450a52a11f8cdfac3 | 88bbb3d5a1c7336d2699b1aa1097dfb1bbe8a1c738adfb5a5d82cfb2ea01cc1d |
| e16_m2 | a4518c32429fc8cf73d71fda5b7f361e6b1c9ccfeb9c0e3a420ec42b62621de5 | f2b54398292a10db0803e5be232041a1a46cc344cb852d9680767651845c1b37 |
| e16_m4 | b141a10141ec73f91c2f3529fc3771757f33d9d5722da9aa9c129baf3066b0d8 | 038cf9a44ddceb4abf038b33b21bbf80e7b354368a7f1cd29a1d69babcf62b58 |
| e16_m8 | 9336ee28a5dab2838ee5db6841356818e6161ec210311f561c82adaeb2072662 | b600d00df412bace58ac123c3f11c5a01313809fbecabda6c66074a70e99b3af |
| e32_mf2 | b8b92cb61055eeed5d7c7f6081592a4d7c76e88698554ce75c7fe4aafcdd97c8 | 88116a3574deaea00131682ec91d5d3c4c5eff178f6a0080d7071cf65db932c4 |
| e32_m2 | e0cd550e3bda450843973dcfcf60bccf73ab1132dee4722dcacb8e078c79b300 | 02ce6d8aa50c817f649043af7992ee1102e48f740631ce0737ac1275639dcca0 |
| e32_m4 | 8dcc1d0ecc1adcd089f94292962761ed205ff34cc0b6f0dc9632e21367865875 | 4d080cb0cd37371af0a86c480f0b7e2403ee87eadc5af64debd435aff4a3dd71 |
| e32_m8 | 0384a741a0df1f4252d40e769dd2e8ddc73675f117f817c4e25aa12dbec02503 | 2a867afaec04564a541530d8ca8b10bc8e99a16a6060a00cb35d5d520597004c |

Formal generic-code and per-case cost review remains pending Tesla's frozen
prep/spec/check/disassembly paths. Nothing here marks unseen code or references PASS.
