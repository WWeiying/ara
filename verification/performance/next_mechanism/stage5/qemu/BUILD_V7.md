# V7 Exact Generated Lock Policy

Preserve V6, host01 (11 PASS), audit01 (FAIL), original prepare03 and BUILD03.
V6 audit failed before Ninja/git because BUILD03's Meson created one empty
`subprojects/.wraplock` in prepare03. Independent review verified all 78,470
pins and all original tree entries: 78,395 regular files, 72 symlinks and
6,309 directories. The lock creation was inside BUILD03's configure window.
Meson `wrap.py:589` acquires it; `utils/posix.py:20` opens with `w+`, and
exit unlocks/closes without unlinking it.

V7 validates the original complete inventory plus exactly this empty regular
file (SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855).
No wildcard ignores or original-tree removal. The frozen original inventory
itself is also hash-bound. The copy skips only the source-root
`subprojects/.wraplock`, preserves symlinks, uses no hardlinks and adds only
the fixed-commit dtc template documented in BUILD_V6.md. Preparation requires
no lock in the new variant. Post-build validation requires exactly the empty
lock that Meson regenerates; every other source/input entry remains exact.
Original and variant generated metadata are recorded separately from source
pins, including build before/after metadata. No source flags or models change.

Commands use build_v7.py with V6's audit/prepare/build CLI. Audit (240s) uses
all eleven Meson introspection files and one read-only Ninja regeneration query;
it is not a full Ninja graph closure. Prepare (600s) only copies prepare03.
The V5 configure flags, minimal environment, Python3.11, internal FDT,
900s configure, 1800s Ninja -j4 and direct service owner checks are unchanged.
No toolenv probes repeat. Parent starts the build after source/variant review.

The shared admission API remains `checked_build(directory, receipt_sha256)`.
`report.prepared` is the new variant; `original_prepare_sha256` binds prepare03.
`checked_variant(path, sha, after_build=True)` admits the exact post-build
metadata state. Consumers must bind V7's OWN closure and schema, not patch
older validators. No guest launches and no native or RTL acceptance here.

## Census Correction

Preserved host01/audit02 used an unjustified 2,941 equality check. The old
three V7 files and their hashes are archived in OUT's
`stage5_qemu_census_review_20261110_01`, alongside the exact path ledger.
The actual collector yields 3,119 unique normalized source files: 3,111
identical, seven reviewed overlays and only the missing dtc template.
The strict source-prefix collection has 2,868 files; normalization includes
251 further test inputs via `build/../source` and canonicalizes two script
spellings without changing their count. No original 2,941 ledger is known.
Producer and consumer now check counts against the unique, pinned ledger
rather than that unexplained constant. Host coverage reconstructs all 3,119
paths and rejects dropped entries, duplicates and missing-set mutations.
All file hashes, archive checks and the sole-missing-template rule remain.
