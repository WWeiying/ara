# Independent Review Response

Reviewer: Maxwell, thread `01a1096a-c271-73e0-8371-db1dd52ef849`.
Status: P1 fix implemented and offline-tested; independent re-review pending.
No snapshot/application approval and no real DVE launch.

## Original P1

After initial approval admission, the original implementation trusted the
mutable snapshot manifest at runtime. A copied Tcl hook and its manifest hash
could both change while the original inputs and review receipt remained intact.
The wrapper could then publish success with a snapshot root different from the
receipt. Maxwell reproduced this with no real subprocesses. His remaining
review found no second blocker; that does not approve the changed implementation.

## Fix

- Parse approval from the same bytes whose explicitly supplied SHA was verified.
- Retain the reviewed root from the receipt throughout the run. Never derive a
  replacement trusted root from the current manifest.
- Verify the approved manifest bytes, exact file/directory membership, member
  types, and all member hashes with one shared validator. Reject symlinks and
  noncanonical member paths. Parse context from the same bytes checked by hash.
- Check before snapshot code import and process launch, after session completion,
  and before publishing success. Runtime prepare/finalize and all three Tcl
  callbacks require the reviewed root and check before and after their work.
- Publish only the root from the original receipt. A mismatch publishes rejection,
  not a new success root. Preserve the dedicated process-group cleanup on errors.

## Offline Regression

`test_wrapper.py` passes 24 test methods including the existing 11 Tcl API model
scenarios. Added coverage includes:

- Seven bundle negatives: content plus updated manifest, manifest-only change,
  content-only change, extra file, extra empty directory, missing file, and symlink.
- Twelve callback negatives: all four content/manifest/extra-file changes at
  each of raw, saved, and reset callback entry, through the actual runtime parser.
- Sixteen outer-run negatives: all four changes at prelaunch, callback,
  post-session, and prepublish boundaries. These use actual root/admission and
  publication guards, stub only expensive/live behavior, and never spawn DVE.
- One unchanged-root positive control. Mutation after initial `load_snapshot`
  cannot publish a different root; prelaunch mutation never reaches Popen, and
  postlaunch simulated failures exercise process-group cleanup.

The baseline remains the official gap48 aggregate of 645 PASS cases. The only
extension remains the qualified exact107 CSR constant-guard vectors. Do not
merge queue candidates, change RTL/old policy, touch parent gap55 preparation,
reinterpret the old failed strict gate, or launch DVE before independent review.
