# Final Publication Delta

Both prior prepared plans remain immutable and unlaunched:
plan01 `2e4be5e555d14eac74877535733783ad0970eefdd376328678d3e5a837236897`;
plan02 `41e1c8521953dcc5322dacf10de1ee53d59c3f7d1187118c63136f46aababe7a`.

New plan SHA `7ff93716f73ad92ccaf3327f44de076909944b4cf7091709141feeabdfc78ece`,
858 input pins. Worker remains byte-identical to02,
`bcdb7357e55131e61ef345f1260799d878cab98c44b5a5eca3e0ba3c92a89741`.
Only terminal_publish.py changed:
`495a2f91dde233c040eea231531d414b734184100b7c33a88dda98b6070ec718`.
Checker/model/ELF/reset/helper/482 oracle are unchanged. Work05 READY unchanged.

Final publication semantics:

1. The actual worker timer is cancelled and joined; absolute monotonic expiry
   remains checked. CSV validation and all evidence hashing precede publication.
2. SIGINT/SIGTERM are blocked for pending-file serialization/fsync and first
   atomic candidate visibility. Known abort/pending/expiry is checked before
   that rename. The abort latch remains open through mask restoration.
3. After handlers are restored, the short locked `abort.closed=True` is the
   explicit cancellation linearization point. The frozen flags and monotonic
   expiry are checked exactly once. A handler that already set abort cannot be
   lost between checking and closure. The final record is corrected atomically
   to NOT_ACCEPTED if needed, before the worker returns non0. A failed correction
   removes candidate PASS and raises; no auto retry occurs.
4. Later cancellation does not reopen an already-decided terminal. Any candidate
   seen while the worker remains active is not whole-worker acceptance; the
   consuming gate needs actual worker exit0 as well as final record. There is
   no infinite signal rechecking and no fallible directory fsync after commit.

This follows temp-file fsync plus atomic visibility, not directory power-loss
durability. Removing the added post-rename directory fsync eliminates the finite
PASS-file/exception-exit mismatch noted in02. File fsync and signal failure
paths remain tested; no filesystem robustness beyond these facts is claimed.

Actual host03: 10 tests, waited child0,4.2182163298s, original21 inherited not
rerun. Includes separate Python children receiving genuine SIGTERM inside file
fsync and before the actual rename: both final NOT_ACCEPTED and actual child1;
pending JSON signal, timer abort during write, absolute expiry during write,
already-started callback cancel/join race, no overwrite, prepublish fsync failure,
late postdecision cancellation, unchanged checker/full21 inputs. Host SHA:
`eb7571fc452e62547530ab2d56861197711fe1ee559cd8e4325e578042a1682e`.

Same never-launched direct unit `ara-macc-full482-scalar64-m8-01.service`,
jobs1/reserved0,10800/12000/13200 bounds. Actual Hilbert final entry JSON/hash
required by unchanged entry_gate before a once-only run. No new reference/compile/
RTL/DUT during preparation. No additional user approval is requested: after the
qualified final delta review, run once under the already-granted authorization.
Scope remains natural first482/481 predecessors, not full22400/Linux history.
