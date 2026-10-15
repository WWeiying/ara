# Remaining Nine M6 Preparation

Prepare/Host only. No DUT launch, RTL/software build, reference rerun or live
query is authorized by this directory. Existing references and mf4 active plan02
remain immutable. One shared shape-configured checker/runner, not nine copies.

## Source And Oracle

Exactly e16 mf2/m1/m2/m4/m8 and e32 mf2/m2/m4/m8. Excludes e16/mf4 and e32/m1.
Uses the original SoC ELFs from `../original_remaining9_prepare01` unchanged,
accepted source/reference READY `ad59b118...` and independent REVIEW `4d9bc0f5...`,
result `73d0ab59...`. Actual runtime image is the existing candidate06 M6.
The plan binds full SHA256s, all source/reference pins, image/snapshot/config,
imported runner modules, and every ELF-derived shape specification.

Each actual ELF independently supplies PC/type/load-store encodings, capacity,
seven legal startup/C CSR sites, one contiguous3-instruction capacity window,
one contiguous21-instruction op0 window and complete forbidden op1/op2 PC ranges.
Every actual RVV retirement must belong to capacity or op0 exactly once. Interior
integer/CSR instructions outside the op0 window and late CSR/prelude repeats fail.
SoC startup is not Spike boot; the SoC CSV begins in actual firmware. No invented
five-instruction Spike ROM sequence is required of the DUT.

Full original8*cap source-word stores,512 seed-word stores,215040 mask-byte stores,
144 old-output stores and6720 ordered bank1 fixture-field reads are checked by
actual address/value, not only counts. Setup uses the selected entry snapshot.
e32 initializes256 seed bytes (helper loads m1/128); m8 inputs use up to1024 bytes.
Bank0 can share the expected NaN/NV, so bank identity uses actual load addresses.
The source21 encodings, full arguments, vset results, saved CSR values, requested
CSR writes, vstart0, returned NV16 and CSR restoration are checked. All144 scalar
LBU oracle reads include the2/4-byte canonical NaN and all unchanged0x5b tail/
guards. CSV has no direct vector-register payload claim. Its complete original
scalar oracle checks the architectural memory result of the full128-byte store.

Native source reference programs and all surrounding skipped loops are unchanged.
Nine single-call programs are not the original nine full6720-call Linux children.

## Budget And Execution Gates

- jobs3, each case5400s; no retries, noFSDB, no build.
- Direct systemd worker unit: `ara-redspecial-remaining9-original-m6-01.service`.
- Unit RuntimeMaxSec19800 (5h30m), KillModecontrol-group, Restartno.
- Worker cancellation deadline18900s; three5400s simulation waves leave2700s
  for validation and900s service teardown. New dispatch needs its unchanged
  5400s plus600s validation allowance before the worker deadline. Insufficient
  budget is NOT_RUN/ERROR and aborts dispatch; no timeout enlargement.
- First simulation, raw failure marker, artifact or strict-check failure sets
  one sticky abort, cancels active peers and prevents pending jobs from launching.
  Failed/cancelled rows and existing raw artifacts remain in runner summary.
- Terminal publication requires exact nine COMPLETE/PASS rows, no abort, full
  console/oracle/exit/CSV/privateELF/command/image checks, fresh disk plan SHA,
  fresh pinned inputs and image, plus atomic no-abort publication.
  Before publication the deadline Timer is cancelled and joined, and elapsed
  deadline is latched into abort; no live Timer can race the terminal decision.
- Actual resource admission occurs only in authorized run: cap24,32GiB available,
  count live simv once plus unused reservations. No stale fixed service roster.

Runtime cost is uncertain: actual reference firmware spans1,858,929..1,924,035;
the earlier~659 retired/s proxy implies~2820..2920s, while273 retired/s implies
~6810..7048s and exceeds5400. No guarantee of completion is claimed. The fixed
parent-selected budget is not enlarged based on these estimates.

Parent subsequently reported the actual mf4 VCS pilot terminal PASS/rc0 at
3470.2s. This worker did not query that run; its independent terminal audit is
still a launch prerequisite. Scaling only its1,858,335 reference instructions
to the remaining shapes gives roughly3471..3593s, a limited scalar-work proxy,
not a guarantee for different LMUL/vector behavior. Case5400s remains unchanged.

## MF4 Prerequisite

Preparation does NOT read or require completion of the active mf4 DUT. Launch
requires explicit `--mf4-acceptance FILE --mf4-acceptance-sha256 SHA` and a NEW
pinned parent authorization. No reference-only ACCEPTED status qualifies.
The proposed independent launch-proof schema is deliberately strict and absent
until the actual mf4 terminal audit exists:

```json
{
  "status": "INDEPENDENT_M6_ORIGINAL_E16_MF4_SINGLE144_ACCEPTED_NOT_FULL_PARENT",
  "plan_sha256": "51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c",
  "soc_elf_sha256": "eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162",
  "image_sha256": "ACTUAL_M6_IMAGE_JSON_SHA256",
  "complete_path": "ACTUAL_MF4_COMPLETE_JSON",
  "complete_sha256": "ACTUAL_TERMINAL_SHA256",
  "report_path": "ACTUAL_INDEPENDENT_REVIEW_MD",
  "report_sha256": "ACTUAL_REVIEW_SHA256",
  "audit_path": "ACTUAL_INDEPENDENT_RESULT_JSON",
  "audit_sha256": "ACTUAL_RESULT_SHA256",
  "audit_status": "INDEPENDENT_M6_ORIGINAL_E16_MF4_SINGLE144_ACCEPTED_NOT_FULL_PARENT",
  "evidence_pins": {"ACTUAL_REPORT_AUDIT_TERMINAL_AND_INPUT_EVIDENCE_PATHS": "SHA256"}
}
```

This is a contract/example, NOT an existing acceptance record. If the actual
independent report has a different schema, parent/reviewer must supply a separate
pinned adapter record linking the unchanged original report; never rewrite old
acceptance or accept broad PASS substrings. The bound independent JSON must
itself report the exact status, plan_sha256, complete_sha256 and image_sha256;
report, audit and terminal files must explicitly occur in evidence_pins.
The worker checks the actual mf4
complete status, exact plan/ELF/image identities, one real PASS result, noabort,
elapsed limit and all input/evidence hashes. Parent review separately binds this
acceptance SHA, new nine-case plan SHA, exact unit and budget risk decision.

## Host Scope

All nine positives use their actual source tables, accepted selected-entry raw
setup, compiled PCs/encodings and original geometric counts. They are synthetic
protocol transport witnesses, not DUT measurements. Both widths, fractional
and m8 shapes have full negative matrices. Additional negatives cover every
unused helper instruction, internal-window repeats, wrong SEW/PC, complete
artifact false-positive transport, raw partial DETAIL monitor, missing oracle,
drift, cancellation during validation, atomic publication, terminal membership,
direct service/budget and missing/wrong/reference-only mf4 prerequisites.

```sh
python3 -B test_host02.py
python3 -B replay.py prepare --authorize-prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0
```

Only prepare is authorized. Generated service command retains unresolved parent
review and mf4 acceptance placeholders; it must not be launched as preparation.

## Preserved Host History

Host01 remains `HOST_FAIL`: 17 methods,548 recorded checks, two expected-message
assertions failed because duplicate op0 entry was correctly rejected earlier
by `Duplicate RVV retirement`. All9 full shape positives and all data/control
negative matrices passed. Do not relabel Host01 PASS or overwrite its log.

Independent pre-seal review additionally found jobs/seed positional inversion
and a live Timer publication race not covered by Host01. `replay_before_host01.py`
is the exact old worker. Host02 binds its hash, unchanged checker and all Host01
evidence; corrects the two diagnostic expectations; verifies actual frozen
RunOptions jobs3/seed1 and its dry-run command (no process), reproduces the
old Timer/Event interleaving, verifies cancel/join and deadline latching, and
retests changed run/terminal/acceptance gates. Its AST check restricts runtime
changes to named options construction and Timer quiescence; only preparation
admission and the explicit independent mf4 report gate also change.
The full long matrix is inherited, not falsely described as rerun by Host02.
