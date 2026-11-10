# V6 Build Asset Variant

BUILD03 entered the explicitly selected internal dtc, then failed because
`subprojects/dtc/version_gen.h.in` was absent. The inherited 34,940-file
manifest and V5's 12 Meson-file comparison were not a build-asset closure.
Preserve BUILD01/02/03 and prepare03 unchanged.

This successor audits all string values in the eleven accepted old Meson
`intro-*.json` files (2,941 existing source references) and captures one
read-only `ninja -t query build.ninja` for regeneration metadata inputs.
Ninja 1.10.2 has no `-t inputs`; this is not a full Ninja dependency-graph
closure claim, nor proof that configuration/compilation will succeed.
The expected union has exactly one missing source file. Differences must
match the already reviewed prepare03 adapter overlay before/after hashes.

The template comes from a recorded `git archive` of dtc commit
`b6910bec11614980a21e46fbccc35934b671bd81`, never unchecked live bytes.
All 104 inherited dtc C/H hashes must match the commit archive. The template
must be exactly `#define DTC_VERSION "DTC @VCS_TAG@"` plus one LF.

`build_v6.py audit --output OUT/stage5_qemu_asset_audit_SUFFIX` captures
the immutable audit inputs, reference provenance, archive, and receipts.
After review, `prepare --output OUT/stage5_qemu_prepare_variant_SUFFIX
--audit AUDIT --reviewed-audit-sha256 SHA --reviewed-inputs-sha256 SHA`
copies prepare03's source and inputs, preserving symlinks, without hardlinks
or re-extraction. Exactly the template is added. Full tree membership,
bytes, symlink targets and distinct regular-file inodes are verified;
original prepared source and toolenv proofs remain required.

`build --output OUT/stage5_qemu_build_SUFFIX --prepared VARIANT
--reviewed-prepare-sha256 SHA --reviewed-inputs-sha256 SHA --service UNIT`
must be owned directly by the named systemd service. It changes only the
configure source path from V5: Python3.11, Ninja, internal FDT, disabled
downloads, minimal environment, 900s configure and 1800s `-j4` build remain.
No dependency probes repeat. `checked_build(directory, receipt_sha256)`
is the shared read-only admission API; V4/V5 or failed receipts cannot pass.
All four native execution gates remain required, with no RTL timing claim.
