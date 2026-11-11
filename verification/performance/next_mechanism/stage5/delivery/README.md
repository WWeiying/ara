# Portable QEMU Source Delivery

This is a source-packaging tool, not another acceptance gate. It does not import
the historical V3--V10 helpers, configure/build QEMU, run firmware, or change an
existing receipt. Current BUILD07/model workers remain independent.

The portable reconstruction inputs are exactly:

1. Python 3 with `tarfile.data_filter` support.
2. Primary `qemu-10.2.0.tar.xz`, SHA256
   `9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`.
3. Reviewed `manifest.json` and its content-addressed `payload.tar.xz`.
4. This standalone `qemu_source.py`.

The manifest carries relative paths, exact pre/post file hashes, sizes,
executable bits, link targets, all source-directory names, and the final complete
inventory digest. The primary archive supplies unchanged bytes. The payload
contains only modified/new regular-file bytes, including the complete fixed DTC
tree. Historical OUT paths, receipts, source helpers, probes, Git repositories,
and network downloads are not reconstruction dependencies. The optional origin
receipt/DTC archive audits occur only while capturing; their identities remain
provenance, not recursive execution inputs.

Variant04 has 13 modified upstream files, 325 added source/marker files and eight
added source directories. The 325 files comprise QBS six + `.xaraqbs-source`,
AKV/transport seven, DTC 310 tracked files at
`b6910bec11614980a21e46fbccc35934b671bd81`, and its retained Meson wrap marker.
Every path/preimage/postimage appears in `manifest.json`; files are not selected
by extension or by a hand-maintained partial source list.

All 310 tracked DTC files are byte-identical to the fixed Git archive. One
historical executable-bit difference is retained, not repaired:
`pylibfdt/setup.py` is executable in that archive but not in variant04. The
manifest explicitly records this difference and reproduces variant04's mode.

The only omissions are the exact upstream EDK2 symlink
`roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack -> /opt/X11/include`, plus optional
generated `subprojects/.wraplock` when it is an empty regular file and
`tests/qemu-iotests/scratch` when it is exactly an empty real directory. Changed
types, nonempty contents, other symlinks, and similarly named paths are not
ignored. No upstream source deletion or type/link change is allowed. Directory
tar-member trailing slashes are normalized, not treated as missing directories.

UID/GID, ACLs, timestamps and non-executable permission differences are not source
identity; reconstruction normalizes regular files to 0644/0755. Source content,
paths, symlink targets and owner-executable bits must match exactly. This does not
claim bit-identical compiled ELF output or transfer old execution acceptance.

## Commands

Host tests use only tiny synthetic archives and a real tiny source extraction:

```sh
cd verification/performance/next_mechanism/stage5/delivery
python3 -B -W error::ResourceWarning -m unittest -v test_qemu_source
```

Capture reads the final frozen source without changing it. Set `PRIMARY`,
`VARIANT`, `DTC_ARCHIVE` and a fresh `BUNDLE` output explicitly:

```sh
python3 -B qemu_source.py capture --archive "$PRIMARY" \
  --source "$VARIANT/qemu-10.2.0" --origin-receipt "$VARIANT/prepare.json" \
  --dtc-archive "$DTC_ARCHIVE" --output "$BUNDLE"
```

Capture checks the full primary/final source delta and replays all operations in
memory. It emits `SOURCE_DELTA_REPLAY_CHECKED_NOT_REBUILT`, not a fresh full-source
extraction or QEMU build result. Future clean extraction is explicit:

```sh
python3 -B qemu_source.py reconstruct --archive "$PRIMARY" \
  --bundle "$BUNDLE" --destination "$FRESH_DESTINATION"
```

Reconstruction verifies the primary/payload hashes, all preimages, safe extraction
and the complete final inventory. It neither downloads missing assets nor starts
configure/build. The original configure arguments are recorded in manifest
provenance. Host compiler, libraries, Python build packages and subsequent build
and execution evidence retain their own pinned delivery contracts.
