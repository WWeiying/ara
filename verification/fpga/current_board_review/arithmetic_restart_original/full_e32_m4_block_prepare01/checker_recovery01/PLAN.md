# One Closed-Raw Checker Recovery

This successor is limited to the actual seed-path classification defect in `reference_entry02/lifecycle.py`. The original Spike rc0, audit rc1 and STOPPED remain immutable. No Spike/compile/DUT launch path exists here.

`lifecycle.py` inherits the sealed observer and replaces only the FP store classification set with the union of all three actual compiled seed paths. Membership does not authorize a write: the inherited code still matches the current `row.seed` event at the current cursor, including PC, address, size, value and A/B order. The three-seed geometry and disjointness from all original RNG store PCs are asserted.

FP loads do not have the faulty seed0 whitelist. They are classified by the actual 32-byte `fp_inputs` range, then matched against the current seed's first eight exact LW events, before any SW. The static receipt records all three actual load-PC sets. The new tests exercise each seed's eight loads and 256 stores, including full-width bank addresses and final b[127]. Missing same-value writes, wrong-seed PCs/paths, duplicates, wrong bank/width/value and missing first/last events remain rejected. Seed RNG writes are separately exercised and cannot be consumed as FP writes.

The parser, context/ELF validation and EOF boundary are byte-identical copies of entry02. Cache ownership, 65 actual LD, expected reads and tags, full original helper history, guards, mask and vstart requirements are unchanged. Positive synthetic setup tests use exact original ordinals1366/3361/5356, all op25/VL0. These isolated tests are not claimed as a second source-reference run.

After numeric focused Host success and Hilbert's exact-entry NO_BLOCKER, `recovery.py execute` runs one offline child, hard-limited to600s. An exclusive `closed01` directory and exclusive audit-start receipt prohibit automatic re-entry. The original raw SHA, actual reference receipt, original command/ELF, old failure receipts and all prior/new pins are checked before and after. Only a new recovery complete can accept the full5985/766080results/11970guards, with firmware-to-HTIF <=3M; cost overflow remains HOLD. All remaining raw rows must be exact pure park through EOF. No VCS acceptance follows from reference acceptance.

## Future DUT Reuse

Any future VCS adapter must derive FP classification from every actual SoC-ELF seed path, not copy this Spike PC set or seed0's sites. It must then match the currently owned call's seed-specific complete sequence. The fixed original source has1890 FP calls requiring15120 LW and483840 ordered SW, including VL0 calls and repeated identical values. A source value already present in memory never substitutes for a fresh event. This recovery prepares no VCS adapter and grants no DUT launch.

## Commands

Preparation: `python -B recovery.py prepare`.

Following exact independent review: `python -B recovery.py execute --review ABSOLUTE_JSON --review-sha EXACT_SHA`.

Review schema is frozen in `entry.json`; existing raw is never regenerated or modified.
