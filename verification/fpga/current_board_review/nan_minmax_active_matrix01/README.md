# Active NaN Min/Max Matrix

This is new directed module coverage, not an archived program replay or a
whole-SoC/VRF/CSR acceptance claim. Only this directory is owned/modified.
Production RTL and the previous tests remain untouched.

## Independent Oracle

The [RVV 1.0 min/max reduction rules](https://raw.githubusercontent.com/riscvarchive/riscv-v-spec/v1.0/v-spec.adoc)
require exact seed copying and no new exceptions for an empty active set.
The [scalar FMIN/FMAX rules](https://raw.githubusercontent.com/riscv/riscv-isa-manual/main/src/unpriv/f-st-ext.adoc)
require canonical NaN for two NaN operands and NV for a signaling NaN.
Consequently an active all-NaN reduction produces canonical qNaN, with NV
iff its seed or any selected source is signaling. This is identical for min
and max and does not depend on tree order. Masked sources cannot add flags.

`run.py:oracle` classifies IEEE bit patterns without calling RTL, using FPnew
results, or using a floating-point reduction implementation as the golden.
Canonical results are 7e00/7fc00000/7ff8000000000000 for FP16/32/64.
Seeds are negative noncanonical qNaN or sNaN with payload55; source payloads
vary with element index and alternate signs. No finite source is hidden in
the all-NaN profiles. Exact output bits and all five flags are checked.

## Fixed Scope

42 cases per topology, 4 lanes then 1 lane, 84 total. Each profile has min
and max at FP16/32/64, VL35, vstart0, initially clear flags:

| Profile | Active set | Seed / source | Expected |
| --- | --- | --- | --- |
| qq_remote | only element33 | qNaN / all qNaN | canonical qNaN, flags0 |
| qq_all | unmasked all35 | qNaN / all qNaN | canonical qNaN, flags0 |
| alloff_q | empty | qNaN / mixed qNaN,sNaN | exact seed, flags0 |
| alloff_s | empty | sNaN / mixed qNaN,sNaN | exact seed, flags0 |
| mixed_remote | only element33 | qNaN / sNaN at33, otherwise qNaN | canonical qNaN, NV16 |
| mixed_all | unmasked all35 | qNaN / alternating qNaN,sNaN | canonical qNaN, NV16 |
| seed_snan_remote | only element33 | sNaN / all qNaN | canonical qNaN, NV16 |

The first24 cases prioritize all-qNaN and exact all-off payload controls.
Element33 is lane1 in the four-lane topology, beyond the first source packet
at every tested EEW. Deterministic source gaps retain the existing TB's
seven-cycle feed cadence. Consecutive cases run without reset after case0.

## Real RTL And Adaptation

Base: `/home/wangwy/fpga_runs/reduction_epoch_unit_20261010/preserve80`.
The new runner rehashes the base pins and requires each hardware source to
match current RTL before freezing it. Required current VMFPU SHA:
`e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12`.

Real `operand_queue`, VMFPU and FPnew instances are retained. The public
operand/predicate inputs and buffered SLDU tree are modeled; no force,
internal injection, alternate RTL, or internal replacement is used.
The inherited four-lane buffered rotation is parameterized to
`log2(N)+1` rounds, matching the previously tested epoch bench's rotation
for N=1/4. Flag OR and token counts are likewise topology-dependent.
These fixture changes do not change result or flag expectations.

Existing checks retain exactly one result write at the expected lane,
address, instruction ID and SEW byte enables, complete input consumption,
one request/done per lane, matched FP input/output counts, and one timely
deferred flag pulse per lane. Only enabled SEW result bits are architectural;
the complete64-bit result and BE remain in the probe.

`trace.csv` retains accepted arithmetic, source progress, mask, raw/collapsed
flags, tree and done timing. `probe.csv` adds actual `ntr_val`, captured seed,
local/global/epoch activity, public queue input/output and handshake values,
and final result write data/BE. These are observations, never golden inputs.

## Execution Policy

One campaign at `run01`, no overwrite or retry. VCS compile timeout300s and
simulation timeout120s per topology. Architectural first mismatch is fatal
after flushing evidence; any compile/harness failure also stops the campaign.
The second topology is not launched if the first fails. No full-SoC build,
Verilator, ZCC, or URG is used. Terminal status/results, commands and pinned
source identities are retained under `run01`; see REPORT.md for measurement.
