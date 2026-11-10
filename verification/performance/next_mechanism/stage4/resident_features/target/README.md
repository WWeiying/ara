# Stage4 B Target Oracle Checkpoint

New successors only. B5 is frozen at `f50092f2d22238c6be4b6c159a1ad71a4ea68678`;
no production source, parent document, sealed helper or dirty assembly is edited.

`prepare.py --output OUT/stage4_resident_features_target_YYYYMMDD_NN` archives
that SDK revision, checks the accepted Qwen3 capture identities, derives ordered
QK scores, probes GNU-newlib tanhf, derives maxima/alpha inputs, then probes
GNU-newlib expf. Both Spike invocations are bounded to15s/300000 instructions;
there is no VCS launch. The same pinned target libm must be linked into the later
firmware. `probe.c` clears FCSR for each call (including expf(0)), uses early
clobber for flags read before CSR restore, and checks restored FCSR every time.
The receipt retains ELF, input sets, raw commit traces, tool/library identities,
actual scalar-transform comparisons and host checker tests.

The oracle reuses only ordered arithmetic primitives from the sealed Stage3
flags-v2 fixture. Its host-libm constructor/expf method is never called. All
target samples are exact-set checked; missing, extra, duplicate or malformed
samples fail. Floating-point arithmetic uses SoftFloat/RNE; F64 reduction to
F32 has an explicit rounding/flag bound. Do not substitute the mathematical
F32 reference for bit predictions. The C order is mask early return, scale,
window early return, softcap, position bias, additive mask. QK/PV still execute
excluded positions. Sinks initialize maximum/sum as sink/1.

## Frozen Consumer Interface (At Successful Preparation)

- `oracle.json`: integer-bit expected outputs, flags, maxima and QK/PV_PREP/PV
  phase flags by case. `case.mask_override` is a list of `[token,bits]`, not
  JSON integer-key dictionaries. Query F32-to-F16 conversion is independently
  checked against captured F16 bytes but its flags are excluded: prepare the
  identical F16 bytes outside both ROIs. Initial FFLAGS cases are0 and sticky
  DZ8, never preseed NV/NX to hide missing flags.
- `target-libm.json`: exact function/input/output/FFLAGS samples and bounded
  probe identities. Probe result words come from actual target memory commits,
  not host glibc or newlib source emulation.
- `build-contract.json`: required entry, macros, ABBA order, environment,
  wrapper and pinned source identity. Both arms use the new features-v2 entry,
  requested0/1, automatic0. `AKV_PAIR_HEADS=1` alone is not the strong baseline:
  link accepted `rotation/pv_rotation.S` with
  `--wrap=akv_experimental_pv_f16_pair`, set `resident_pv_rotation_selected=1`,
  prove final ELF binding and retired PCs inside the rotation body (past its
  selection branch). Candidate must bypass it. Include normalization stores
  and vector drain/fence in ROI. Expected real-case command counts are237/4
  legacy commands for A/B and6 resident commands for B.
- `source-pins.json`, `commands.json`, `result.json`: complete provenance and
  explicit scope. Firmware build/whole-call numerical checks remain pending
  when state is `ORACLE_PROBES_PASS_FIRMWARE_PENDING`.

## Finite Cases And Remaining Target Work

Performance keeps real Qwen3 D128/H2/T137/cap256 Q/K/V/masks/scale. Only feature
controls are derived: keybase4096, query4232, window100/0, slopes1/128 and1/64,
sinks-2/-1, softcap0. Preparation rejects an all-zero alpha-input case.

Functional fixtures are explicitly derived, not additional captures: D64/T5
softcap2 and additive masks; fully excluded T1 with/without sinks; T65 excluded
first tile then included tail, and included first tile then excluded tail,
each with/without sinks; two local H3 groups repeating captured Q/K/V with
distinct local features. `query_rows` indexes the original two captured rows;
K/V repeat the original single KV head. H3 maps bases0/H2,2/H1 then resets0
for the second group. No PV skip is permitted on excluded tiles.

Delegate actual SDK firmware/build and SoC checker/runner to the firmware owner
against this interface. Require requestedOFF/ON numerical pairs for the finite
functional cases, clean/sticky-DZ checks, and a non-RNE fallback pair (actual
FRM1, optionsFRM0) matching requestedOFF at the same FRM with no resident work.
That fallback pair is not compared to an RNE golden. Host06 already closes
VSTART rejection and is not rerun. No model/performance/default-promotion claim
is made by scalar probes or this oracle checkpoint.
