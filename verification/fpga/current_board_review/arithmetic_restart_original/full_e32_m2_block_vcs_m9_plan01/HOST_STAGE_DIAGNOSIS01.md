# Host Snapshot Locator Cost

Host01 is a new-worker constructed stream, not DUT/reference. Its snapshots loop
rebuilds lifecycle.mask_schedule(0) on every retirement solely to locate the
first selected-mask load PC. That immutable80-event table need only be read once.
Observed calls/elapsed:1024/70.412s,1280/89.677s,1536/132.770s,
1792/184.692s. FP calls have more scalar rows; extrapolation of the observed
integer and FP phases predicts more than600s for the full3-seed stream.

Stop only this owned Host child, retain original script/log/numeric receipt.
Successor moves the four snapshot keys/PCs outside the row loop and changes only
the output receipt basename. Same checker, same Builder, full5985 positive and
all negatives, same600s Host bound; no deepcopy/fullgold change, no DUT/reference.
This is a diagnostic test-driver correction, not an accepted original Host run.
