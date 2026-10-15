# Final Eight-Job Entry Review

**NO_BLOCKER** for plan `165c12dfee46c794...`. Use `entry01.json` and its
actual SHA in the existing README authorization fields. Averroes may launch
under the user's existing authorization; no additional approval is requested.

- Exact14 source members, runtime/source-name separation, immutable SoC ELF
  identities and specs match the accepted READY. Plan1271 pins include all
  original1253 software pins. Source700-byte comparisons and references were
  not repeated. Existing worker Host34 has actual wait0; dryrun lists all14.
- `checker.strict_csv` uses the pinned `abi_check.Checker` directly, calls
  `row` for every CSV row and `finish` at EOF. This is the reviewed analyze
  path with additional constructor/terminal failure diagnostics, not a
  fallback to the earlier ABI-incomplete checker. Exact source PASS and four
  completed owners are required. Generic `validate_trace` runs separately;
  row/retirement/last-cycle extents must agree. No console-only acceptance.
- Eight jobs,1800s/case,6900s worker deadline,7200s service hard limit and
  reserved0 are pinned. Every dispatch checks sticky abort and remaining
  budget. Failure cancels affected work without retry or budget increase.
  First-error serialization preserves the original cause. Actual numeric
  monitor/child outcomes are persisted before postchecking; malformed or
  raw-failing outputs cannot be promoted by a PASS marker. Terminal gates
  retain fresh-plan/full-pin and no-abort checks.
- The prepared service command launches the direct Python worker with
  KillMode=control-group, Restart=no, and the pinned ExecStopPost hook.
  That hook exclusively records real systemd exit fields; successful exit
  is not fabricated from an absent process or collected unit.

Static/metadata entry verification exited0 (chunk54ba56,0.704548764s).
Reviewed current worker/checker/hook/import pins and exact plan/Host/dryrun
bindings; did not rerun Host, parse raw CSV/reference, query live services,
launch DUT or modify sealed files. Actual resource and service-owner checks
remain the launcher's responsibility. This signs entry, not DUT acceptance.
