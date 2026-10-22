# Original Unboxed Prefix265: Independent Review Preparation

Status: **WAITING_FOR_TESLA_READY_SEAL; ORIGINAL_STATIC_SCOPE_ONLY**.
No producer output has been read. No DUT/Host/reference/compiler/build, live query or producer/production edit. This note is not reference acceptance, a current RTL bug finding or launch permission.

## Authentic Original Scope

Read `next_original_candidate02.md`, actual original C/assembly/fixtures/manifest/Linux ELF and selected raw archived board report. Fresh hashes match the selection note:

| Artifact | SHA256 |
| --- | --- |
| Selection note | df426d3a8471292681fb6cee2420f82cf9cfefd444ee2a3eb00e9b451194f428 |
| Original `fp_compare_oracle.c` | 03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad |
| Linux parent ELF `rvv_fp_compare_unboxed_unmasked_e16_mf4` | 404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152 |
| Original manifest | 13a460255abd3e2349c8a6108c3ed5f2a9174dc30648d347d7e7fb3900c0a489 |
| Parent assembly | 33abaa5c662a3780ac82ea631fec6909a035ccbb6b9d656896ce0cb356808bbe |
| Archived fixtures | 5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1 |
| Archived operations header | cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64 |
| Board report | 78feb29c49c69ee6d4e6dd7803a3bccf8d8c88566b10cbbfd639f630c1cda3e1 |

Original paths are recorded in the selection note. Actual manifest member has the same ELF SHA; historical timeout metadata is300s, not a new VCS budget. Board report independently confirms first DETAIL at op4/seed0/VL15/mode0/sticky0, expected_flags0/actual16/errors1, and failed/exit1; final parent17920 calls/errors832. No claim of832 distinct bugs.

Actual original ELF disassembly independently confirms capacity at0x10538 (e16/mf4, encoding00e2f557), op0..3 routines17 instructions each, op4 routine19. Target op4 PC0x10668/opcode62805c57, with `lhu t2,0(a1)` at0x10658 and **`fmv.d.x ft0,t2`/f2038053 at0x1065c**. Immediate vstart read0x1066c and flags read0x10670, packed return, caller fflags restore and original vsm.v must remain intact.

Natural prefix: seed0 only; op0..3 each56 calls, op4 first41, **265 calls with264 predecessors**. Original order is seed/op/length/mode/sticky/trial; nonrestart trial0 only. Capacity16 at VLEN1024/mf4; lengths0/1/2/3/8/15/16. Do not remove unmasked-mode repetitions or sticky histories, filter predecessors, reset between calls or add warmups. Original fixture rotations are deterministic, not RNG.

Expected complete scope: **4240 original result-bit checks,530 guard values,265 flags and265 returned-vstart checks**; **4587 helper retirements** =4*56*17 +41*19, plus capacity. op5..9 may remain in the ELF but must not execute. All128 mask bytes, a/b16 elements and output130 bytes are initialized each call. Only two output mask bytes contain the16 checked results; right guard is `output[3]`, not `output[129]`.

## Oracle / Scalar Discriminators

Final tuple op4/seed0/VL15/mode0/sticky0/start0: a[0..15] equals the original16 inputs, b allzero. **ft0 raw64bits=0**, intentionally not boxed half +0; canonical qNaN behavior is modeled using fixture column14, not by changing software scalar transport. a14=7e55 is active qNaN, a15=7c55 is **tail sNaN**. Active bits0..14 must allzero, flags0/NV0, returned-vstart0. Bit0=1 would distinguish wrongly using low-half +0; correct bits with NV16 instead distinguish active-window/flags ownership leakage.

Preserve the original tail decision tree exactly:

- Active: exact fixture bit and flags accumulation (unmasked means mask contents do not filter active bits).
- `start>=VL` or prestart: exact original old bit. In particular VL0/start0 is a no-op with exact old bits, not arbitrary agnostic tail.
- Inactive body: original overlap-conditioned allowance; this chosen unmasked/v24 program has no masked inactive body, but do not rewrite the shared oracle.
- Tail: actual must belong to **{old, 1, wanted.bit}**, evaluated per bit, not a fixed byte and not universally arbitrary0/1. Final bit15 old0/wanted0 legitimately allows0 or1, so final second byte may be00 or80 while low15 result bits remainzero.
- Low32 packed status must be0; upper32 must equal original sticky OR active fixture flags. Immediate CSR values and restored caller flags must be evidenced, not merely final text PASS.

## Review After Seal

Wait for Tesla's exact READY path/SHA and frozen input/evidence inventory. Then inspect only that sealed generation: authentic source diff/runtime adaptation, full original helper bytes and relocated ELF map, actual `fmv.d.x` transport, execution profile, full generated trace/setup/results/flags/CSR/call ledger, true reference rc0/normal exit and immutable pins.

Perform **one** complete offline reconstruction of the already generated reference and compare it to stored analysis; no Spike rerun, new compilation, extra counterexample campaign or repeated full parsing. Reject first raw error or missing identity/oracle evidence. Bind a new owned `audit.json` to exact READY/ELFs/source/evidence hashes only after success; state **SOURCE_REFERENCE_ONLY_NOT_DUT**, exact265 scope, no launch authorization and no full17920/Linux/cross-process or all-RVV09 claim. Do not substitute the archived reduced single for this natural parent prefix.

Until seal, no prepared/reference acceptance or admission hash exists in this owned directory. Producer files and shared documents are not modified.
