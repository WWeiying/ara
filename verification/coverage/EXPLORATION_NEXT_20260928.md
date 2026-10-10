# Coverage-first follow-up

## Policy

The user requested coverage expansion before further bug repair. Freeze RTL
after the already-applied empty-segment reservation change. The existing
51-case repair gate retains its original immutable plan; do not edit its
running scripts or silently change its verdict policy. A separate follow-up
campaign uses the same instrumented image and independent result directories.

Ordinary mismatches and bounded timeouts are recorded with ELF, image,
configuration and first-failure evidence; independent tests continue. Stop
only for provenance drift, unreliable checking, or systemic tool failures.
Do not change RTL, relax checkers, increase every timeout, or waive reachable
logic to improve reported percentages.

## Targets

1. Operand queue conversion and dependency combinations: legal SEW/LMUL,
   mask, tail, widening/narrowing and producer-consumer chains. Check resulting
   architectural values against an independent reference.
2. Dispatcher configuration boundaries: VL=0/1, tail VL, vstart boundary,
   configuration changes and legal register grouping. Avoid simply repeating
   the 12 already-triaged indexed-segment stalls.
3. Use latest DVE hierarchy to choose subsequent QBS/AKV and short system
   cases. Do not substitute a long Linux boot for targeted coverage tests.

## Scheduling and reporting

Use at most eight concurrent simulations across the existing repair and
follow-up queues. Compile once, then reuse the frozen VCS image. Generate and
precheck additional stimuli while the current queue executes. Long-running
queues are independent background services, not continuously polled sessions.

Publish passed, failed, timed-out and not-run counts separately. Verified DVE
coverage admits only independently checked PASS tests from compatible builds.
Any exploration coverage including failing execution must be separately
labeled. The pre-repair 473-PASS report remains historical evidence, not
coverage for the modified RTL. Track per-module coverage deltas as well as
top-level line, condition, branch, FSM and toggle percentages.
