# M7 Build Preparation Only

No snapshot, Bender, EDA build, DUT or service was started. No final VLDU/VSTU
hash is bound while VSTU acceptance is pending. No M6 file or task is changed.

`build.py` reuses `integration/run.py snapshot` and `build-image`, deriving
from `indexed_overlap_original/repair06_build/build.py`. It pins the existing
M6 snapshot/image/compile manifest and both integration helpers. The only
allowed live-source differences are `hardware/src/vlsu/vldu.sv` and
`hardware/src/vlsu/vstu.sv`; every other M6 input, including dispatcher and
configuration, must match. Both final approved hashes are required at build.

Configuration remains NrLanes4, VLEN1024, 2MiB, OSSupport1, PMP0 and the full
M6 settings. Snapshot membership must remain 539 files (537 live inputs),
compiled membership 453. Only the two approved source contents and exact
candidate06-to-candidate07 path relocation may differ. An existing output
directory is rejected; failures retain their first output, with no retry.

Read-only preparation command, from the integration worktree:

```sh
python3 -B verification/fpga/current_board_review/memory_candidate07_build/build.py
```

Actual check returned 0 and found only VLDU/VSTU changes. A small mocked
gate check covers approved pair, extra file, wrong hash and missing change;
it runs no build/helper and binds no current RTL SHA.

Future command, only after both final source revisions are accepted and main
authorizes building (variables must contain the final approved literal hashes):

```sh
python3 -B verification/fpga/current_board_review/memory_candidate07_build/build.py \
  --approved-vldu-sha256 "$APPROVED_VLDU_SHA256" \
  --approved-vstu-sha256 "$APPROVED_VSTU_SHA256" \
  --authorize-freeze-and-build
```

Do not populate approval variables by blindly hashing still-changing sources.
Output: `/home/wangwy/fpga_runs/current_board_memory_candidate07`.
The helper first freezes new sources, then builds its own campaign/image.
BUILD_ACCEPTED.json means build identity checks passed, never DUT acceptance.
M6 build-image elapsed 112.090s; this is historical context, not an M7 runtime
guarantee. Snapshot/hash and license wait add cost. No timeout or live task is
modified by this preparation.

One metadata-only check of e16 found attached.json/authorization.json only in
its automatic terminal audit directory, with no terminal audit result yet.
No active trace was read and no repeated background query was made.
