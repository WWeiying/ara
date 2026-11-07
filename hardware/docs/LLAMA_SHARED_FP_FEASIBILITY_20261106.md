# Llama Shared FP Feasibility

Date: 2026-11-06. Static design assessment only. No RTL changes, EDA,
simulation, synthesis, new model execution, or performance acceptance.

## Decision

1. Do not double integer dot throughput alone. The measured Q4_K/Q8_K M4
   workload already needs four arithmetic issues per accumulator update on
   one QBS arithmetic port. Its service floor equals the current dot floor.
2. The smallest promising new component is an **II=1 normal FP16 x FP32 scale
   multiplier**, with conservative admission and unchanged full-FPU fallback.
   It needs a 11x24-bit significand product, normalization, RNE, NX, and tags;
   it is not the existing flag-free FP16 x FP16 helper. Proceed only after
   MAIN's actual-model, dynamic-MUL-weighted hit-rate audit and independent
   numerical proof. No implementation is authorized by this document.
3. A dedicated full FP32 scale-MUL port is the simpler general reference
   architecture. Keep the existing FMA and I2F paths. Do not assume that a
   second generic fpnew ADDMUL instance synthesizes into a MUL-only unit.
4. Borrowing one lane's existing FP32 slice is structurally possible without
   intermediate VRF traffic. Existing blocking QBS ownership makes an
   exclusive-command lease plausible. However, this is a new lane/VLSU
   protocol, not a wire into the current VMFPU result interface. Defer it as
   a PPA alternative; multiple borrowed lanes are not the first performance
   step while the original one-result/cycle QBS FMA port remains.

None of these changes alone establishes an end-to-end speedup at the present
64 integer products/cycle. A useful throughput experiment must eventually
coordinate dot, scale, FMA, conversion, entry lifetime, and physical supply.

## Evidence And Service Limits

The existing source-bound diagnosis is
`verification/out/e2e_supply_prefill_diagnosis_20261106_01/result.json` in
`ara_dsa_signoff_integration`, SHA256
`581ecd31248e3c192e8a96c6e42dac9a450955f704431c6e991cef1bdd60c183`.
It covers the actual M4/N32/K2048 Qwen3 QKV command population, 96 Q4_K and
32 Q6_K commands, not every model operation or every profile.

Each command performs U=4*32*8=1024 block updates. The accepted wide dot
configuration issues 64 integer products/cycle: `qbs_dot_array.sv` has
four rows and 16 product slots/row with `WideMatrixDot`; VLSU explicitly
instantiates `.WideMatrixDot(1'b1)`. The module parameter default remains off.

| Service demand per command | Q4_K/Q8_K | Q6_K/Q8_K |
| --- | ---: | ---: |
| Current dot issue cycles | 4096 | 4096 |
| Independent I2F operations | 2U = 2048 | U = 1024 |
| Scale MUL operations | 2U = 2048 | U = 1024 |
| Ordered accumulation FMA operations | 2U = 2048 | U = 1024 |
| Current shared MUL/FMA-port issue floor | 4U = 4096 | 2U = 2048 |
| With independent full-rate scale MUL, arithmetic floors | MUL 2048; FMA 2048 | MUL 1024; FMA 1024 |
| Hypothetical 128-products/cycle dot floor | 2048 | 2048 |
| Actual 256-bit physical R beats | 1737 | 2313 |

These are overlapping service requirements, not additive cycle predictions.
Even an ideal new FP port leaves the current Q4 dot floor at 4096. For a
future doubled-dot design, Q6 supply can exceed its 2048-cycle dot floor.
The old paired busy reduction, 693319 to 656103, was exactly its 37216-cycle
weight-phase reduction; compute-plus-overlap stayed 565248. Do not attribute
that result to spare FP arithmetic or predict the next complete-call ratio.

`qbs_compute_engine.sv` increments `probe_fp_input_blocked_cycles` on an
offered arithmetic/cast operation rejected by its unit. Zero does not mean
that a future faster producer has capacity. `probe_fp_busy_cycles` uses
`fp_busy`, whose accumulator definition includes live table entries as well
as functional-unit pipelines. It is not an arithmetic utilization counter.

## Existing QBS Contract

`qbs_fp_accumulator.sv` has 16 fixed stream slots, not an arbitrary free-list
ROB. The seven-bit accumulator index selects 8 banks x 16 rows. An entry
exclusively owns its accumulator until completion; another update to that
accumulator is rejected. A busy stream slot can backpressure integer results
even when other table slots are free.

The entry states are `FP_DOT_CONVERT`, `FP_AUX_CONVERT`,
`FP_SCALE_MULTIPLY`, `FP_MIN_SCALE_MULTIPLY`, `FP_ACCUMULATE_DOT`, and
`FP_ACCUMULATE_MIN`. Default `SplitIssue=1` separates I2F from the single
32-bit fpnew MUL/FMADD port. The arithmetic pipeline has two configured
register stages; the conversion pipeline has one. Each entry allows only
one in-flight micro-op, identified by a four-bit table-slot tag.

For Q4, retain this dependency order:

`I2F(dot) -> I2F(aux) -> MUL(d, activation_d) -> MUL(dmin, activation_d)
 -> FMA(scale, dot, previous_accumulator) -> FMA(-min_scale, aux, dot_result)`.

Separate requests for independent entries may overlap. Within one entry,
do not merge the two rounded scale products into a later FMA, swap the two
accumulations, skip the first-block FMA with zero, or reassociate blocks.
`entry_work_value_q` holds activation scale until its final scale multiply,
then holds the accumulator addend. A split return must preserve this reuse.

`qbs_half_scale.sv` already handles finite FP16 x FP16 exactly using a 22-bit
product and two valid-register stages, including finite half subnormals.
It needs no FP32 rounding or flags. Its current admission excludes affine
min correction and requires FP16 activation scale. Q8_K activation scale is
FP32, so the actual Q4_K/Q6_K workload above cannot use that route.

QBS numerical-contract v1 is fixed RNE, not dynamic architectural FRM.
`fflags_q` ORs completed arithmetic and cast status. VLSU publishes QBS flags
only on successful command completion (`qbs_active_q && qbs_success_valid`),
through `ara_sequencer` and the blocking dispatcher response. Private scale
status must join this path, never the ordinary lane exception path.

## Candidate A: Dedicated Full FP32 Scale MUL

Add a separate scale scheduler for both scale states, excluding those states
from the original arithmetic scheduler only when the new route is selected.
Keep conversion and accumulation FMA units and their rounding untouched.
One MUL/cycle is sufficient for the Q4 2U-MUL floor to match its 2U-FMA floor;
two scale ports are not required for the first doubled-dot target.

The minimal local interface is `valid/ready`, two 32-bit operands, fixed RNE,
`slot[3:0]`, and, if cancellation/reuse is supported, an epoch. Return
`valid/ready`, result[31:0], `status_t{NV,DZ,OF,UF,NX}`, and the unchanged tag.
Pipeline requests/results; do not add a combinational dependency from integer
result arbitration through a new FPU back into integer ready.

Scale returns update the scale field, entry state, and, at the last scale
operation, the previous-accumulator addend. Compute that addend index from
the **returning scale tag**, not today's original `fp_tag_out` wire. Permit
cast, scale, and FMA completions for different entries in one clock; assert
their tags are distinct. OR all statuses in one owner. Only the existing FMA
completion writes final accumulator banks and emits `update_valid_o`.

A statically MUL-only, IEEE-complete implementation needs product,
normalization, rounding, exceptional-input handling, pipeline/tag registers,
and handshake control. Simply cloning fpnew ADDMUL may retain an FMA adder
and unnecessary operation selection. Actual area/frequency remains unknown.

## Candidate B: Restricted FP16 x FP32 Scale MUL

### Exact Normal-Range Arithmetic

Let the normal half weight be `(-1)^sw * A * 2^(ew-10)`, A in [1024,2047],
ew=half_exponent-15. Let the normal FP32 activation be
`(-1)^sa * B * 2^(ea-23)`, B in [2^23,2^24-1], ea=single_exponent-127.
Then P=A*B is a **35-bit exact integer**, with leading bit 33 or 34.
This is the same exact product as first exactly widening the normal half to
FP32 and multiplying it by the activation; no floating intermediate occurs.

Set c=P[34], E=ew+ea+c, and shift=10+c. Keep `P >> shift` as a 24-bit
significand, retaining an extra carry bit for rounding. For the discarded
bits use exact round-to-nearest-even:

`increment = guard && (sticky || retained_lsb)`.

The guard is P[shift-1], sticky is the OR below it, and
`NX = OR(P[shift-1:0])`. If rounding produces a 25th bit, renormalize and
increment E. The result sign is sw XOR sa. Sign must not be restricted to
positive model scales. For admitted normal results the other status bits
are zero; NX is not optional, even if downstream values happen to match.

### Conservative Admission Without Replay

For the first component, require both inputs to be normal and require the
signed unbiased sum S=ew+ea to satisfy **-126 <= S <= 125**. Then:

- Before rounding E is in [-126,126]. No subnormal handling is needed.
- Even a normalization carry from rounding leaves E <= 127: no overflow.
- Both product-leading-bit choices and a possible rounding carry are safe.

This is deliberately sufficient, not necessary. Wider admission may inspect
P and the rounded exponent, but must have an independently proved boundary.
Do not admit merely because S fits eight bits, and do not use the whole
normal FP32 exponent range without accounting for both carries. Reject
zero, subnormal, NaN, infinity, and all uncertain exponent cases **before
fast-port issue**. They continue through the unchanged original FP32 MUL.
There is no post-issue replay, no double issue, and no discarded flag path.

The current scale fields contain exactly widened half values before their
MUL. Their low 13 fraction bits are zero, so the 11-bit significand can be
recovered without adding a second full operand copy. Admission must also
retain/prove FP16-source and FP32-activation provenance and the correct
scale state. Do not reinterpret the existing half-port's packed raw halves,
or a scale field already overwritten with a computed FP32 product.

### Integration And Cost Boundary

Add an independent II=1 scheduler for eligible `FP_SCALE_MULTIPLY` and
`FP_MIN_SCALE_MULTIPLY`; Q4's affine min scale is included when eligible.
Ineligible states remain eligible for the original arithmetic scheduler.
The old half-only route remains mutually exclusive. Preserve the existing
one-in-flight-per-entry rule and all FMA ordering. Normal conversion of
half inputs must not become an extra independently rounded arithmetic step.

A plausible minimum has a registered 35-bit product plus sign, signed
exponent sum, valid and slot tag; then registered normalization/RNE/result,
NX and tag. No LZC is needed for two normal inputs. Like the existing half
helper, it can be non-backpressured only if every valid return is guaranteed
to be accepted; otherwise add a correctly credited elastic return buffer.
Use sufficiently wide signed exponent arithmetic before comparing bounds.
Do not reset datapath bits unnecessarily; reset valids and include both
stages in busy. Two stages are an architectural proposal, not a frequency
promise; an extra register may be needed after timing work is authorized.

The 11x24 versus 24x24 multiplier suggests fewer partial products, but this
is not a total-area ratio: exponent/sign, RNE, status, scheduler, muxes, and
tag registers remain. Existing FMA and cast resources are not removed.
All nine accepted weight profiles remain valid: only eligible scale MULs
take the new route; every miss retains the old route and numerical contract.
The measured performance scope remains Q4_K/Q6_K, not all nine profiles.

Let h be the fraction of **dynamic scale MULs** admitted, counting d and dmin
separately. Q4's old arithmetic-port demand becomes `(4-2h)*U`, while fast
scale demand is `2h*U`; I2F and ordered FMA each still need 2U services.
A high fraction of tensor files, or unique scale words, is not this h.
MAIN owns the actual-model hit audit and independent golden implementation.
No hit rate or resulting speedup is assumed here.

Count each accepted scale micro-op exactly once in `fp_uop_issue_o`, whether
fast or fallback; the logical 6-uop Q4 and 3-uop Q6 sequences do not shrink.
Add route-specific scale issue/return/NX counters and extend busy/input-stall
probes to the new port. Do not report omitted fast-port events as less work.

## Candidate C: Lease Existing Lane FP Resources

### Why It Is Feasible, And What Is Not Already An Interface

`ara_dispatcher.sv` already holds VQBEXEC until terminal response, waits for
`ara_idle_i` before issue, and blocks subsequent instructions. Therefore
the accepted blocking command offers a useful **exclusive ownership epoch**:
ordinary RVV should not compete with QBS during that epoch. This is more
favorable than a general per-cycle shared-issue proposal. It is still
necessary to prove local drain and isolate every return path.

The route would be:

`VLSU/qbs_compute_engine/i_fp_accumulator -> ara -> selected lane
 -> vector_fus_stage/i_vmfpu -> raw fpnew input/output mux -> private return`.

There is no such sideband in those module interfaces today. No intermediate
VRF reads, architectural vector instructions, mfpu operand-queue entries,
or VRF result writes are needed or permitted for the borrowed scale work.
The existing final atomic QBS VRF commit remains unchanged.

At `vmfpu.fpu_gen.i_fpnew_bulk`, the actual request fields are three 64-bit
operands, `rnd_mode`, `op`, `op_mod`, `src_fmt`, `dst_fmt`, `int_fmt`,
`vectorial_op`, `simd_mask`, tag, valid/ready and flush. The return is a
64-bit result, five status bits, tag, valid/ready and busy. Set the QBS
request's mode to fixed RNE, `op=MUL`, FP32 source/destination, and avoid
the RVV sign/operand preprocessing. Do not inherit `vinsn_issue_q.fp_rm`.

The default 64-bit SIMD slice contains two FP32 arithmetic elements, not
four independent request ports. They share op/format/rounding, handshake,
and one returned tag. `fpnew_opgroup_fmt_slice.sv` returns lane_tags[0] and
ORs masked statuses. For the half/single/double configuration its four-bit
mask maps to FP32 element selectors 0 and 2; the VMFPU's source byte mask
must not be mistaken for two independent client-ready signals.

One scalar MUL/cycle, masking the unused FP32 element, is already sufficient
for the initial Q4 target. Two packed MULs/cycle require two *different*
eligible entries, two slot identities/valid bits in the private tag and
return handling for both results. Do not issue d and dmin concurrently for
one entry under the existing one-in-flight state machine. Aggregate status
is usable for command-sticky flags only when both elements belong to the
same command/epoch. Multiple lanes beyond this do not lower the original
dedicated FMA's 2U service floor.

### Required Ownership, Tag And Exception Changes

- Grant a latched command lease only after a local idle acknowledgment:
  instruction issue/process/commit queues empty, result queue empty, raw
  fpnew not busy, no pending reduction/SLDU token, and no prior private
  response. `ara_idle_i` is the architectural prerequisite, not a substitute
  for these explicit assertions. Latch the pre-issue idle qualification;
  do not wait for global Ara idle while QBS itself is already active, which
  can deadlock acquisition. Deny unsupported/disabled FP configurations.
- With the lease active, disable RVV issue to that FP port and route its
  ready only to the private request queue. Release only after every private
  request, fpnew operation and return queue has drained. No ordinary RVV
  instruction can be acknowledged as a side effect of a private handshake.
- Current synthesis `vfpu_tag_t` contains `operand_a`, `flag_mask`, and
  `control`; debug vid/op fields are simulation-only. It has no production
  QBS slot/epoch/owner. Use explicit opaque private tag fields, or a strictly
  exclusive-lease tag interpretation with proven retained fields. Do not
  rely on debug_id, a VRF vid, or spare operand_a bits: MAIN's optional
  `SharedFmaTagKeepMask` intentionally discards operand_a through ADDMUL.
- Demultiplex **raw** fpnew result/status before VMFPU postprocessing,
  processing-queue accounting, narrowing selectors and VRF result insertion.
  VMFPU assumes program-order processing and stalls opgroup transitions;
  its two-entry result queue is not a QBS completion ROB. Private results
  must not trigger `mfpu_vinsn_done`, mask/reduction feedback or VRF requests.
- Mask private returns from both `fflags_ex_valid` **and the flag data**.
  The dispatcher ORs lane flag data, not only valid-qualified data. Return
  private flags exclusively to QBS sticky status and its terminal response.
- Keep ordinary RVV format, mask, NaN-boxing, reductions, FRM and VSTART
  semantics unchanged. Bypassing VRF alone does not accomplish this.

Minimum registered boundaries are an elastic private request cut before
lane selection/FP input arbitration, and an elastic private return cut
before the central entry-table write. Credit return capacity when issuing;
do not create a combinational valid/ready loop across lane and VLSU. Lane
FP32 ADDMUL has four configured stages, versus two in QBS; routing cuts add
latency. With only 16 fixed stream slots, longer entry residence can defeat
an otherwise adequate issue rate. This needs measurement, not a latency-
insensitive claim. Multiple lanes add selection, return merge, tag storage
and simultaneous table writes, not just extra free multipliers.

### Fault, Clear And Flush

Both current QBS fpnew instances and the lane bulk FP instance tie flush
low. QBS uses `QBS_FAULT_DRAIN -> QBS_FAULT_CLEAR`, waits for integer and FP
busy to clear, and asserts that accumulator clear never overlaps live FP
work. Preserve this drain model. A command fault stops new command/tile
starts, but **already admitted entries still need their remaining MUL/FMA
micro-ops** to become empty. Gating every borrowed request with `!fault_i`
would strand those entries and deadlock fault drain.

Include request/response cuts and borrowed-unit outstanding work in QBS
busy. Drain into hidden accumulators, suppress architectural commit on fault,
then clear and release ownership. Never flush a shared unit to cancel QBS
while RVV results might still be resident. Reset is global; command clear
is not a lane reset. If a later design supports cancellation rather than
drain, it needs epoch-tagged poison handling and explicit return accounting;
changing the table tag alone is insufficient.

## Comparison And Minimum Next Decision

| Choice | Main incremental resources | Protocol blast radius | Stage recommendation |
| --- | --- | --- | --- |
| Full FP32 scale MUL | General FP32 MUL/round/exceptions, local scheduler/tag pipeline | QBS-local three-port completion | General reference; not necessarily smallest |
| Restricted FP16 x FP32 MUL | 11x24 product, one-bit normalization, RNE/NX, local scheduler/tag pipeline | QBS-local; miss uses original FPU | Preferred bounded component if dynamic hit coverage is strong |
| One lane, exclusive lease | Request/result cuts, owner/drain protocol, input mux, return/status isolation | VLSU, ara, lane, vector_fus_stage, vmfpu | Later PPA alternative, not current critical path |
| Multiple lanes | Above plus distribution/merge and more completion bandwidth | Broadest; entry lifetime still matters | Defer while dedicated FMA/cast bottlenecks remain |

Before any implementation, finish the model cost ledger and scale-hit audit.
The first authorized experimental component should prove exact admitted
mixed-scale results **and NX**, every conservative-boundary rejection, slot
lifetime, II=1 and reset-valid masking. Test both Q4 scale and min-scale;
include signed inputs, ties-even/odd, both product-leading-bit cases, possible
rounding carry, and zero/subnormal/nonfinite/exponent guard misses. Compare
against an independently implemented integer/rational oracle and the original
FP32 FPU. This document adds no oracle, fixture, or run.

A later integration decision must check simultaneous cast/scale/FMA returns,
fixed-slot pressure, faults at each pipeline boundary, fault-drain followed
by immediate new command, and exact accumulator/flags across all nine legal
profiles with fast paths enabled and disabled. For a lane lease, additionally
test RVV FP16/32/64, masks/tails/VSTART, mixed opgroups, ordered/unordered
reductions and SLDU drain immediately before and after QBS. Require zero
private VRF traffic and zero private lane-CSR flag publication.

Only after that is a focused, same-data Q4_K/Q6_K M4 experiment with the
joint dot/FP configuration useful. Observe actual arithmetic/cast/scale
handshakes by operation class, entry state/inflight occupancy and conflicts,
return credits, FP32 status, lane lease/idle/drain, final commit, and physical
R beats. Follow with the actual SDK complete-call measurement. Neither
service-floor arithmetic nor a component II=1 test is end-to-end acceptance.

## Source Identity And Freeze Boundary

MAIN QBS accumulator/half-scale/compute/dot sources match the frozen actual
SoC source tree at
`ara_dsa_signoff_integration/verification/out/e2e_physical_wide_soc_inputs_20261106_01/source`.
MAIN vmfpu/ara_pkg additionally contain default-off sharing experiments;
the frozen VMFPU directly instantiates fpnew_top, whereas MAIN uses
simd_fpnew with `EnableSharedFma=0` forwarding to original fpnew. That switch
is **lane-local format sharing**, not QBS/lane-client ownership. MAIN also
has an optional integer-multiplier experiment, outside this proposal.
Do not relabel either experiment as accepted sharing in the actual SoC.

| MAIN file | SHA256 |
| --- | --- |
| `hardware/src/vlsu/qbs/qbs_fp_accumulator.sv` | `13a400d7daa62779e6f829237365c4df7b31fbd4f2f6024491c1fb59468f4d60` |
| `hardware/src/vlsu/qbs/qbs_half_scale.sv` | `aa687023b3fe688ba3bd57d53dd98b63298ea9153dfb3da4b6ef059b279b25e8` |
| `hardware/src/vlsu/qbs/qbs_compute_engine.sv` | `f8cdc47107dd434743d30c0372f4dba029a91b2cfc7f931ca6c3e11b9203546a` |
| `hardware/src/vlsu/qbs/qbs_dot_array.sv` | `f0817108d4a20c619d5bfa6d61e9918f99d6d00df3561ee504ecd8d635c055d3` |
| `hardware/src/lane/vmfpu.sv` | `713daa47cdc7cf522068755694b40360eb34b983c6030336e889925a4f88665c` |
| `hardware/src/lane/simd_fpnew.sv` | `966fceecca758f6b297155c22b7d2ddebb78eef160f25ee235d494a5e1d860e7` |
| `hardware/include/ara_pkg.sv` | `8222c99643999b67c1ecc05855df6bee73bece38dfe1678e8ef86c8fc36eb05b` |
| `hardware/include/qbs_pkg.sv` | `5cba22278054776e56d74f01a4833f521729a16953a264fe959dbe8848c33a97` |
| `hardware/src/ara_dispatcher.sv` | `7bd7b46c87e2821e349d7c8938870ac79b2a77bf31eb3525fa07b904fc4eadf8` |
| `hardware/src/ara_sequencer.sv` | `fb652f96740aef941602fb546183dbe5e1f896f4a844b07b15d12d569eed36d1` |

Frozen VMFPU SHA256 is
`e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12`;
frozen ara_pkg is
`49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971`.
The fpnew mask/packing details above were checked in
`hardware/deps/fpnew/src/fpnew_opgroup_block.sv` and
`fpnew_opgroup_fmt_slice.sv`, both identical to the frozen counterparts.

Before this file was created, the six active Decode-partition/F16/RMS model
worker source-pin inventories were inspected; none consumed this new path.
Only this new document was written. All RTL, existing documents, helpers,
test benches, images and campaign receipts remain untouched. Implementation
must use separately owned experimental files/frozen build inputs, not edits
to these sealed baseline sources.
