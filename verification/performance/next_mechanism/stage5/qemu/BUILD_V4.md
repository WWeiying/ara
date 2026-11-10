# Build-Only V4

Reuses accepted prepare03; no extraction or changes to its nineteen helpers or
source tree. Build01's Python 3.9 TOML failure remains a failed attempt.

Only configure additions: `--python=/usr/bin/python3.11` and
`--ninja=/usr/bin/ninja`. Minimal environment adds explicit `PKG_CONFIG` and
`PKG_CONFIG_LIBDIR=/usr/lib64/pkgconfig:/usr/share/pkgconfig`; no ambient path,
Python package, compiler flag or dynamic loader injection is inherited.

One offline host preflight runs QEMU's actual mkvenv/create/ensuregroup sequence
in a fresh output. QEMU's venv uses system-site packages by upstream design;
selected packages, interpreter, tools, pkg-config metadata and library paths are
recorded and pinned. This is a practical dependency identity gate, not a claim
of a hermetic system-header/toolchain build. Docs and testdeps are not required
for the selected target. The two QEMU wheels provide Meson 1.9.0 and pycotap 1.3.1.
Python 3.11 provides tomllib; no global pip install or network package resolution.
toolenv01's ancillary audit failure is preserved: pkg-config is a shell wrapper,
not an ELF executable. V4 classifies inputs before ldd, pins both known wrappers,
their shell, rpm and the explicit pkgconf target, and rejects unknown wrappers.

After review, parent launches `build_v4.py build` directly as the transient
service MainPID, with `--toolenv`, `--reviewed-toolenv-sha256`, `--output` and
`--service`. Bounds stay configure 900 seconds, Ninja 1800 seconds with -j4.
`checked_build(build_dir, reviewed_build_sha256)` is the shared read-only
receipt/image admission API for downstream launchers. Successful build remains
BUILT_NOT_EXECUTED; directed AKV, native QBS and unchanged Stage4 ELF gates are
still required. No RTL timing, arithmetic acceptance or deployment claim.
