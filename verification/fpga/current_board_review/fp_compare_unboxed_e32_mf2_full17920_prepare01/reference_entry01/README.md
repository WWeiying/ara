# Exact FP32 Reference Entry

Preparation only. The accepted software, numeric Host, GCC and linked CFG
are not repeated. This entry specializes the accepted full-e16 raw reader to
the actual FP32 ELF, source model and compiled access sites. It does not run
Spike until BOTH exact Averroes admission and separate parent authorization
are supplied. There is no DUT command or automatic retry.

`prepare.py` derives the real new spec, crosschecks every instruction against
ELF bytes, runs only short synthetic checker tests, and pins their numeric
receipt. The interpreter tracks known GPRs, all actual scalar effective
addresses/values/widths, initialized memory, exact helper control flow, CSR
state/deltas, vector source/result payloads and committed f0 writes. It never
initializes unknown GPRs to zero. Exact initial callee-save stores can capture
opaque caller values in memory; ordinary unknown source writes are rejected.

FP32 differences are explicit:64 fresh bytes per input bank,4096-byte backing,
16 input LD and49 fresh SD/SH per call,16 lanes of32-bit source data, vtype23,
actual LWU then FMV.D.X, unchanged130-byte output initialization and four-byte
LWU oracle. Both mask loads remain logical2B although all128 bytes are fresh.
Result old mask remains DK0=0x5b5b. Tail allowed sets, exact flags/sticky/vstart,
all17920 calls,185 static and326144 dynamic helper instructions remain strict.

The parser distinguishes `f0` from integer `x0`. Every vf move must record the
exact64-bit zero-extended32-bit source payload at the actual helper PC, including
nonzero seeds and sign/high-bit cases. NaN-boxed prefixes, erased nonzero raw
payloads and upper32 mutations are rejected. This is committed writeback trace
evidence, not physical FPR readback. Future DUT RVFI qualification additionally
uses the frozen M9 writeback proof already in source input pins.

The reference checks89600 helper memory-instruction occurrences and15360
nonempty targets. These are not proof of DUT CVX owner allocation/completion;
that future checker must retain every helper token even when target VL0.

Finite contract: `rs 4000000; quit`,120s reference,768MiB raw, one closed audit
bounded600s, firmware through actual HTIF<=3000000. Exact HTIF1 is necessary,
but not sufficient: every remaining record through EOF must be the actual
side-effect-free park instruction. No success-marker shortcut or missing-CSR
default is introduced. Any exception, raw/console failure, drift or partial
scope remains NOT_ACCEPTED with no retry.

Required future review JSON: `status=NO_BLOCKER_REFERENCE_ENTRY`, exact
`entry_sha256` and `input_pins_sha256`. Required separate parent JSON:
`status=AUTHORIZE_SOLE_FP32_FULL17920_REFERENCE`, exact `entry_sha256`,
`review_sha256`, and integer `reference_attempts=1`. Software-stage admission
is not accepted as reference launch authorization.

Deferred DUT-only note: preserve the parent's requested private monitor exact
newline-terminated `RVV_FP_COMPARE_DETAIL ... errors=N` veto with N>0, original
base FAIL_RE, complete tuple evidence and chunk-boundary negatives. This is
not implemented or executed in the reference stage; no frozen runner changes.
