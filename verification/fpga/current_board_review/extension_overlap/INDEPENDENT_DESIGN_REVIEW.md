# Independent Extension Overlap Design Review

2026-10-10. Static review only. No RTL, sealed comparison input, shared report,
or test was changed; no build or simulation was launched. Tesla owns the current
VL127 measurement. References below are to the integration worktree.

## Decision

The missed classification in [STATIC_VL127_20261010.md](STATIC_VL127_20261010.md)
is real at source level. Whether it explains the current measured stall remains
conditional on maintenance completing and the target not being accepted.

**Do not simply delete all three CSR-SEW comparisons globally.** Destination
EEW greater than source EEW identifies the relevant data-layout conflict, but
does not by itself identify a widening arithmetic instruction. The smallest
bounded change is to retain the old widening domain and explicitly include
decoded VZEXT/VSEXT in the three cooperating predicates. This is a static design
recommendation, not a validated patch. Nonzero-vstart preservation requires an
additional decision before claiming complete extension support.

## Reviewed Identity and Original Case

SHA256 at review:

| File | SHA256 |
|---|---|
| hardware/src/ara_dispatcher.sv | 4eda3df195e1a8ec319e51a14df1a051964cd08f6ee10335145a7c10cc89db4d |
| hardware/src/lane/lane.sv | 5e621bf955cad43e87881253a2d8626c5bad23e2251e2ee7276a3518d1036241 |
| hardware/src/lane/lane_sequencer.sv | 60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0 |
| hardware/src/lane/operand_requester.sv | 327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2 |
| hardware/src/lane/operand_queue.sv | eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d |
| STATIC_VL127_20261010.md | 7004e43c00769b42d9006f944b9e40d557efe7118c5df406a30ecac7c8b2a273 |

Independently read and hashed the pinned `scenario.c` and `scenario.S` under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extension_single01/rvv_trace_extension_single_e16_m2_vf2/`.
Their hashes match the candidate report: C
`bcd4f3aec5436bf846429ccb8fef9d2207f07f6ecf6b0efeb0a37b7b3b923e2c`,
assembly `9235360ef269649313c2a1ba84450b438fb07d3f056383194e11d574c4472152`.

`scenario.S:29` is the overlapping zero-extension function; `scenario.c:37`
selects seed0/op2/length-index5/mode0. At capacity128, this is VL127, all-one
mask, e16/m2, `vzext.vf2 v24,v25,v0.t`. The source load overwrites the upper
half of old destination before extension. `scenario.c:45` accounts for this;
the preserved final element is **0xb26b**, not the initial fill 0x5b5b.
`scenario.c:61` checks returned vstart, all256 output bytes and both guards.
The historical reports and binary identities remain those in the candidate
report; they are not new current-image measurements from this review.

## Why the Three Predicates Must Agree

`ara_dispatcher.sv:2809` decodes all six extension forms to VADD/scalar-zero,
without a vector vs1, with `CVT_WIDE` and the appropriate conversion_vs2.
Unlike ordinary widening arithmetic, destination SEW is not incremented.
Source EEW and LMUL are reduced by the extension factor (`:2818`, `:2842`,
`:2864`, and their signed counterparts).

- `masked_widen_layout_conflict` at `:5488` must retain the narrow source
  before normalizing a masked destination. Its source-EEW comparison and
  high-overlap test already describe this case, but the CSR comparison rejects it.
- `source_snapshot_resolves_widen` at `:5500` must recognize that retained
  source on re-decode. It matches register base, EEW and LMUL, not just validity.
  This predicate does **not** itself include a source-width/high-overlap test;
  its effect is gated by `legal_widen_overlap` at the two use sites.
- `legal_widen_overlap` at `:5668` must suppress destructive destination-first
  normalization before capture, but stop suppressing it after the narrow source
  is safely replayable (`:5679`, `:5791`).

Changing only capture can leave normalization/snapshot recognition inconsistent.
Changing only legal overlap sends a masked operation to a tail-only repair path,
which cannot repair arbitrary masked-off holes. Changing only snapshot-resolved
does not create a snapshot. Keep the existing wide-vd replay exception at
`:5516`: a retained wide `.wv` source is not interchangeable with the narrow
source retained for extension.

For the original setup, the intended bounded sequence is: retain v25 in EEW8;
normalize the destination registers intersecting [0,127) to EEW16; replay v25
through AluB with ZExt2; issue the original once. If the source initially needs
normalization, legal-overlap suppression must first allow source normalization,
then capture on re-decode. This is the falsifiable alternative to alternating
destination/source reshuffles in the candidate report.

## Minimal Safe Domain and Preservation Conditions

1. Replace the old domain test in the three predicates with conceptually
   `legacy_dest_gt_csr || decoded_integer_extension`, keeping all other tests.
   Prefer a decode-local flag for exactly VXUNARY0 VZEXT/VSEXT, or an equally
   exact decoded signature: VADD, CVT_WIDE, scalar-zero, no vector vs1, vector
   vs2, and ZExt/SExt2/4/8 conversion. Do not use VADD alone or CVT_WIDE alone;
   FP widening arithmetic deliberately also uses CVT_SAME (`:5661`).
2. Preserve decoder legality at `:2891`, alignment checks at `:3088`, and
   `widening_high_overlap` at `:442`. The latter requires integer source LMUL,
   a strictly smaller source group, and an exact common high end. It is not a
   generic permission for any intersecting groups. Do not admit same-base,
   low/interior overlap, fractional-source overlap, or misaligned groups.
3. Do not change `widen_accumulator_layout_conflict` at `:5472` for this fix.
   Extensions do not read vd as an accumulator; widening MAC preservation is
   an existing, separate path. Preserve its ordering and the `.wv` exception.
4. Preserve snapshot capture length **VL in source elements**, not destination
   byte count or VL/factor. Capture starts at zero and is unmasked, writes no
   architectural destination, and waits for backend idle (`:1481`). Completion
   before setting valid is at `:1509`. One extension has only one vector source,
   so it does not require a second snapshot owner.
5. Replay must retain source EEW/conversion, not the newly recorded vd EEW.
   `:5541` matches the saved view and cancels its reshuffle. AluB propagates
   replay/conversion at `lane_sequencer.sv:515`. `lane.sv:514` captures raw
   lane-local words; `:499` substitutes those words into the ordinary queue.
   `operand_requester.sv:443` initializes the word index, and `:518` advances
   only with queue capacity and satisfied hazards. This is not converted-result
   injection. Preserve drain-before-recapture and stable replay under stalls;
   dispatcher local-valid clearing at `:5902` must not permit shadow overwrite
   while the previously issued operation still consumes it.
6. For masked extension, normalizing each touched destination register preserves
   its old masked-off and tail bytes in the output EEW. VALU's existing BE at
   `valu.sv:944` then applies prestart, VL and predicate. Preserve the mask stream;
   all-one mask data does not turn an encoded masked instruction into vm=1.
   Maintenance must not touch v0 or architectural bytes outside its layout task.
7. **Unmasked prestart is a separate static safety gap.** The proposed three
   domain changes alone can route vm=1/vstart>0 extension through overlap repair
   without source capture. `:5826` initializes prefix repair only for narrowing;
   `:5866` adds an accumulator-only exception. `OVERLAP_FIXUP` at `:1396` repairs
   elements from VL onward, not below vstart. VALU suppresses prefix writes, but
   that cannot convert preserved raw bytes from the old EEW to the new EEW.
   Example to discriminate later: initial destination/source EEW8, e16/m2
   v24/v25 extension, vm=1, vstart1, VL127. Prefix and source need simultaneous
   views; tail repair is insufficient. This is a static risk, not a measured
   new failure. A scoped solution is to use source-capture/normalize/replay also
   for extension when vstart!=0 and vd needs normalization. Do not blindly run
   prefix reshuffle before capturing a source that that prefix can overlap.
8. Alternatively, always snapshot legal overlapping extensions before needed
   destination normalization, including unmasked cases. This reuses existing
   hardware and avoids assuming factor-independent read-before-write timing,
   but adds maintenance and is not the smallest performance change. Either
   choice needs the regressions below; no implementation is approved here.

Complete untouched registers can retain their old EEW: destination maintenance
uses active-register selection (`:382`, `:1138`, `:5350`), and normal issue updates
only active-register metadata (`:5930`). Do not require every register in the
LMUL group to have one EEW, or relabel untouched prefix/tail registers as converted.
VL0/vstart>=VL must retain the existing no-maintenance exit at `:5332`/`:5951`.

## Factor Coverage and Other Operation Classes

| Form | Destination SEW supported by this decode | Legal overlapping destination/source LMUL pairs |
|---|---|---|
| vf2 | 16,32,64 | 2/1, 4/2, 8/4 |
| vf4 | 32,64 | 4/1, 8/2 |
| vf8 | 64 | 8/1 |

Fractional sources can be valid **disjoint** extensions, but are not accepted as
high-end overlaps by this decoder. Include signed and unsigned forms. AluB has
IntExt2/4/8 enabled (`operand_queues_stage.sv:103`); queue conversion and consumption
are explicitly factor-dependent (`operand_queue.sv:338`, `:367`, `:505`, `:523`).
Snapshot capacity is eight registers per lane (`lane.sv:333`), with byte/word
counting at `:516`; vf4/vf8 do not justify dividing capture VL by four/eight again.

| Class affected or at risk under indiscriminate gate deletion | Static assessment / regression need |
|---|---|
| Indexed loads with narrow indices | `:4152`/`:4220` keep destination=CSR SEW but set smaller index EEW/LMUL. An exact-high index overlap now also satisfies the generic widening geometry. Existing index snapshot, mixed-layout normalization, and replay old_eew ownership are at `:5404`, `:5564`. New classification is not proof of corruption, but it crosses memory/fault/segment semantics without need. Exclude from this extension change; retain masked/unmasked alias controls. |
| VRGATHEREI16 | `:1792` gives smaller index EEW/EMUL at SEW32/64. Geometry alone must not authorize destination/index overlap or substitute widening's sequential source consumption for gather's protocol. Existing source-source alias snapshot and full-capacity data capture (`:5783`) must remain unchanged. Test legal disjoint destination plus source-source alias; keep reserved destination aliases negative. |
| VIOTA | `:2692`/`:2718` use a packed-mask source's stored EEW and LMUL1 (`:3080`), but a data-vector destination. A source physically at the high end can satisfy the stripped tests; that is not arithmetic widening or proof of architectural legality. Do not route packed-mask data through generic widening repair based on its notebook EEW. |
| Integer/FP widening arithmetic, multiply, MAC, `.wv`/`.wx` | Existing intended domain. Retain masked accumulator-old-vd behavior, dual-source serialization and wide-vd replay, including scalar widening and FP CVT_SAME. New classifier should not change their truth values. |
| Integer/FP narrowing and clip | Existing low-alias snapshot/preserve path (`:5584`, `:5616`, `:5742`). Do not redefine all snapshots as narrow-source widening snapshots or change their prefix merge. |
| Reductions and integer/FP mask results | Excluded from legal widening by `single_register_result` (`:138`..`:165`). Preserve exclusion, scalar seed geometry, and reduction-specific repair at `:5650`. |
| Ordinary ALU, slide, gather, compress, stores, scalar extraction, whole moves | Equal effective widths, absent vd/source, equal group sizes, or specialized normalization usually exclude them. Keep those exclusions; notably `vs2_reshuffle_eew` intentionally overrides gather/compress fields at `:5319`. A broad conversion/opcode heuristic is not equivalent. |

## Required Evidence Before Signoff

These are proposed checks, **none run by this review**. Reuse Tesla's original
VL127 measurement/capture; do not launch a duplicate.

- Original seed0/op2/VL127 case: capture completes, source snapshot matches raw
  v25, no repeated EEW8/16 alternation, one accepted original, full old-destination
  oracle including 0xb26b tail and guards. Preserve original provenance.
- Signed op3 and all-zero/0xaa/0x24 masks: distinct active results and undisturbed
  holes throughout both registers. Derivatives are not the original single.
- vf2/4/8 table above: source initially correct, initially wrong, and mixed per-
  register EEW; signed boundary values; disjoint controls. VL near aggregate-word,
  register, source-overlap-start and VLMAX boundaries; full VLMAX and VL0.
- vm=0 and vm=1 with nonzero vstart inside a word, on a word/register boundary,
  and inside the overlapping high source; vstart>=VL. Check complete prefix,
  body, tail and per-register metadata, not only active element values.
- tu/mu exact preservation is mandatory for the original. For ta/ma derivatives,
  accept only architecturally permitted element outcomes, never arbitrary byte
  corruption; prestart remains preserved. Do not weaken the original oracle.
- Capture/replay backpressure, partial-lane completion, last partial source word,
  immediate dependent consumer, and consecutive snapshot users. Check snapshot
  index bounds/accepted beats, source lifetime and immutable shadow ownership.
- Negative legality: same-base/low/interior overlap, fractional overlapping source,
  misalignment, invalid factor/SEW/LMUL. Positive high-end placement up to v31.
- Shared-path sentinels: masked widening MAC, `.wv` dual-source/wide-vd replay,
  FP widening arithmetic and conversion, narrowing prefix preservation, widening
  reduction, indexed-load alias, legal gather source alias, mask result and VIOTA
  non-overlap. Classifier equivalence for non-extension decodes is a useful static
  acceptance condition for the bounded proposal.

Bottom line: approve the **direction** of recognizing extension by effective
source/destination widths within an explicit extension domain. Do not describe
global gate removal or the three-predicate change alone as fully safe for all
mask/tail/prestart cases. Current stall proof, factor timing, and prefix coverage
remain pending the owners' measurements and review.

## Final Current-Patch Static Domain Review

Reviewed again on 2026-10-10 after the parent incorporated the extension
classification and unmasked-capture direction. Current dispatcher SHA256:
`8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2`.
This appendix records the implemented scope; earlier sections remain the
historical proposal. No RTL or sealed input was changed, and no new test,
simulation or build was run for this final review.

**Domain conclusion: the extension-specific expansion is appropriately bounded.**
`integer_extension` defaults to zero at `ara_dispatcher.sv:1028` and is set only
inside VXUNARY0 for rs1=2..7 at `:2812`, covering exactly signed/unsigned vf2/4/8.
The three cooperating predicates at `:5495`, `:5509` and `:5680` retain the
legacy destination-greater-than-CSR domain and OR this exact extension domain.
Source-width checks, legal high-end group overlap and single-register-result
exclusions remain. The flag neither legalizes reserved extension encodings nor
widens the classifier to indexed loads, gather indices or packed-mask sources.
For non-extension decodes these three predicates retain their former truth
conditions. Existing widening/MAC, wide-vd replay and narrowing ownership are
not redefined by this extension change.

The `(!ara_req.vm || integer_extension)` condition at `:5496` now includes
unmasked extensions when an old destination layout conversion is required.
This addresses the earlier masked-only routing objection for that domain,
including nonzero-vstart operations whose active destination registers need
conversion. Capture precedes destination normalization; snapshot matching
retains source base, EEW and LMUL (`:5509`), replay retains the source view
(`:5572`), and extension capture length remains VL in source elements
(`:5796`), not VL divided by the extension factor. No new predicate consumer,
mask bypass or production output-layout change is introduced.

**Important limit: unmasked capture is conditional, not universal.** The current
code still requires `reshuffle_req_d[0]` at `:5497`. Full unmasked vstart0/VLMAX
pure overwrite suppresses that request at `:5393`..`:5396`; an already-correct
active destination layout also leaves it clear. Those legal high-overlap
extensions can therefore retain the existing read-before-write/OVERLAP_FIXUP
path. This patch alone is not a proof that vf4/vf8 no longer depend on that
path's source-consumption timing.

The previously reported mixed-layout prestart concern also remains static and
unproven, not a new measured failure: e64/m8 `vzext.vf8 v24,v31`, vstart16,
VL17, with old v24 stored EEW8, active v25 already EEW64 and source v31 EEW8.
The active destination and source can both require no reshuffle, bypassing
capture. Generic overlap handling initializes prefix repair only for narrowing
at `:5839`; OVERLAP_FIXUP computes active_elements from VL rather than vstart
at `:1410`..`:1415`, then relabels each visited register at `:1446`. Thus a
complete untouched prefix register can be relabeled without conversion in
this static scenario. The new unmasked condition alone does not close it.
This is the same earlier review boundary, not an additional case campaign.

The working-tree diff also contains whole-register-move restart and widening-
reduction legality changes; they are outside this extension-domain conclusion.
Accept the bounded extension classification and conditional capture design;
do not interpret this review as all-layout functional signoff or as full04
runtime results. Existing owner measurements and the ongoing original-case
pipeline remain separate evidence. No further cases were added in this turn.
