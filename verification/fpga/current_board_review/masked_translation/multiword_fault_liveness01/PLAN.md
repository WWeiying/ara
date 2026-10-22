# Bounded Multiword Fault Discriminator

User authorized one short local VCS experiment, no RTL changes or SoC build.
Use unchanged frozen M6 AddrGen, VLDU, MASKU and ara_sequencer, with their
real predicate owner/window and descriptor connections. The two fixed cases
are e64m4, zero stride, vm0/all predicate bits one, start0, VL8 and VL9.
A single genuine packed mask beat is supplied through MASKU's lane ports.
The MMU model responds cause13 exactly three sampled cycles after a real
request qualified by VLDU's actual first mask window. No forced internals,
direct synthetic mask_valid at VLDU, invented mask abort or fabricated done.

Static hypothesis: a first-window fault can externally acknowledge at most
two predicate windows into the non-bypassed two-slot load cut. VL8 needs two
windows, VL9 three. After HANDLE_EXCEPTION removes the issue owner, its
mask_input_valid is false and the third MASKU word cannot be accepted. MASKU
commit remains1, keeping the real sequencer running bit and ara_idle low.
AddrGen supplies a fault marker but has no MASKU cancellation output. MASKU
has a separate two-entry output queue; enqueue there does not retire its
commit count. The four physical downstream/queue slots are NOT four completed
predicate-window handshakes.

Observe 100 cycles, requiring a stable exact terminal state for cycles80..100.
Require one request, MMU response, descriptor, load-done and architectural
exception response in both cases. VL8 must have MASKU-done/global-idle; VL9
must have remaining commit1, head first_element8 and refused handshake.
No data AR/R/prefix write is legal in this first-active-element experiment.
VLDU final flags must all remain1, distinguishing the new mask lifecycle
candidate from the already repaired prefix final-write path.

The CPU, lane requester and dispatcher are not instantiated. Lane readiness
and a correctly handshaken finite packed-mask supplier model their interface.
The CSV `flush_eligible_model` is the inspected dispatcher precondition
(exception response observed and real ara_idle), not a measured CSR response.
No flush is injected. VL8 global idle is not a claim that the local VLDU mask
cut is empty before the later production flush. Success of the discriminator
means expected defect reproduction, NOT architectural PASS.

Tesla confirms original RVV-16 e64m4's sixteen configurations all use VL8.
This VL9 boundary does not identify that archived Linux hang's root cause.
The original load PC10846/cause13 remains distinct from scalar kernel-store
traps in the other archived children. No original source is adapted here.

Command: `/usr/bin/python3 -B run.py` from this directory.
Output: new exclusive `measurement01/`; compile bound90s, two runs <=10s each,
200-cycle HDL watchdog. Existing local manifests supply the dependency list.
All RTL/includes, derived sequencer types and helper/TB are snapshotted/pinned;
all inputs are rechecked after execution. No retry or timeout increase.
