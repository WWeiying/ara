# Independent M6 Prefix98 Plan02 Admission Review

Date: 2026-10-11. Read-only review of sibling
`e16_m8_ops1_prefix98_vcs_m6_plan02/prepared01`. Only this separate report was
written. No preparation, compilation, Host/Spike suite rerun, DUT launch, resource
admission attempt, or sealed-file edit was performed.

## Decision

**Approved for the parent's bounded jobs1 launch, subject to the worker's live
resource and service-identity gates. No remaining launch blocker found.**
The plan01 first-emitted-error veto defect is corrected without changing source,
ELF, expected results, full98 acceptance, image, or runtime bounds. This does not
assert startup, service exit, DUT PASS, or full historical-child/Linux closure.

Approved plan SHA256:
`e4476bec15fadab91251915d44bc156e24c9191abd0aea0359a32d372336f5c2`.

## Actual Successor Differences

Compared actual files against rejected plan01:

- `checker.py`: only adds explicit `\bRVV_PERMUTE_DETAIL\b` to VETO.
- `replay.py`: only changes service suffix `m6-01` to `m6-02` and required Host
  test count23 to24.
- `test_host.py`: adds one test using the exact existing Host active-error line,
  both truncated before `expected=` and complete, without newline or final FAIL.
  It checks VETO directly, standalone console rejection, and rejection after an
  otherwise successful console.
- `reference_audit.py` and `reference_audit02.json` are byte-identical copies.
  README and Host report describe the successor rather than rewriting old results.

The actual detail line is:

```text
RVV_PERMUTE_DETAIL op=1 seed=0 scalar=0 vl=1 mask=0 element=0 vstart=0 expected=61881 actual=61880
```

Independent read-only evaluation against this retained evidence confirms that
both forms match the new VETO and raise its raw-failure rejection in console_gate.
Neither contains a final FAIL marker. The wrapper adds that same VETO to the
frozen runner's streaming FAIL_RE before launching. The runner scans new console
bytes with a256-character carry buffer every0.1s and stops its child process group
on a match, exception, cancellation or timeout. Detection no longer waits for the
original C's final prefix FAIL after an emitted element mismatch.

This is first-emitted-error cancellation. The unchanged original C does not emit
an immediate detail for a guard-only or returned-CSR-only error; those remain
detectable by final FAIL and strict full-trace acceptance, not a newly added
per-element live CSV monitor.

## Pins And Recorded Host Evidence

Independently rehashed all708 plan02 pins and all708 plan01 pins: all match.
All common pin paths retain the same hashes; exactly seven plan-local paths move
from plan01 to plan02. The original plan SHA remains
`55e99bd7056dbfaaf6e1e5a71c1df55ddea66fddf68041071b8e2cf27d27dbd0`.
All plan fields other than pins, resource snapshot and service name are identical.
Ready.json names the exact approved plan SHA and records708 pins/not started.
At review, the output directory contains only plan.json and ready.json.

| Plan02 artifact | SHA256 |
| --- | --- |
| checker.py | `4b6c426a5938d597eb2b0fa01954a427d196fb991834055731ca8804b0e6b8cd` |
| replay.py | `4c1a1e04805039c70482e3e0fb93c4565709fc72a6a98f07c881cd8ba61174d7` |
| test_host.py | `84aac0ec2e557d1b8ec2851fd88af5b4a01ecc716d86b041e67933388460603e` |
| host01.json | `6ed452b8a2593c3ad593f7a4046111c856fd8e1bd102b7e4ede2fd8ece0f6c6c` |
| reference_audit02.json | `ef0ea23876a3d7c5515ece322138ece83f1dc4bf130b656e54db0304a044c922` |
| prepared01/ready.json | `01c18ffcfdbfff4ac637101178c98fbefd3821682553398b6d2e20dc94cb1ba5` |

The pinned Host report records24 tests PASS, zero failures/errors,28.488s, and the
matching test-script hash. This review inspected that evidence and the new test;
it did not rerun or overwrite the Host suite.

## Unchanged Acceptance And Isolation

The [reference preparation audit](REVIEW.md) still applies: natural calls1..98,
all97 predecessors, original RNG/setup, original13 helper instructions,512 values
per call, both guards and original vstart oracle. The strict CSV checker retains
50,176 element checks,196 guards,2178 setup values/call, actual call arguments,
three vset results/call, returned vstart0, original CTRL exit0, and restrictions on
any observed post-exit retirements. Generic frozen-image trace validation remains
additional, not a replacement for the scalar oracle.

Both raw logs must have the exact98/error0 and case/simulator success markers;
the added detail veto applies even after PASS. Private ELF hash, source path,
command/cwd, image identity, trace validity, runner COMPLETE/PASS1, exact summary,
returncode0, elapsed<=9000 and unchanged pins are required. Validation exceptions
and late cancellation latch abort; final publication checks pending signals.

The identical SoC ELF is SHA256
`161f41852ebbe6d7d9a0574691c39435dec3229b1017b20462e6211fb82fe74d`.
Frozen M6 image.json SHA is
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`;
snapshot SHA is
`3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.
The pinned dispatcher remains Repair06 SHA
`c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d`.

The command uses the existing frozen M6 simv, private input.elf/work/CSV, seed1,
NO_FSDB, no coverage/UCLI, and no build or retry. Jobs1 is independent of the
indexed pilot's private directory. Shared immutable executable use does not
require another image or serialize these two tests.

Service is `ara-gather-e16m8-prefix98-m6-02.service`, RuntimeMaxSec10200,
KillMode=control-group, Restart=no, with append logs. Worker verifies its exact
MainPID/cgroup and these service properties through the trusted UID bus. The case
bound is9000s; the outer bound is10200s (2h50m), both below3h. Resource admission
rechecks total live plus unused reservations plus jobs1 <=24 and available memory
>=32GiB. `reserved_slots=0` means no unused reservations: an already-live indexed
pilot is counted through actual process inventory, not reserved again. This
review did not claim a fresh live capacity check or launch either service.

Natural trial98 remains VL512/start256/scalar0/all-on; its relationship to the
historical exact stalled tuple is unknown. Full2688 child and Linux closure remain
open. Service exit provenance must still be collected after actual termination.
