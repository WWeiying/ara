# Unmasked Strided Alignment Repair Boundary

Status: independent static repair proposal, pending Aquinas's single joint measurement. No production edit or simulation performed; no running segment job queried.

## Hypothesis And Scope

The inspected M8-equivalent AddrGen checks raw base initially and excludes vm1 from the later nonindexed local-fault branch. For EEW64/VL2/start0/baseB aligned/stride4, normal descriptors request8 bytes atB and an unaligned single AXI beat atB+4. AXI valid-byte bounds admit8+4 bytes, while VLDU still expects16. No precise fault terminates that short transfer. This is a reachable static hypothesis, not an independently measured result or historical Linux attribution.

Choose a precise alignment exception for unsupported element misalignment, not an invented larger payload or counter adjustment. Do not reject an entire byte-stride instruction before executing its valid prefix.

## Minimal Coordinated AddrGen Changes

1. Initial vm1 alignment uses the already computed effective vaddr_start, not pe_req_q.scalar_op (addrgen.sv:357-394). Unit start is base+start*EEW; strided start is base+start*stride. Set tval to that same address and exception_vstart to the original start. This first-element rejection has no new AXI/ordered fault descriptor and retains its early-illegal completion route. A misaligned raw base whose actual restarted element is aligned must not be spuriously rejected.

   exception_vstart_o is currently registered (:580), but this initial ack/exception is combinational. Merely writing exception_vstart_d on the rejection cycle would leave the old index at the sequencer sampling edge. Supply the original start on that same ack (a single-driver early-fault output mux or a proven accepted-request preload); do not introduce a second procedural writer across the two FSM blocks. The delayed ordered path already uses latched exception/index together and must retain that pairing.

2. Extend the existing ordered local-fault branch (:948-977) to unmasked nonindexed, nonburst element requests. Require actual predicate-valid/active, current address misalignment and descriptor capacity; masked skips keep priority. For vm1 the predicate is valid/active independently of MASKU. The fault marker follows every already-issued good/skip descriptor, emits no AR/AW for the offending element, stores current virtual address and element index VL-(remaining_bytes>>EEW), and terminates further descriptor generation. Reuse the existing cause4/load or6/store, vstart and exception buffer rather than constructing fake successful data.

3. Preserve the late response for nontranslated vm1 unsafe byte strides. Merely removing !vm is insufficient: ADDRGEN's same-cycle addrgen_req_ready currently acks success without forwarding newly written mmu_exception_d. At request entry, additionally use WAIT_LAST_TRANSLATION for VLSE/VSSE when remaining elements>1 and stride is not a multiple of EEW. The held request then forwards latched exception_q on completion. Match the last_translation_completed condition to the same wait class, so a waiting request cannot lose normal completion. No new FSM state is necessary.

   Derive this classification from held request fields, with VL>start before subtracting. With an aligned effective first address, the next element is unaligned iff stride's EEW low bits are nonzero. Negative strides use the same low-bit criterion. remaining1 cannot develop a later fault; stride0, +/-EEW multiples and EEW8-bit requests are safe. Keep their original handshake timing. Keep vm1 unit bursts, translated and masked paths otherwise unchanged.

4. An ordered WAIT_LAST_TRANSLATION exception must not also assert early-illegal (:545-551). The current !vm qualification is insufficient once vm1 late faults use descriptors. Tie suppression to the ordered nonindexed fault/wait route, or an explicit proven ordered-marker predicate. Initial immediate faults and indexed paths retain their existing appropriate early route. Assert that every suppressed early pulse has an ordered marker delivery; do not silently suppress an exception lacking either mechanism.

5. Local active-address rejection must dominate MMU/AXI launch (:1171-1182). With fault marker pending, FIFO full or backpressure, do not fall through to the MMU request branch for the rejected address. No mmu_req may acquire the shared arbiter for that local fault. Preserve legitimate prior-prefix translation completion and existing indexed request guard. Do not globally cancel or waive MMU/page/PMP exceptions.

## Consumer And Completion Invariants

- VLDU already waits for earlier good descriptors and commits the valid partial VRF prefix before processing its ordered exception (:613-698). Preserve byte enables and destination guards, not a forced16-byte completion.
- VSTU already requires the good descriptor prefix to leave the head and actual pending B responses to drain before exception completion (:581-606). pending_b0 alone does not prove W prefix completion. Preserve AW/W/B ordering and the current descriptor-head guard.
- Sequencer captures exception/vstart only with address acknowledgement and waits for faulting load completion or store-B completion (:979-1044). Never emit an earlier success response followed by an unowned late exception. Keep the original owner/PE identity until that terminal response.
- No new VLDU/VSTU/sequencer RTL changes are justified by this static review. If the measured consumer path contradicts these invariants, preserve evidence and revise the hypothesis before changing more modules.

## Discriminating Evidence

Use Aquinas's already assigned bounded joint real AddrGen/consumer measurement; do not inject counters or repeat trials without a new hypothesis. Baseline stride8 is the same-cycle normal control. The stride4 load prediction is two normal ARs atB/B+4,8+4 actual bytes, no fault and no done. Correct repair instead yields only the valid B transfer, exactly one ordered fault atB+4/vstart1/cause4, no MMU request forB+4, preserved valid prefix and eventual fault-owner done/response.

For a store counterpart require valid-prefix AW/W/B, no AW/W for the rejected element, correct prefix data/strb and no final completion before WLAST/B drain. No assumption that an early target fault itself allocated a downstream AXI transaction.

Before signoff, narrow representative checks should distinguish effective-start behavior: start1/baseB/stride4 faults atB+4 with no prefix; start1/rawbaseB+4/stride4/remaining1 accesses alignedB+8 without a false raw-base fault. Also check translated resident prefix versus local rejection, masked inactive misaligned skips, and identical aligned unit/stride0/positive-negative EEW-multiple cycle traces. These are future evidence requirements, not tests run here.

Static address projection checked9900 aligned-first combinations across EEW1/2/4/8, stride-16..16, start0..4 and remaining1..4: the remaining>1/nonmultiple-stride classification exactly identifies potential later misalignment. This arithmetic check does not model RTL timing or replace the joint VCS evidence.

## Read Identity

Sole worktree: /home/wangwy/openproject/ara_dsa_signoff_integration. Original P1 report left untouched.

- AddrGen:1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2
- VLDU:92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401
- VSTU:37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0
- Sequencer:bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655
- Dispatcher:c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d
- P1 report:37d0c0aff377556bbddf91cbcb71f0ace22ab7f40706b90eb9eba694805016b9
