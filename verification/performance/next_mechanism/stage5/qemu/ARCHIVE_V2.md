# Archive Preparation Successor V2

Source03 and `recipe.py` remain sealed. Parent prepare01 failed before build at
Python's `AbsoluteLinkError`; its report SHA256 remains
`10cb21e9ac020518dec5b6c9bc1dd718764f658bd6b831457947e73d81a5618f`.
This is an archive extraction issue, not an AKV/QBS model failure.

The single initial inventory visited 84,624 members, 694,485,712 declared bytes
and all 73 links. Exactly one link was absolute/unsafe:

```
qemu-10.2.0/roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack -> /opt/X11/include
```

The accepted archive remains SHA256
`9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`.
The link is referenced only by the EDK2 EmulatorPkg host's XCODE IA32/X64 flags
(`roms/edk2/EmulatorPkg/Unix/Host/Host.inf`, lines 136/143 in the frozen source).
It is not a dependency in the accepted QEMU build's `build.ninja`. QEMU's
`pc-bios/meson.build` unpacks existing EDK2 firmware blobs; this recipe does not
build the Xcode host emulator. No source under the excluded link is pinned by
the accepted source manifest. The exclusion must remain absent after inherited
source overlay and after build.

`archive_policy_v2.py` skips only that exact member name, symlink type and target.
All other entries still pass through `tarfile.data_filter` at extraction time.
Before extraction it checks the entire archive inventory, rejects duplicate or
noncanonical members, special files, changed exclusions, escaping links, link
cycles, and any link/member traversing the excluded path. The whole-archive SHA
and exact member/byte/link totals remain admission conditions. This is not
`fully_trusted` extraction or a generic absolute-link allowlist.

`recipe_v2.py` is an explicit successor copy of the sealed recipe. Its only
functional changes are this extraction policy, inventory/exclusion receipts,
successor schema/identity binding, and post-copy exclusion/archive checks.
All existing source closure, exact tree membership, minimal build environment,
direct service MainPID, command bounds, model host receipt, QBS unchanged-byte
and no-guest-launch requirements are retained. New preparation/build receipts
use `stage5-qemu-prepare-v2` / `stage5-qemu-build-v2` and record the original
sealed recipe SHA. Launch the successor filename, not `recipe.py`.

Host checks use `python3 -B test_archive_policy_v2.py --output OUT/..._04` and
include malformed-link synthetic archives plus the complete pinned archive
inventory. They do not extract the real archive, prepare a QEMU tree, compile,
or launch guests. Parent may prepare02 only after the host result and successor
source identity are reviewed. All original failure evidence remains unchanged.
