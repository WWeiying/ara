# M9 Precise Alignment Handoff

Decision: measured P1 supports a coordinated AddrGen repair. Production RTL belongs to main only. This is not candidate acceptance or a SoC/Linux result. Original static PLAN.md and all measurement/error records remain unchanged.

## Accepted Root Evidence

Aquinas's single real AG/VLDU/sequencer measurement (N4, AXI128, translation disabled) proves:

- stride8: AR/descriptor pushes9,10; R/pop11,12; valid16B; done15; idle16.
- stride4: AR/descriptor pushes9,10 atB/B+4; R/pop11,12; valid12B; issue/commit demand16B; no exception, result or done through255.
- Both return a no-exception AG ack/sequencer response at10. Thus a future late local fault must not inherit this success-response route.
- Sole simulator actual0/10.6416s includes a preserved terminal TB fatal: its diagnostic AG-idle assertion is wrong because idle includes the unfinished owner, not merely empty transactions. Original batch stays ERROR.
- Closed audit accepts502 rows/83 unchanged pins, status CLOSED_CYCLE_EVIDENCE_ACCEPTED_P1_REPRODUCED_NOT_ARCH_PASS. CSV was not re-read by this handoff; no rerun.

## Production Change Boundary

1. **Effective start, same-cycle precise context.** In initial vm1 nonindexed rejection, test the existing vaddr_start (unit base+start*EEW; strided base+start*stride). tval uses that same address. exception_vstart must be original start on the ack sampling edge. Its current output is registered: changing d only on the ack cycle is insufficient. Use a single-driver early-fault mux or proven actual-request preload, not a second always-block writer. Rejecting the first accessed element remains an early/no-descriptor fault.

2. **Defer only unsafe strided responses.** Define unsafeStrideDefer for vm1 VLSE/VSSE with remaining elements>1 and stride low EEW-alignment bits nonzero. Reuse registered lookahead_len_q (>one element's bytes) and held stride/EEW; no new multiplier/subtraction stage is necessary. Add only this class to the existing translated/masked WAIT_LAST_TRANSLATION route before descriptor processing. Final ready cannot acknowledge success while a new local exception is merely in exception_d; wait for the latched exception_q/index pair. Match normal completion signaling to the actual wait route as well.

   This excludes unit bursts, stride0, positive/negative EEW multiples, EEW1-byte operations and an aligned remaining-one request. Keep their original ack/issue timing, not an unconditional wait for every strided access. Never pre-reject the whole unsafe stride: execute its valid prefix and fault the first offending element.

3. **Ordered late fault, never duplicate early-illegal.** Extend the existing active, nonindexed, nonburst local-alignment branch to vm1; retain skip priority for inactive masked elements. With FIFO space, enqueue one ordered exception marker after the good prefix, cause4/load or6/store, tval=current address and vstart=VL-(remaining_bytes>>EEW). Stop later transfers. Every WAIT-route exception here originates from an ordered marker, so suppress early-illegal for this route irrespective of vm. Initial early faults and indexed handling remain distinct. Require marker/response ownership correspondence; do not suppress an exception lacking a delivery route.

4. **Local reject before MMU/AXI ownership.** Keep rejection ahead of start_req/translation_req. No AR/AW or mmu_req for the rejected element, including while its marker is blocked by FIFO/channel backpressure. Preserve legitimate prefix translation and indexed-MMU guards; do not issue a transient MMU request and then abandon it. Do not waive a real page/PMP/MMU exception.

Do not change VLDU/VSTU counters or synthesize the missing4 bytes. Existing ordered exception handling should commit only the valid load prefix, or finish actual store W/B prefix before discarding remaining operands. Keep existing descriptor-head, pending-B, owner and sequencer fault-completion guards. A contradiction in repair measurement calls for a revised hypothesis, not additional blind consumer edits.

## Minimal Repair Acceptance

- Same stride8 control must keep the actual baseline handshake/writeback/owner cycles and all16B plus112B tail checks. Normal aligned unit/stride0/positive-negative EEW-multiple controls must have zero additional cycles versus their unchanged baseline; unit cycles have not been measured by the current two-case run.
- Repaired stride4 load: only B's valid8B AR/R; no B+4 AR/MMU request; one ordered cause4/tvalB+4/vstart1; preserve valid prefix and inactive bytes; fault response only with completed owner/drain. Never call a short normal transfer successful.
- Effective-start control proposed after baseline is still unmeasured: VL2/start1/rawbaseB-4/stride4 accesses alignedB once. It must preserve prestart element0 and tail, not fault on rawbaseB-4. Conversely start1/rawbaseB/stride4 must fault atB+4 with original index1 and no prefix AXI.
- Store and translated behavior remain unmeasured. In focused repair validation require actual good-prefix AW/W/B and correct data/strb, no completion before B, no transfer/MMU acquisition for a locally rejected address, and exactly one owned architectural fault. Keep masked skips/all-off semantics intact.

No new simulation, image build, production edit or live-task polling by this reviewer. Main determines the bounded successor acceptance campaign; old baseline is not rerun just to append controls.

## Evidence Pins

- Measurement REVIEW.md:20f8f648fd99bdb38b0dca3326f9ca4aa8e88c95c9e3c47c7de00222bd0e7972
- closed_audit01/result.json:5725c6d9a56d488268cac6402d0e82ec8911e6059cafd019f4be0b0858da0349
- Original ERROR result:99115cf768583b7c2f0915771033f6c90b945620cf8684e09875245c6e2bd80d
- Closed CSV:6edb1777a39c6b81af06e62f2e49a7823c4e73726e9abc9496f4c684ddc93f1b
- Inspected AddrGen baseline:1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2
