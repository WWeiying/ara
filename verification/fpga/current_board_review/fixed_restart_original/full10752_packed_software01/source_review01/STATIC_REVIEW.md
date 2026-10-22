# Full10752 Source And Generator Review

Decision: **SOURCE_GENERATOR_NO_BLOCKER_PENDING_PARENT_EXECUTION_AUTHORIZATION**.

This is a read-only source review, not generated-model, Host, compiled-lowering, reference or DUT acceptance. Nothing was imported or executed from generate.py; no table was generated. The prior static geometry review is reused rather than recomputed. The parent must separately authorize generation, short independent numerical tests and one fixed-flags compile/cost stage.

## Reviewed Identity

The supplied SOURCE_STATUS.json hashes match all four actual files. Bindings are in STATIC_REVIEW.json. Original C, helper/header and byte-equivalent ELF identities remain the PINNED constants in generate.py:16-22. Missing historical C text is not misrepresented as recovered text. No old plan/source/accepted asset was modified.

No blocking source defect was found in the current candidate. One documentation note: README source mapping row numbers drift after the initialization section. In the pinned original C, output initialization is 317-319, call/vstart is 336-337, the fallback is 338-392, checks is393 and summary398-402. The generator uses the correct exact text anchors; the README line-number mismatch does not alter generated semantics.

## Generator Algorithm

- `seed_inputs` (52-77) retains all three unsigned64 xorshift operations per element. Masking each left shift before XOR keeps state within64 bits. Both random assignments precede every original override, including b-only SEW=8 at i%8==3. It records all1472 source byte assignments per seed; this is not a claim about old GCC-retired SB counts. There is no scalar-suite b[0] override and no reseeding within a seed's calls.
- `value` (80-96) matches the original specialized integer oracle on inspection. Floor quotient and nonnegative residue modulo128 implement the original arithmetic right shift and low-bit tests for negative products. RNU/RNE/RDN/ROD use the correct half/parity/residue conditions; vsmul has the original upper saturation test. op1/2/3 preserve signed add, unsigned add and signed subtract clipping. This is an algorithm argument, not an executed numerical equivalence result.
- `mask_sequence` and `mask_header` (99-106,226-237) emit all16 clear stores and the original cumulative selected-byte updates in ascending selected-i order. Mode3 still clears all128 bytes. No final-mask-only substitution or removal of a repeated same-value epoch is present.
- `make_model` (109-205) retains seed/op/VL/mode/start/control loop nesting and all10752 entries, including duplicate starts and sticky variants. Saturation is initialized from control>>2, ORs active saturation, and remains indexed per call independently of row interning. `target_required=start<vl` does not use predicate activity as an ownership waiver.
- Row keys include seed/op/effective rounding/active indices; block keys additionally include block position. Empty regions use distinct full/tail sentinel keys. Exact byte-value interning is followed by complete514-byte reconstruction equality. Row0 is qualified iff the full raw output equals sentinel. No call or helper is deduplicated. The original442/716 symbolic bounds are asserted, not asserted to be actual generated uniqueness before execution.
- `expected_header` (208-223) emits little-endian uint64 blocks, uint16 row/index IDs and a separate uint8 saturation stream. The ninth descriptor has only two output bytes; its other62 bytes are immutable ROM padding. `model.json` retains full expected bytes and input/mask assignment records for later independent comparison.

## Transformation And Packed Code

`port_source` preserves the original body while replacing Linux syscall/entry/exit plumbing, qualifying capacity512/vlenb128, and supplying an explicit Host vlenb callback. The retained original assembly/header are copied as bytes and hash-checked. `port.h` explicitly substitutes the unavailable tty drain with success; this is a bare source-port boundary, not evidence that Linux TCSBRK or scheduler/CSR-wait behavior was exercised.

`packed_source` changes array alignment, wraps every source input assignment, replaces the mask construction, merges the two identical output-initialization loops, and wraps only the original data/saturation/guard oracle block. The seed RNG statements, tuple loops, function-pointer helper call, boundary diagnostics and preceding vstart check remain. No new vector/CSR instruction is present in packed.h; the new inline assembly is scalar comparison plus compiler barriers. Linked instruction identity and no-extra-RVV still require the later compiler gate.

The packed helper initializes64 words plus a two-byte tail, then always reads64 words plus the same tail. Every full-block path performs all eight actual reads. `bad` is sticky and does not control subsequent actual reads. The actual memory accessors use fixed-size memcpy rather than uint64 pointer casts into byte arrays; expected storage is a genuinely typed uint64 array. Alignment is explicit. The tail actual access is two bytes, not an eight-byte overread. Empty volatile assembly with value input/output and memory clobber preserves the intended load/store dependencies; exact linked widths and all-path accesses remain unmeasured.

The RV64 compare first reads both inputs in BEQ and only then writes the +r bad operand with LI1 on mismatch. There are no later input reads in that asm, so early-clobber is not required. Equal input preserves bad, unequal input sets it, and later equal words cannot clear it. Host C inequality is not proof of this linked RV64 implementation; later instruction/lowering review is still needed.

## Original Failure Contract

`generate.py:284-296` copies the complete original substring beginning with `unsigned packed=0` and ending before `++checks` into the mismatch branch. Thus the original rounding/saturation calculations, per-byte failure loop, element increments, saturation failure and combined guard diagnostic remain byte-identical in that branch. It neither reruns a helper nor reinitializes output. The vstart check remains before the branch, and checks increments once outside it.

For packed equality, all data and guards match the immutable source-derived oracle: elements increases by512 and the complete high32 status is compared with the per-call saturation byte. This equivalence assumes the proven input/history contract: a/b hold their original per-seed values and helpers do not write them. A future strict observer must not permit unexplained input mutation or table drift just because the packed result matches. The low32 vstart check is not skipped on the fast path.

The original global error count, first20 diagnostic suppression, data ordering, and single combined guard diagnostic are preserved. A wrong front guard still reports the original rear-guard actual field. A mismatch in immutable expected ROM may enter fallback and find no source error; that is not a numerical failure-count bug. ROM integrity must have a separate identity/equivalence gate instead of inventing an extra original-source error.

## Required Next Numerical Gate

This gate is a requirement for the separately authorized next stage, **not performed here**:

1. Do not use this same Python model for both emulated helper output and the expected table comparison. Execute the unchanged original C `extra_value`, `rounded` and `selected` under the original SEW8/FRACTIONAL configuration as the independent mathematical path. Preserve the original loop schedule and compare every call, not only distinct rows.
2. Compare all **10752*514 = 5526528 output/guard bytes** and all10752 saturation values. Separately compare the actual three-seed RNG progression, all4416 initial/override source assignment events, all336 mask epochs, clear-byte semantics, and all70644 cumulative selected-byte updates. An event adapter may observe the original assignments without replacing the original arithmetic oracle with Python expectations.
3. Cross-check fastpass and fallback behavior with vstart-only and saturation-only errors on numerically correct output, then data+vstart+sat, front/rear/both guards, and combinations across these categories. Compare the complete ordered diagnostic records, elements/checks totals and final error count, not just exit status. Exercise errors19/20/21 so suppression stops printing, not counting.
4. Include first/middle/last data and multi-byte corruption (including equal deltas), first/last guards, full514-byte end protection, and mismatch followed by matching words. A later Host/trace accessor must show all65 actual reads and65 initialization stores, including the two-byte tail. Deleted repeated initialization/input/mask events must not pass solely because final bytes match.
5. Full table/source identities must be independently checked before an equality fast path is trusted. The original-C reference must not read `fixed_expected_blocks`, `fixed_expected_index` or `fixed_expected_sat` to produce its own expected values. Separate generated-model correctness from packed-code correctness and from helper/ISA execution.

## Remaining Limits

The generator creates only a fresh exclusive directory, saves inputs before/after, copies original helpers and records failed generation rather than overwriting a prior attempt. It contains no compiler/subprocess/Spike/DUT path. Its CLI flag is an intent guard, not independent runtime authorization; later entry must bind these reviewed source hashes.

No actual generated table, compile flags, image layout, stack map, whole-CFG instruction count or <=3h runtime is accepted here. The prior incomplete2698536 cost subtotal remains incomplete. Generated mask code size, register pressure, inline comparison topology, spills, caller/status costs and exact instruction widths must be charged after a separately authorized fixed compile. No longer budget, smaller scope, repeated compiler trial or automatic reference/DUT follows this review.
