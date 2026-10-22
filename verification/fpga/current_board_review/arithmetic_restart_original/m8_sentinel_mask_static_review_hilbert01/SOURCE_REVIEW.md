# Exact Source Delta Review

Verdict: NO_BLOCKER_SOURCE_DELTA_ONLY. Read the complete old/new packed.h diff and compared case.c SHA256. No compile/test/reference/DUT executed by reviewer.

- case.c remains byte-identical, SHA256 `465bd9f3fa5503992cf4b11f2bc277a1a6e9ac56dca13eb916c26f2d50bbb212`; helper calls, original RNG/history, returned vstart, full fallback and exact error/guard/diagnostic accounting are unchanged.
- New packed.h SHA256 `37e49d968d9a4384a06c9331995015f364516102fe0bdb23ecc7c966049c6a5e`.
- SOURCE_PLAN.md identity `fcaf1feef4d4dd68ef1eebe686daa18985bf549e09944af5034ffa6e23fc3851` (plan identity, not compiled proof).

Actual delta only expands the mask loop to sixteen original-source memcpy8 operations at offsets0..120, and adds the ID0 path to each of16 full comparator blocks. One local typed005b005b005b005b constant is used. Each ID0 block checks exactly its original eight actual word offsets in order and returns1 on mismatch; nonzero-ID comparisons remain unchanged. Final4-byte tail expression, raw_word memcpy and output initialization are unchanged. No sticky accumulator, aliasing cast, cross-call cache or new RVV appears in this source delta.

All expected ID0 words must remain bound to the original dictionary, with original sequence/include/helper inputs pinned at compile. Source equivalence does not establish machine read/store counts, branch orientation, absence of spills or actual cost. Next parent-authorized short C checks and sole fixed-flags SoC/Spike compilations may proceed under that separate authorization; no reference/DUT permission follows. Actual whole CFG must account for dispatch/joins/constant setup/main/ABI and preserve old failures and fixed budgets. No repeat compile or flag trial is admitted by this review.
