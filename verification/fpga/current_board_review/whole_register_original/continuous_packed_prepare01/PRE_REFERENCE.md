# Packed Full1134 Preparation

Scope: one scalar conversion, not original C byte identity and not Linux ABI.
Original source, wrappers/runtime/linker and 20 assembly helpers are preserved.
The case conversion replaces only full-array scalar initialization and the
oracle's word precheck with unchanged per-byte diagnostic fallback.

Host01 compile failed because `/usr/lib64/libubsan.so.1.0.0` is missing.
Its compile exit1 is preserved; no Host01 program ran. Host02 uses UBSAN trap
mode (no runtime library), not different target/performance flags. Target SoC
and Spike each compiled once successfully. No blind optimization flag trials.

Host02 executes actual source-extracted scalar/packed check fragments:
1134 full positives plus per-word/position mutations at initial error0/11/12,
cross-word errors, status accounting and CURRENT post-helper input changes.
Each corruption tests only its owning eight-byte word, not the whole matrix.
Actual exit0/7.438s: 3,706,506 comparisons, 3,701,376 corruption checks,
864 changed-input checks. `host_entry01` additionally runs the actual converted
main's complete source order with explicitly MOCKED helpers and Host capacity;
exit0, exact1134/366 summary. These are scalar Host proofs, not RVV execution.
The UB probe intentionally shifts by64 and exited-4, proving trap instrumentation.
Six fresh-store/read-gate tests exited0. No accepted Host test is rerun.

Reference `SetupLedger` starts only at actual original-main entry, ignoring BSS
zeroing. Before EVERY helper entry it requires 128 new input sd and 136 new
output sd with exact address order/size/value; entering a new call with old
shadow values but no fresh stores fails. Store/read phase boundaries use the
reviewed immutable completion cache. Each call checks all136 ordered ld words
by expanding all1088 original expected bytes, plus original helper paths,
vstart/status, exact counters/log and successful raw exit/HTIF. No extra RVV.

`lowering.json` binds actual ELF encodings for table ld, input/output sd,
current-input ld and both active/inactive output ld paths in BOTH backends.
No memcpy symbol/libcall or vector opcode outside original helpers is allowed.
Output guards are checked before forming input pointers; empty/partial masks
avoid shifts by64. Byte arrays are never cast to uint64_t pointers.

Parent's `../test_packed_boundaries_main01.py` was independently run by parent
(reported exit0/1.825s):1134/366;154224words=111096empty+42912full+216partial;
all guard masks zero and three seed periods match. This is complementary
geometry evidence, not a claim this implementation was independently executed.

Only after Tesla's bound-specific NO_BLOCKER may `reference.py execute` run
one complete Spike120s/40Mstep/4GiB reference and one parser600s. No automatic
retry, timeout enlargement or DUT path. Actual firmware cost determines next
admission; normal-path static lowering gives a plausible reduction, not a
runtime promise. All old O2/Os inputs and failed attempts remain unchanged.
