# V8 Full Dtc Tracked Closure

BUILD04 failed on `libfdt/version.lds`. The earlier 3,119 Meson references
and regeneration metadata did not include this unconditional `link_depends`
asset, so they were not a complete build-asset closure. Preserve BUILD04,
variant01, all V7 sources and both failed census audits unchanged.

The existing dtc archive, SHA-256
`1fb660c56f7c255b930f9763f58e0b3f3c59d1815fa11bc5cb01d01823540ba4`,
is bound to commit `b6910bec11614980a21e46fbccc35934b671bd81` by exact
`git ls-tree -rz` membership, every Git blob ID and executable mode. All 310
tracked files are regular. Variant01 has 116 byte-identical files and is
missing 194. Restore all 194, including eleven executable files, irrespective
of conditional target selection. No C/H bytes or existing dtc files change.
The pinned `.meson-subproject-wrap-hash.txt` remains the sole nontracked file.
Existing setup.py's mode 0660 is preserved rather than Git's 0755; Python is
disabled by the unchanged QEMU subproject options, and this is not a claim
of accepting standalone dtc Python packaging.

Host01 stopped in initialization: the first audit incorrectly equated Git's
0644/0755 with archive 0664/0775. All 310 blob IDs and execute bits matched;
the difference is the archive group-write bit. Its failed receipt and source
snapshot remain. The successor records both modes, accepts only the canonical
mode or that mode plus group-write, and creates added files with Git's exact
0644/0755 mode. Other permission changes and execute-bit drift remain rejected.

All four Meson files are recorded verbatim in the asset manifest. Review covers
`vcs_tag` input version_gen.h.in; libfdt files/headers, version-script link_args
and link_depends; tool lexer/parser generator inputs; Python libfdt.i/setup.py;
and test assembly, scripts and data. There are no configure_file calls in this
fixed dtc revision. Whole tracked membership, not selected introspection paths,
is the asset boundary. No claim is made about an entire QEMU Ninja graph.

Separately authorized API repair: the new copy's `hw/riscv/ara_stage4.c`
changes only `CharBackend console;` to `CharFrontend console;`. Its original
hash, resulting hash and exact patch are separate artifacts and receipt fields.
James's finite API review found no second definite C/API issue. The frozen
original helper, original03 and variant01 remain untouched. This repair is not
attributed to dtc and changes neither instruction arithmetic nor admission.

`build_v8.py prepare --output OUT/stage5_qemu_prepare_variant_SUFFIX
--reviewed-inputs-sha256 SHA` copies variant01 without hardlinks, skips only
the proved empty Meson lock, restores tracked assets and applies the one repair.
All inherited files, symlinks, directories and added executable modes are
checked before/after; the parent and original source proofs are retained.
The receipt separately records the asset manifest and adapter repair.

`build_v8.py build --output OUT/stage5_qemu_build_SUFFIX --prepared VARIANT
--reviewed-prepare-sha256 SHA --reviewed-inputs-sha256 SHA --service UNIT`
retains Python3.11, offline/internal FDT, the minimal environment, configure900s,
Ninja1800s/-j4 and direct MainPID checks. Preparation is bounded to 900s.
Parent authorized one direct user-systemd build05: Type=exec, MemoryMax=8G,
RuntimeMaxSec=3000. No guest launch. Shared `checked_build(directory, SHA)`
requires schema V8 and its full OWN closure, parent/variant proofs, exact
post-build empty lock, command receipts and binary hash. Four execution gates
remain required before any architectural acceptance; no RTL timing claim.
