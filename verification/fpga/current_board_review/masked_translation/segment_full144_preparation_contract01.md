# Complete Segment Alignment Source-Port Preparation

This contract supplements `segment_boundary9_gap_plan01.md`. It authorizes
preparation of the complete e16/m2 144-configuration source port, not a new
DUT launch or a claim that the historical Linux stall is reproduced.

## Required Scope

Retain all eight original helpers, NF3/NF4, unit/positive/negative stride,
offsets 0/1, VL 0/1/128, active/all-off masks and original nested-loop order.
Retain exact archived helper instructions, aligned staging/readback, both
phase stores, vstart return, full 8192-byte numerical oracle and 128-byte
predicate initialization. Do not substitute a 12-call prefix for the full
144-configuration goal.

## Permitted Scalar Cost Reduction

The original input and load-memory byte formulas are deterministic and do not
depend on DUT outputs. Precomputed immutable tables may replace their scalar
construction if Host comparison proves every initialized byte identical.
Aligned scalar word copies/comparisons may reduce verification instructions;
they must still inspect every byte, preserve first-error-byte identification
and reject all mismatches. No added vector verification instructions may
alter the original helper-to-helper register history.

Prove store/load expected buffers independently for every configuration,
including signed reverse strides. Check initialization of all four original
8192-byte buffers, not only the bytes modified by the target. Check the
linked memory footprint and stack bounds before any reference execution.

## Child And Fault Semantics

Linux executes each helper in an isolated child. A direct-call port must reset
all data before every call and must not propagate a child's store results into
the next configuration. This preserves deterministic data initialization but
does not reproduce Linux clone, COW, signal, scheduler or vector-context rules.
Such OS-specific closure remains open even if the source port passes.

Only a fault at the actual target instruction with nonzero offset, VL>0,
active mask and phase=1 can take the original permitted misalignment branch.
A phase-store, staging, readback, all-off or VL0 fault is a failure, not a
capability exemption. A trapped child has no invented numerical output or
successful return-CSR observation. Record numerical and capability outcomes
separately; never relabel capability exit77 as numerical PASS.

## Admission Evidence

Before VCS, require exact source/helper identities, exhaustive Host data and
oracle equivalence checks, negative corruption tests, actual Spike reference
completion and measured firmware instruction cost. Bind the simulator to
frozen M8 and use a reviewed dynamic checker for all original calls and
architectural outcomes. The complete proposed run must fit the three-hour
limit with a stated margin. If it does not, retain preparation and the budget
limitation rather than dropping checks or extending the timeout silently.
