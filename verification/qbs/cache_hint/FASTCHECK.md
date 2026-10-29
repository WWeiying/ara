# Successor to the bounded first VCS run

The original `cache-hint-vcs-20261029-01` exhausted its 5400-second wall limit.
It remains FAIL and has no accepted performance result. Three completed trial
records had equal signatures, zero errors and matching architectural flags.
The fourth trial and final protocol checks did not complete.

The first paired ROI observations were 203427 and 202641 cycles. They suggest
only a small preparation benefit, not a production-ready speedup. In particular,
do not promote this optimization based on its larger comparison-length saving.

`native_fastcheck.cpp` is a successor, not a rewrite of the original pinned
source. It preserves the input, four-trial ABBA schedule, quantizers, cache
implementations, timed preparation code and full payload/guard checks. Outside
the ROI, it compares each payload using the existing RVV byte-equality helper.
It computes the repeated-output reference signature once rather than recomputing
the scalar FNV hash for all four trials. Consequently, the printed signature in
this successor is the reference signature; the actual-output check is the full
byte comparison and its error count. It is not a separate output-hash check.

The expected result, flags, counters and completion requirements in `check.py`
remain unchanged. This test does not provide an independent new proof of the
RVV byte-equality helper. That helper is already used by the cache; its prior
validation remains relevant. No byte sampling or hash-only acceptance is used.

`build_fastcheck.py` builds the successor into a new directory and retains all
capture, source, compiler and library pinning. Both variants are rebuilt into
the same ELF. Changes to out-of-ROI work can affect cache warmth, so compare
baseline/candidate within this new ABBA run; do not mix its cycles with the
incomplete earlier run.
