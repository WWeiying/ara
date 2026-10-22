# Recovery01 Exact Entry Review

Verdict: NO_BLOCKER_ONE_CLOSED_RAW_RECOVERY_NOT_DUT.

Bound entry SHA256: `b3c6347e7b21c9dd036fc5fabc7f9f699c6e643d9f2b6fb5a5f3b77be5e8a060`. Freshly verified535 non-raw pins with zero mismatches. The remaining pin is the existing closed raw: its recorded SHA `4c570d9e9a24d3b0dd2a50dd865c999ac017a8d918efd17b190c30acc941ceee` matches entry and preserved firstfailure metadata. I did not read or hash raw; the recovery runner independently verifies that pin before/after parsing.

## Cause And Narrow Delta

Original Spike actual numeric0 /8.339230659s, original audit numeric1 /78.480145270s, no timeout/retry. Preserved firstfailure identifies line1437394, PC80000d6e, compressed SW c310, with3360 completed calls: setup for ordinal3361. This is a seed1 FP-store classification defect in the observer, not established source numerical failure. My previous entry review missed this classification omission; that historical NO_BLOCKER and failed audit remain unchanged.

New Lifecycle subclasses the pinned old implementation. Only FP store classification changes to the union of all three actual compiled paths (768 PCs), with explicit disjointness from source RNG PCs and path geometry checks. Authorization remains the inherited exact match against `self.fp[row['seed']][self.fp_cursor]`: PC, bank/address, width, value and ordering must all match. Union membership does not accept a different seed's store. Each path requires eight fresh32-bit input loads followed by256 alternating A/B32-bit stores through B127. Actual load PC sets are equal across the three seeds; load handling was already address-classified with strict selected-path matching and had no seed0 whitelist.

context.py, reference_check.py and raw_boundary.py are byte-identical to the reviewed entry02 versions. Full helper/oracle, fresh initialization, mask, sticky/cache, failure-range and EOF checks therefore remain intact. No replacement reference/model, code compilation or wider numerical waiver.

## Focused Host And Execution Gate

Consumed pinned seven-test receipt: actual numeric0 /1.171631657s, no timeout/retry. Tests cover original VL0 ordinals1366/3361/5356 for seeds0/1/2; complete8LW+256SW through B127 and next helper; wrong same/other-seed PC/path, bank, width and value; missing equal-valued firstA or finalB, duplicate/extra SW; load order/width/value/missing-load; integer RNG sequence not swallowed by FP union and FP stores rejected in integer setup. Tests were not rerun by this review.

recovery.py has no simulator-launch path. It binds the original exact Spike command/ELF/finite command and numeric0, preserves old audit1/STOPPED, and permits one exclusively created closed01 output. The offline child is bounded600s; actual wait/timeout receipt is saved before completion checks. All pins, including raw digest, are verified before/after; original raw inode/size/mtime are checked around the semantic parse. First error remains durable and no automatic retry occurs.

Acceptance still requires full5985 calls/766080 results/11970 guards, 389025 actual reads, 124041 expected reads, 53865 IDs, 14757 fills/33123 hits, 483840 FP SW, 154350 mask SB, original seed writes, all13 helper instructions per call, exact marker/counters, true HTIF success and pure park through EOF. Firmware>3M publishes HOLD, not PASS. This review permits only the parent's single closed-raw offline recovery. No Spike rerun, compilation or DUT authorization; no complete numerical acceptance yet.
