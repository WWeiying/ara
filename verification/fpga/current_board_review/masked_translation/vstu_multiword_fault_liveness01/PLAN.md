# VSTU Multiword Fault Discriminator

Hypothesis: current unchanged VSTU clears its issue-valid and signals store done on first
active translation fault after popping at most one buffered mask. Its mask_input_valid is
gated by issue-valid, so any unaccepted tail mask remains in MASKU. At 4 lanes/EW64,
two prefetched windows cover VL8; VL9 requires a third window and leaves commit=1.

One real MASKU/VSTU/AddrGen/sequencer request per VL8/9. Source is VSSE stride0,
mask enabled/all-one external packed predicates, EW64/LMUL4/vstart0. AddrGen's real
MMU request triggers a modeled STORE_PAGE_FAULT two cycles later. No AXI AW/W or
B response. Store data and mask are external ready/valid lane source models; no force,
deposit, queue counter assignment, or internal-state injection. Hierarchy is read only.

Pin a private snapshot of current RTL dependencies; unchanged VSTU must exactly equal
candidate06 frozen VSTU. VLDU isn't compiled. No RTL/SoC image/old evidence edits.
100-cycle result, stable cycles80..100, 200-cycle RTL watchdog, 60s host startup
bound per compile/case. Compile once, each case once, no retries. Cycle CSV only.
Scope: isolated four-module liveness discriminator, not full SoC acceptance.
