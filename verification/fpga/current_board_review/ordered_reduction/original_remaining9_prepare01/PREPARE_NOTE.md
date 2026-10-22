# Preparation history

Initial software preparer exited before creating a manifest or per-shape artifacts:
`KeyError: pins`. The immutable inventory calls its hash map `fresh_sha256`.
Only that local lookup was corrected. No compiler, reference, or DUT had run.

This batch uses one shared checker, nine source-specific private software outputs.
Reference dispatch is sequential and stops on the first execution/checker failure.
Each reference has one attempt, 3M instructions, 256MiB raw per file, 120 seconds,
and the explicit `rv64gcv_zfh_zvfh_zvl1024b` profile.
Compilation and static admission must complete before any reference starts.

Independent static reviewer found before any new reference that the first checker
draft incorrectly classified Spike boot's `csrr mhartid` as a firmware CSR.
The successor preflight02 now validates exactly five boot instructions/effects;
the firmware CSR rule is unchanged. Preflight01 remains as historical Host-only
evidence without boot-prefix coverage. No reference was consumed for this fix.

Before any reference, independent review also caught unchanged-vtype logging:
capacity already sets e16/m1, so helper's first vset need not log vtype again.
Preflight03 inherits actual capacity CSR state and uses sparse-vtype positive
witnesses plus missing/corrupt-capacity-state negatives. Preflight02 retained.
The full nine references remain authorized once each; optional batch2 parallel
execution is conservatively implemented as sequential first-error-stop jobs1.
