# M9 Boundary Sufficiency Review

Decision: no new evidenced production defect or static blocker. LOAD local7 supports its declared e64/nontranslated scope, not all EEWs, STORE or SoC/MMU acceptance. Production AddrGen remains3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5. No production/sealed files modified, new simulator run, CSV parse or long-task query.

## Static Predicate And Context

- unsafe_stride_defer uses original held remaining bytes, not absolute VL and not the decremented AXI count. lookahead_len_q and pe_req_q are captured from the same accepted request. It remains true until the late exception is acknowledged; a prefix transfer cannot accidentally disable WAIT.
- For supported EEW1/2/4/8 and legal M9 VLEN1024/LMUL requests, maximum transfer bytes are1024, within the existing11-bit vlen_t. No new arithmetic-width defect is evidenced. A request with start>=VL is dispatcher-elided; forcing one internally is not a genuine boundary test.
- Negative stride is tested as an address low-bit pattern, not an unsigned magnitude comparison. -8 is safe for e64; -4 is unsafe. Accepted lookahead multiplication/address addition already use the original two's-complement address semantics.
- The first effective address must be checked independently of raw base. Initial fault supplies original start on its same ack; late fault supplies VL-(remaining>>EEW), including a nonzero original start. q exception/index pair is forwarded after the ordered marker push, not acknowledged as success in the marker's construction cycle.
- For vm1 constant stride, aligned first address plus unsafe stride necessarily makes the very next element unaligned. More than one valid element before this alignment fault is mathematically impossible. Do not synthesize a fake many-prefix case. Real many-prefix faults require a different situation, such as masked skips or a later translated page fault.

## Actual Coverage And Smallest Missing Boundaries

Existing LOAD7 includes ordinary stride8, unsafe+4 late fault, effective-start remaining1 success, initial restarted fault, unit, stride0 and safe-8. Exact normal cycle comparisons cover four controls. The remaining1 boundary is already exercised by case2 (VL2/start1/baseB-4/stride4), so it is not an untested correctness gap.

| Boundary | Evidence status / minimal useful discriminator |
| --- | --- |
| EEW16/32 | Not covered by LOAD7 or inspected STORE4. At least one width-specific unsafe case each: stride1/e16, stride2/e32, VL2/start0. Check exact2/4B prefix enables, cause/tval/index1, no offending transaction and full destination/memory guards. These exercise distinct byte-width/partial-result paths, not new RTL hypotheses. |
| Negative unsafe stride | Safe-8 is covered; unsafe-4 is not. One e64/VL2/baseB/stride-4 case must fault atB-4/index1 after a validB prefix. No positive-stride-derived tval. |
| Nonzero-start late fault | Current initial start1 and late start0 tests do not compose this case. Example e64/VL6/start4/baseB-16/stride4: actual addressesB thenB+4, fault index5, not1 or4. Verify prestart/tail untouched and only element4's prefix. |
| Remaining1 fast-path cycles | Correctness covered by LOAD case2. Only if claiming zero additional cycles for every existing safe path, add an aligned-raw VL1/start0/stride4 M8/M9 comparison. The current case2 cannot be an unchanged-M8 normal control because old raw-base rejection was wrong. No mandatory duplicate correctness test. |
| W/B backpressure | Inspected STORE successor explicitly holds Wready until40 and delays prefixB to50; its contract checks protected owner, good descriptor not popped early, full data/strb/guards and final B drain. This is not proof of descriptor FIFO-full or translated-MMU backpressure. |
| FIFO/R/writeback backpressure | LOAD ready-bank model is always ready from its release setting, and its two-descriptor case cannot establish full FIFO pressure. A genuine prior-owner/queue-full or delayed R/final-grant check can distinguish marker blocked by capacity, stable context, no success ack and eventual drain. No internal-state force. |
| MMU-enabled local reject | Neither local suite enables translation. Prefer a real resident-map SoC prefix followed by local alignment fault, then a legal scalar access/vector control with bounded progress. Actual MMU req/grant observation is needed to claim zero acquisition; architectural progress alone establishes no lasting orphan, not zero MMU activity. |

These are coverage limits and focused acceptance choices, not measured failures or reasons to change production again. They can be folded into Aquinas's bounded successor/SoC contract rather than rerunning passed source cases.

## STORE Contract Review

Read successor01/probe_tb.sv only, not active outputs. AWready is fixed1, so counting aw_valid counts real handshakes in this fixture. Real VSTU spill registers are included in st_idle; final idle plus source handshakes covers their discard/drain. Prefix memory checks include all64 bytes and exact untouched guards.

The response predicate RESP_CONTEXT_OR_PENDING permits st_pending as an alternative to actual done. Current M8/M9 WaitForStoreB is1; if the claim is architectural response after B, the clean contract should assert the actual prefix B count/completion at response, not treat pending as proof that B returned. Existing protected_cycles requires nonidle until done and may catch an early state release indirectly. This is a narrowly identified contract strengthening, not an established false PASS or RTL defect. Do not edit the already consumed fixture during its run; tighten a successor or the SoC entry contract.

An early initial store fault has no AW/W/B; a late store fault has the exact valid-prefix AW/W/B before final completion. Do not merge their expected counts or treat pending_b0 before WLAST as a drained prefix. Keep the descriptor-head guard and owner matching.

## SoC Entry Contract Pending Actual Fixture

No SoC source path was available in the reviewed artifacts; no SoC checker/entry approval is made. Requirements sent directly to Aquinas:

- Bind actual target PC/encoding and helper setup, actual requested VL/EEW/vstart, and direction-correct cause4/6 with exact mtval/absolute vstart. Page/access/phase/staging faults are unexpected failures, not alignment acceptance.
- Check complete architectural prefix plus prestart/tail/guards using real initialized input and post-trap scalar observations. Never manufacture missing vector payload or a successful normal target return after a trap.
- Retain actual monitor exit separately from architectural expected-trap outcome; require owned protocol closure, no retry/abort/pin drift. Event early-elision is legitimate only for the actual early fault, not for a prefix-owning late fault.
- For translation-enabled coverage, use real page setup and trap return; require a later legitimate memory operation to make progress. Direct MMU no-acquisition claims require actual relevant signals/probes. Software RVFI alone does not show AXI B counts or all MMU arbitration.

## Evidence Identity

LOAD REVIEW.md SHA0ef1058f6f4731ee8ecd979161c8d90a46b8221d230f5c45951bbf23a43f9bc2; result SHAe2af226c3b560e06782bd1bd1c482bd5e841970d123488be99a876a42b6eb5e6, status SEVEN_M9_CASES_PASS_NORMAL_CYCLES_IDENTICAL_NOT_SOC. Inspected STORE successor probe SHA0d6a60cb76e14229ec4e4f05df9b05db293b6ccb083e77795d60d40506fdf440. This review does not consume running STORE evidence as accepted.
