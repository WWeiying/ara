# M6 e16/m8/op1 Natural Prefix98

Prepare only. No simulator, compiler, build, waveform capture or service is launched
by preparation. Parent authorization and the exact plan SHA are required for run.
The reference directory, its ELF, original source and failed local audit01 are
unchanged. `reference_audit02.json` rechecks the raw reference and correctly accepts
the negative fixture's EOF rejection; it does not turn the old audit01 into PASS.

## Scope

- Identical reference SoC ELF SHA256:
  `161f41852ebbe6d7d9a0574691c39435dec3229b1017b20462e6211fb82fe74d`.
- Authentic original child e16/m8/ops1, natural calls1..98, endpoint
  `[seed0,op1,scalar-index0,length-index6,mask-mode0,trial1]`.
- All initialization/RNG, 13 original asm instructions per call, actual scalar
  argument/VL/vstart, three vsetvli returns and returned vstart0 are mandatory.
- Strict CSV analyzer checks 2178 initialized values per call, 50176 full-capacity
  halfword results and 196 guards, plus original CTRL exit0 and parking instruction.
  Generic frozen-image trace validator independently checks CVX/retirement/uops.
- Both raw logs require the exact98 full oracle, case marker and simulator exit0;
  errors after PASS veto acceptance. No agnostic or prestart oracle is discarded.
- A natural prefix is not the original2688-call child, not exact historical stall
  reproduction (old stopped tuple unknown), and not closure of the other10 stalls.

## Bounds And Ownership

The reference retired 2002820 instructions. At the conservative historical rate
273 retired/s the estimate is 7336.34s. The single case stays fixed at9000s with
no retry or timeout adaptation; direct service RuntimeMaxSec10200 leaves20min
for validation/teardown and remains below3h. This is a budget estimate, not M6
performance evidence. Jobs1; cap24 and available memory32GiB are checked again
at admission. `reserved-slots` counts unused external reservations only.

`replay.py prepare` verifies the actual M6 image, source manifest, settings,
snapshot, transitive helpers, reference/source/input pins and host gates. It emits
`prepared01/plan.json` and `ready.json`, containing the exact explicit service
command. This command is for the parent to launch only after review. The worker
must itself be the expected service MainPID in the exact cgroup, with no restart
and control-group teardown. User-manager queries use the explicit trusted UID bus.

The frozen runner creates a private ELF per test and full commit CSV, seed1,
`+NO_FSDB`, no coverage, no UCLI. Initial full-prefix replay has no waveform dump.
If a real issue occurs, a separate approved late bounded profile may be prepared;
the runner does not silently rerun or change trials.

Abort is sticky through expensive checks. COMPLETE/PASS1, exact summary, private
ELF/command/image identity, elapsed<=9000 and unchanged pins are required before
the signal-blocked final decision. Evidence hashes include raw CSV/logs/private
input/command and run/summary/strict analysis. Service exit provenance remains a
separate post-terminal observation; the worker does not invent its own exit facts.

## Host Verification

`test_host.py` uses an explicitly synthetic98-call protocol fixture only to test
the checker and generic validator. It is not a source program or DUT acceptance.
Negatives cover missing setup/RNG/arguments/instruction/CSR, result/guard/missing
oracle/truncation/exit/park, raw veto/markers, ELF/image pin drift, cancellation
during actual validation, checker exceptions, COMPLETE/abort, pending signal,
capacity and sanitized user-bus query. The real source reference is separately
bound in `reference_audit02.json`; no Spike or VCS rerun is part of these tests.
