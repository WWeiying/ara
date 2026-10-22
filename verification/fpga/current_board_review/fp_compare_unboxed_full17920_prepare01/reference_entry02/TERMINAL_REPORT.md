# Full17920 Reference Terminal

Status: **REFERENCE_EXECUTOR_PASS_PENDING_TERMINAL_REVIEW_NOT_DUT**.
This is the complete source-derived unboxed/unmasked e16/mf4 parent, not merely
the earlier265 calls and not alias-m8. It is golden software-reference evidence,
not original Linux execution or hardware acceptance of this full parent.

Independent ENTRY02 NO_BLOCKER:
`fp_compare_unboxed_full17920_source_review01/REFERENCE_ENTRY02_REVIEW.json`,
SHA`57c2f711ef74de40b426203361683951b3b43ab388b45dd1994f3a6f2c4b2e93`.
The parent conditional authorization was exercised exactly once after reading
and verifying that actual review. Entry01's Host-identity HOLD and all earlier
source-model/Host failures remain unchanged. No reference retry or second semantic
parse was performed, and no compiler, VCS or RTL task was launched here.

## Actual Process Evidence

| Process | Actual wait | Timeout | Elapsed |
|---|---:|---|---:|
| Sole Spike | 0 | false | 7.236188s |
| Sole closed raw audit | 0 | false | 218.384610s |
| Controlling executor | 0 | terminal observed | not inferred |

Receipts: [spike.wait.json](reference01/spike.wait.json),
[audit.wait.json](reference01/audit.wait.json),
[controller_wait.json](reference01/controller_wait.json).
The first two numeric waits were persisted before result acceptance. The last
records the actual tool process-completion response, not a PID/GC inference.

Fixed limits remained `rs4000000;quit`,120s,768MiB raw, one600s audit and
firmware<=3M. Actual raw is236711843 bytes,2655000 records:
5 reset-ROM + **2653044 firmware through HTIF** +1951 pure-park records.
Complete EOF was checked; no synthetic completion or truncation acceptance.
The measured firmware count is15998 below the compiled conservative Spike upper
2669042, and346956 below3M. This does not predict VCS walltime.

## Complete Source Scope

The [audit result](reference01/audit01/result.json) confirms:

- 17920 original calls in order;286720 result bits and35840 guards.
- All17920 expected flags and returned zero vstarts.
- Original185 static helper encodings with326144 dynamic op-helper instructions
  plus the single3-instruction capacity window.
- 734720 actual fresh scalar stores (41/call),143360 input LD (8/call),
  17920 complete output LWU and2240 exact hoisted-record loads.
- Every original raw scalar seed observed336 times across vf calls; seeds0/16
  zero, other30 nonzero, original invalid NaN boxing preserved.
- Exact DK0 old bits, all original allowed tail alternatives, full input/mask/
  output initialization, caller ABI/CSR save-restore, actual ELF PC/control flow,
  complete scalar/vector result store/read checks and pure-park EOF.

Reconstructed raw console contains exactly the case BEGIN, original
`RVV_FP_COMPARE_PASS sew=16 cases=17920 errors=0`, case PASS and BOARD_REPLAY_PASS
lines. No DETAIL/failure marker is accepted. Actual HTIF success1 is mandatory
in addition to the console and full counters.

## Immutable Bindings

Pre/post source/tool/reference-entry pins are identical, and the raw hash was
checked before and after the sole semantic audit. No raw modification occurred.

| Artifact | SHA256 |
|---|---|
| COMPLETE.json | `30b18a9051d31e73bc0cf786813c6849bcb87555c621a2554c23535ea0270657` |
| audit01/result.json | `42147ec08005540cd6a5416bd1a2682dd8f403c125ffbe9e8f59e923d3464def` |
| spike.wait.json | `60d93c3378c970dcd1cc76f06f87c4d14a762d3f809315838585782fed4aec9a` |
| audit.wait.json | `40055c14436152332401cdcef102ef48ae08ba40f2dcac0da610123990589d1e` |
| commits.log | `f87f872f9fa87bb45eefdcaf9c1b60d9e618d1d3dd9f04288a56d01b7c82f8ae` |

Aquinas has been sent these actual terminal paths/hashes for a metadata/pin-only
short review. No further raw semantic parse is requested. All future DUT work
requires separate authorization; these files make no full-parent RTL PASS claim.
