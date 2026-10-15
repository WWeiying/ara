# Software02 Unique Finite Reference Entry

Verdict: **NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT**.
Under the parent's explicit conditional authorization, Aquinas may execute the
single sealed entry. This reviewer will not duplicate the execution. No DUT
authorization and no reference PASS are implied by this pre-execution review.

Entry: `full_e32_m1_packed_prepare01/reference_entry01/entry.json`, SHA256
`011a92d114214be61a6c376f352e140cb7e6cf76895fb5421165b452642b61a2`.
All298 input pins independently rehashed without mismatch. This binds the
accepted software02 Spike ELF
`b4fba0b73d4fbd656f54769f7ea8047b3af6fec848de53d685fb209a89651d4f`,
original bit-table/ledger, new observer modules, existing actual Host/compile
receipts, and accepted static positive cost upper2,550,519. software01 HOLD and
all its original evidence remain untouched.

## Observer Coverage

- `context.py` reads accepted software artifacts, not regenerated gold. The
  complete original5985 ordered calls/35 ops and exact FP table-derived bits
  were independently bound by the preceding artifact review.
- `lifecycle.py` verifies all276 original RNG/override stores at exact seed/call
  owners. Each of1890 FP calls requires64 ordered SW events at the two actual
  sites, alternating banks and all32 indices, exact value/address/width, before
  output initialization. Reusing equal old bytes cannot replace a missing store.
- Each of2205 mask groups requires sixteen ordered SD clears followed by every
  actual selected-bit SB update, including intermediate OR values in a byte.
  The total is35280 clear SD and38955 bitset SB. Only si0 owns this initialization;
  later starts reuse the original mask. Full128B footprint and upper zero bytes
  remain checked. The phases must precede FP refresh and output initialization.
- Capacity has one exact3-instruction window. All35 original helper PC ranges
  are classified, with the next original op and strict13-step window; stray
  interior helper retirements cannot be silently ignored. Actual PC/code is
  checked against the pinned disassembly, whose extra-RVV count was zero in the
  accepted linked artifact audit. Helper counts must be5985 per step,77805 total.
- Actual arguments, vset results, vtype16/vl/vstart, source v8/v16, old v24,
  low32 predicate bits, target full128B result, returned vstart0, and full vector
  store result are checked. Every call requires17 fresh8-byte output stores and
  all17 ordered actual8-byte reads:101745 reads,191520 data and11970 guards.
  There is no e8-style short-tail exception; output is136B.
- Startup BSS, single arithmetic entry and fcsr0/RNE setup bind actual code.
  Original lacks an fflags oracle; this is not a new flags acceptance claim.
  Failure-routine entry, bad console, incomplete counters, nonzero return or
  incomplete final lifecycle are rejected before acceptance.
- Exact5-row Spike reset, success HTIF PC/code/value and side-effect-free
  `0x8000007e: a001` park bind the actual linked image. Parser consumes through
  EOF and rejects other post-success PC/code/side effects. No SoC MMIO exit
  assumption is imported into this Spike-only observer.

## Host and Bounded Execution

Read existing21-test Host log and numeric receipt, no rerun. Actual child0,
timeout=false, attempts1, outer31.396273898426443s; unittest reports30.919s.
Tests include constructed full5985 parser flow, deleting each of64 equal-valued
FP writes, each clear/bitset event, each output store/read, truncated final word,
wrong owner/site/value/width, missing seed, wrong/extra helper, and invalid
reset/HTIF/post-HTIF activity. The constructed trace is explicitly synthetic
Host parser evidence, not ISA execution or replacement for the pending reference.

The execution wrapper verifies review SHA and exact entry SHA/pins, uses exclusive
fresh `reference01` creation, no retry, pinned Spike and `rv64gcv_zvl1024b`,
finite `rs 4000000; quit`,120s timeout and768MiB raw-file limit. It persists the
actual child wait before postchecks; one separate closed-raw audit has600s and
its own numeric wait receipt. Input hashes and raw identity are checked around
the single semantic parse. Firmware-to-HTIF above3M yields HOLD, not READY,
even if full architectural checks pass. Failure artifacts are retained.

Independent read-only binding completion `0ef151`: numeric0,1.75598092s.
No Host/compile/reference/DUT execution was performed by this reviewer.
