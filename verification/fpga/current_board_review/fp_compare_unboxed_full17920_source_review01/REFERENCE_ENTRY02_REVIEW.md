# Exact Reference Entry02 Review

Decision: **NO_BLOCKER_REFERENCE_ENTRY**. The sole finite reference may proceed
under the parent's existing conditional authorization, executed by Tesla only.
This is not reference completion or DUT approval.

Exact ENTRY SHA63647edc1479e91ec27377e5fe206e9064d114b75dacd7b05c59e805b59ff3c6;
input_pins SHAaa51cee0488c76be74c8277241142bd6eb121fe657901a2667d756129c88a3e3.
Independent metadata/hash verification returned0 and matched all106 pins.
The old ENTRY01 HOLD and its files remain preserved.

The executor delta is narrow: validate_host now compares the receipt to the
ENTRY's frozen host_wait_sha256 before establishing runtime pins, requires an
integer numeric0 and timed_out is False, then compares the actual log hash to
the pinned receipt's log_sha256. Receipt/log files are additionally in the
successor input pin set. The previously reported replacement counterexample
therefore fails before any output directory or reference child is created.

Actual new gate receipt is numeric0/not timed out,0.166s. Its six small tests
cover unchanged positive, changed-but-still-zero receipt, changed log, boolean
false rc, numeric0 timeout and nonzero rc. Source assertions exercise the real
validate_host function using temporary files. No repeat of the22 checker tests:
their original numeric0 receipt/log, checker, test_checker, spec and audit_once
are byte-identical copies, all independently compared here.

The previous source/artifact/ENTRY01 review of the unchanged checker applies:
full17920 original history, CAP16/e16mf4/vtype14, fixed DK0 old5b5b, all32 raw
unboxed ft0 seed values, original allowed tails/flags/vstart and guards,185 static
helper encodings/326144 dynamic op instructions plus capacity3,41 fresh writes
and8 actual input LDs each call, one4B LWU and2240 hoisted record LDs. Exact
linked Spike PCs, input bytes, BSS, caller s6/sticky spills, target vector inputs,
returned CSR values and original result/diagnostic checks remain mandatory.
No alias-m8 scalar boxing/old-value semantics or SoC endpoint is substituted.

Finite command remains rs4000000;quit with rv64gcv_zfh_zvfh_zvl1024b,120s and
768MiB RLIMIT_FSIZE (not RSS), one offline audit600s and firmware<=3000000.
The exact Spike ELF is0ecbd714c95e1aed2b1a6586cebdd7953e090d2da6d8c6521ee1101c2aec9671.
Actual HTIF PC8000007a success1 must follow complete scope; every remaining raw
record until EOF must be pure8000007e/a001 park. Nonzero/timeout/partial output,
failure PC/console, post-exit side effects, changed input or raw hashes veto PASS.
Exclusive output creation and explicit no-retry behavior remain in force.

Only small metadata/source/hash inspection was done by this reviewer. No Host,
compile, model, reference or DUT rerun, no active/raw trace read, and no query or
modification of the e32 inotify observer. Runtime results still require terminal
review; source-port success would not close the original Linux full-history claim.
