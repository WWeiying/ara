# ADDMUL tag-compaction acceptance evidence

Source root:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared_fma_tagpack_acceptance_20261105_02`

Accepted source commit: `34a2b97dc4fe3a72cfef99f3546e672ad8c1a4b9`.
This directory copies selected original reports without changing their contents.
Relative paths below match the source root; `source-pins.json` retains the original
absolute input identities, including inherited prior-run inputs. Do not rewrite
these paths or describe subsequent live-source drift as an original-run failure.

Before this documentation-only archive commit, all 4818 input pin hashes matched
their source files. All 18 copied artifacts were checked byte-for-byte against
the source root. Raw report whitespace is retained intentionally.

- `status.json`: completed measurement, not full physical signoff.
- `soc/status.json`, `soc/report.json`, `soc/plan.json`: 39 paired programs,
  78 runs, PASS, old/new completion and microkernel records.
- `ppa/report.json`: baseline 32175.023623 um2, candidate 31341.743648 um2,
  incremental reduction 2.589834850670747 percent.
- `ppa/manifest.json`, `ppa/library-pins.json`: synthesis provenance.
- `ppa/{baseline,shared}/`: raw area, QOR, clock setup paths, timing checks,
  and resolved library identities. Preserve COMBO/hold violations and warnings.

Large DDCs, simulation binaries, logs, and frozen sources remain in the original
run directory. Earlier failed runs remain there under their original names;
this package does not replace those records or claim they passed.

See `hardware/docs/AREA_OPTIMIZATION_VERSION_20261105.md` for activation defaults,
verification scope, historical SoC estimates, and remaining acceptance work.
