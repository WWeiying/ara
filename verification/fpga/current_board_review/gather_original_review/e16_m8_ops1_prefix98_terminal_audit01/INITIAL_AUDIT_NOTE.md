# Initial Offline Invocation And Finalization

The first offline invocation recomputed the complete raw CSV through the frozen
generic and strict analyzers, saved `recomputed_strict_prefix.json`, and passed
its complete equality comparison against the original strict report and all
98-call/count/tuple assertions. It then failed at the final original-evidence
hash recheck: the imported Gather `sha` expects Path, while evidence keys are
strings. Error: `AttributeError: 'str' object has no attribute 'read_bytes'`.
No independent terminal acceptance was published by that invocation.

The owned auditor normalizes hash inputs to Path. Explicit `--finalize-existing`
reuses the preserved independent recomputation with exact SHA
`9e276ae7bda91801fd2f201bb3739e35f78f02da54491bcf4be2f7d6d3b59066`,
requires its CSV hash still match the original CSV, rechecks all immutable
inputs, source/ELF evidence, original terminal/evidence hashes and comparison,
then publishes only this owned audit. The first recompute elapsed duration was
not persisted; finalization reports null rather than inventing it.

No original report was overwritten, no sealed checker was changed, and no DUT
or Spike was rerun. This is an owned audit-wrapper type error, not a DUT failure.
