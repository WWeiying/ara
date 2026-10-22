# Sequencer Fault Completion Boundary

## Frozen Baseline

Measured with host VCS, real `ara_sequencer`, public request/response ports only.
No internal force/deposit, production edit or full SoC build. AddrGen ack/fault,
PE readiness and load done timing are modeled public peers; this does not claim
that a second real AddrGen/VLDU pair has been simulated or that Sv39 is fixed.

- Run: `sequencer_before10/` in this directory.
- Baseline sequencer SHA256:
  `f1d6095e1ade018b9225678a493438da04e7d84f68a956bdf7a116941bfafc5b`.
- Fixed TB `sequencer_fault_tb.sv` SHA256:
  `2e6e022a52d436a8e6cf0ba2ece08f481d2c11bc41dcc347903ad5d5c145e182`.
- Seven probes completed, with response metadata checks and no simulation
  assertion failures. PROBES_COMPLETE is evidence collection, not RTL approval.
- Each named case contains `cycles.csv`, `run.log` and bounded `window.vcd`;
  `pins.json` records frozen sources and `command.json` records compilation.
- Request/response types are extracted from the pinned production `ara.sv`,
  using the established local-fixture approach, not guessed field layouts.

## Hypothesis And Discriminator

Baseline WAIT response logic at `ara_sequencer.sv:1013` requires AddrGen ack and
lane/mask acceptance. It adds a tagged done obligation for stores but none for
faulting loads. Therefore a non-first FOF exception can be returned to the
dispatcher while the corresponding VLDU instruction remains active in cleanup.
The independent VLDU public-port test establishes that accepting prefix data
and receiving its final bank grants can be separated by many cycles.

The distinguishing public signals are `addrgen_ack_i`, exception.valid,
`addrgen_fof_exception_i`, `pe_req_o.id`, the LoadUnit `vinsn_done` vector,
`ara_resp_valid_o`, `ara_req_ready_o`, and `pe_vinsn_running_o`. No internal
sequencer state is needed as evidence. Load ready is modeled low during the
fault-cleanup interval; it is high for the first PE acceptance.

## Cycle Results

All tested requests are unmasked unit-stride e16 loads, VL8. Fault metadata is
LOAD_PAGE_FAULT/cause13, tval `0x81234006`, vstart3. FOF exception is asserted
only when a FOF load actually faults. The TB validates these fields in every
response, including after the one-cycle ack input has disappeared.

| Case | Target VID | PE first | Ack | Other VID done | Target done | Baseline response |
| --- | --- | --- | --- | --- | --- | --- |
| normal_delayed_done | 0 | 5 | 9 | none | 21 | 9 |
| fof_fault_delayed_done | 0 | 5 | 9 | none | 21 | 9 |
| fault_delayed_done | 0 | 5 | 9 | none | 21 | 9 |
| other_vid_done | 1 | 9 | 13 | VID0 at16 | 25 | 13 |
| done_before_ack | 0 | 5 | 15 | none | 7 | 15 |
| done_with_ack | 0 | 5 | 9 | none | 9 | 9 |
| fof_no_fault | 0 | 5 | 9 | none | 21 | 9 |

The FOF fault's cycle9 CSV row has ack=1, exception=1, fof=1,
ldu_done=00000000, resp_valid=1, ara_ready=1, ldu_ready=0,
running=00000001, resp_exception=1, resp_fof=1 and resp_vstart=3.
The corresponding VID0 done pulse occurs only at cycle21. This directly proves
the response is 12 cycles ahead of the modeled legal load-completion boundary.
Plain load fault has the same timing. Nonfault responses at ack are intentional
controls, not failures to be slowed by a blanket load barrier.

The other-VID stimulus first submits a real nonfault load and retains its real
allocated VID0 without retiring it. The target then receives VID1 from the real
sequencer allocator. Both done pulses are asserted only while their VID is
actually in the public running vector. A future barrier must ignore VID0's
cycle16 completion and wait for VID1 at25. The baseline responds already at13,
so it does not establish a distinct wrong-VID-latch bug; this is a discriminating
regression control for the proposed fix.

The early-done and same-cycle-done cases require no extra bubble: response must
remain at ack15 and ack9, respectively. FOF without an exception must retain
the nonfault ack9 response despite done21.

## Preserved Fixture Errors

`sequencer_before08` retains the first compile failure: the TB referenced
`riscv::LD_PAGE_FAULT`, while this tree defines `riscv::LOAD_PAGE_FAULT`.
Only the fixture constant name was corrected.

`sequencer_before09` compiled and its normal control returned PE5/ack9/response9/
done21. The runner then rejected an X in the diagnostic unused other-owner slot.
The final TB prints -1 when that slot was never allocated. No request timing,
done stimulus, metadata oracle or production RTL changed. These failed
preparation records remain untouched; before10 uses their same frozen RTL.

## Acceptance Boundary

The measured response-ownership defect agrees with the independent static
integration finding. A scoped barrier should require the matching load VID's
completion only for an acknowledged load fault, preserve that completion if
it precedes ack, and preserve normal/FOF-no-fault ack response timing. The seven
fixed cases are ready for same-TB A/B when the parent provides that candidate.
This report does not authorize an unmeasured general broadcast-ready rewrite
or claim full-system scheduling, page-table, trap or restart signoff.

## Final Candidate Same-TB A/B

`sequencer_final12/status.json` is terminal: all seven simulations exited zero,
with frozen inputs verified. It will not be changed by subsequent work.
Final sequencer SHA256:
`bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655`.
`sequencer_ab12.json` records `PASS_7_SEQUENCER_FAULT_BARRIER`; reproduce with
`python3 -B analyze_sequencer.py --after sequencer_final12 --out NEW_OUTPUT.json`
from this directory (use a new output path to preserve evidence).

| Case | Baseline response | Final response | Matching done |
| --- | --- | --- | --- |
| normal_delayed_done | 9 | 9 | 21 |
| fof_fault_delayed_done | 9 | 21 | 21 |
| fault_delayed_done | 9 | 21 | 21 |
| other_vid_done | 13 | 25 | 25, ignoring VID0 at16 |
| done_before_ack | 15 | 15 | 7 |
| done_with_ack | 9 | 9 | 9 |
| fof_no_fault | 9 | 9 | 21 |

All request/ack/done stimulus cycles and allocated IDs match before10. The TB,
generated types and every pinned dependency are identical; only sequencer RTL
differs. Each target responds exactly once with checked exception cause, tval,
vstart and FOF metadata. Nonfault and early/same-cycle controls retain timing.

`sequencer_after11/` and `sequencer_ab11.json` remain preserved and terminal,
but pin intermediate SHA
`58d8e431cc222f0584b6a13086720adcd53b72daf6f57d4f024b39844e3f98e8`.
That intermediate seven-case pass does not substitute for final12: the final
allocation guard explicitly restricts completion-bit clearing to loads.

## Combined Test Feasibility

A real sequencer plus real VLDU fixture is feasible without internal forcing:
connect allocated request IDs and actual VLDU done feedback; retain the real
per-lane stream_register requesters used by the consumer fixture; model only
the public AddrGen descriptor/ack/fault and memory interfaces. Delay prefix
bank final grants, then present a subsequent load after the architectural
response to check owner cleanup and normal forward progress. AddrGen descriptor
ordering and exception-sideband timing must follow its public protocol, not
assume arbitrary interface reorderings. The existing seven cases isolate the
sequencer barrier; they do not themselves prove this combined path, Sv39,
trap handling or full-system signoff. No combined build was started here.
