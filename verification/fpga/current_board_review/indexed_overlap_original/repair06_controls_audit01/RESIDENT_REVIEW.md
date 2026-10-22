# M6 Resident Overlap Independent Case Acceptance

Verdict: **RESIDENT_FULL50_PLUS_MASKED_REFERENCE03_INDEPENDENTLY_ACCEPTED**.
Only `d32m2_i64_resident_ov1` is accepted. No active fault-control output,
process, or service status was queried; no whole-controls/whole3/service-exit
acceptance is implied. No DUT rerun or original/helper modification.

## Actual Case Completion And Exit

The completed frozen runner's actual record is service.log line2:
`[PASS   ] d32m2_i64_resident_ov1            1336.40s`.
Its exact resident-only extract is saved in `resident_runner_record.json`.
This is not a conclusion from the parent's observation that PID648445 vanished.

Simulator **rc0 follows from the verified frozen code path**, not a fabricated
numeric case JSON: runner.py rejects nonzero returncode before returning PASS;
the M6 worker calls artifacts() only for a PASS result and requires returncode0
before writing indexed_analysis.json. Its future returns only after the full
artifact checker and cancellation gate; only then does the runner print this
actual PASS line. Both frozen source identities are pinned. A standalone
numeric per-case rc JSON is not present yet, and stage/service completion was
not inspected. Elapsed1336.40s is within the unchanged2400s case budget.

Both raw logs contain exactly the full original resident oracle, simulator
SUCCESS(tohost0), and normal $finish, with no failure-veto marker. Input ELF,
source path, image ledger, actual command/debug argument and working directory
match the sealed M6 plan. Generic trace summary is VALID.

## Independent Full-Oracle Recompute

Frozen checker.analyze consumed the actual resident CSV and refs03 maps/disassembly
in19.54s. The newly retained recomputation equals the stored analysis structurally
and **byte-for-byte**, SHA:
`e71e11c4dd4910ed0287a7d0eda3f9a3532dc8d623d3847649bffde55b491673`.
CSV SHA: `400cd29c64fb06d64283780cbe2071038a456c106658be2f6d02b0556cffd688`.

- Original50 rounds plus complete extra masked/tail/vstart control:51 checkpoints.
- All32 outputs per checkpoint:1632 values; both guards:102 values.
- Actual firmware checks5215; accepted targets/successful retirements/reloads51 each.
- Faults/repairs/retries0; backing-memory/PTE scalar reads32768/1536.
- Architectural retirements834220; last CSV cycle1125905.
- Extra control retains VL17/vstart7, odd mask, original -7 sentinel outside
  the active positions7/9/11/13/15; all32 outputs, guards and CSR fields checked.

The checker verifies actual scalar loads/stores, complete prologue/setup,
original result-store ledger, missing-byte strictness, final counters and magic,
CTRL0 exit and only side-effect-free permitted parking afterward.
Actual ELF maps/disassembly and all41 authentic helper encodings were checked.

All737 plan pins match before and after; resident original artifact hashes are
unchanged. The combined748 static/evidence pins are in `resident_audit.json`.
Same SoC ELF: `85b1da567120fba1d04f2ec11ab6abc5d1898970c55550ed440b1ddc7cf276df`.
Authentic Linux ELF: `76ef2e1a73b1987729ba887a99108ad2fe61daeee36634d6e847448489941df5`.
The executed program is the Sv39 reference03 source fixture, not that Linux ELF
or its original kernel/context/minor-fault schedule.

Plan `d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8`;
image `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
Whole3 remains a separate later terminal review.
