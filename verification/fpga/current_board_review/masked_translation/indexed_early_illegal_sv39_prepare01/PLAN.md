# M7 Indexed Prefix Recovery

New boundary regression, not archived original16 replay. Reuse the accepted
mask_drain Sv39 runtime, independent oracle and single-case frozen M7 runner.
No RTL/image/delay changes, one unique bounded reference then one DUT run.

Primary: e64m1, VL3, vstart0, mask byte0x06, ordered
`vsoxei64.v v24,(a0),v16,v0.t`. Base0x40000000; offsets[32,8,17].
Element0 is skipped, element1 stores to aligned mapped base+8, element2 is
misaligned at base+17. Both data pages are mapped R/W/A/D from the start.
Expect exactly cause6, exact target PC/tval base+17, vstart2, VL3/vtype24.
Cause15/pagefault, cause7/accessfault or cause2/illegal are failures.

Before modifying state, handler reads vstart2 and captures whole source
registers and8KiB prefix memory. Clear vstart only for handler vector work.
Require prefix element1 committed, skipped/fault addresses untouched. Poison
the committed base+8 word, reload the same full index register with only
element2 changed17->16, restore VL3/vtype24 and actual saved vstart2, then
MRET without changing MEPC or PTEs. Require no prefix replay (poison remains)
and only element2's new aligned store. Read actual post-retry vstart0.

Follow with an ordered indexed store using different index/data registers
v20/v8, base+256, scrambled offsets[24,0,16], mask0x05 and vstart0. Distinct
data/address/predicate make stale SlideAddrGenA/StA/MaskM state visible.
Retain full source-register tails/neighbors, complete8KiB data and12KiB page
tables/guards, captured prefix image, exact traps, mask bytes and CSR restore
checks. This VL3 test does not claim exhaustion of depth2 multiword queues.

M7 frozen addrgen.sv:921 skip descriptors precede alignment/translation;
1117 local indexed alignment sets idx_op_error and fault vstart;514/550
deliver cause6 and early-store indication without an exception descriptor.
Frozen vstu.sv:584/595 forbid cleanup while a good descriptor remains and
until pending B drains. Translation requests may still be asserted in the
same combinational path; do not claim zero MMU traffic. Mapping all offsets
within one valid page separates the intended fault from page exceptions.

Spike source cfg.cc:41 defaults misaligned=false; do not pass --misaligned.
VI_ST_INDEX sets vstart before the store and skips lower indices on restart.
The unique reference must itself prove cause6/prefix/retry, not infer it.

M7 simulator.conf verify_axi_delay=1; ara_system.sv:368 uses fixed input
delay3/output0, not a runtime W-delay option. Keep it unchanged. A passing
SoC proves real queues/CSR/same-PC recovery but does not alone prove the old
early-error-with-good-head/pendingB0 timing window was exercised. Existing
local old-M6 counterexample remains root evidence; extra W pressure, if
needed, belongs to a separate explained TB, not random timeout/delay tuning.

Budgets: reference500k instructions/120s/128MiB, DUT900s plus bounded checker
teardown in a1200s direct-owner service. No automatic retry or bound growth.
