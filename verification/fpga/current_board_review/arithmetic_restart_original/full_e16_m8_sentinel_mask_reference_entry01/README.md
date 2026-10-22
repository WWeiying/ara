# Finite Reference Entry

Original e16/m8 integer arithmetic: 25 operations, 4095 chronological calls,
CAP512, typed 0x005b, 1028 checked bytes, physical 8-register groups.
Software02 alone changes sentinel dictionary-ID0 comparisons and mask16 stores.
Original fallback, source inputs, helpers, dictionary and all results remain.

ENTRY.json is preparation, not execution. Exact independent review schema:
`status=NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT`,
`entry_sha256`, `one_attempt=true`, `DUT_authorized=false`.
After that review the existing parent conditional authorization permits one
reference.py execute --review PATH --review-sha SHA.
Finite rs4000000/quit, 120 seconds, raw768MiB, one audit600 seconds, fw3M.
No retry, VCS, image rebuild or automatic DUT authorization.

Host02 is 13 short decoded-PC/epoch/ABI/marker rejection tests, not fullstream
raw execution proof. Host01 failure is retained: CFG stores held full GPR values,
where SH memory payloads are ISA-width truncated. PROFILE02 preserves full
source_register_value and truncates only the memory payload. No oracle changes.
Shared actual shadow is initialized by actual stores and actual vector output;
all scalar loads are checked against this shadow or pinned ELF ROM.
New actual main ABI frame304 and exact callee-save PCs are the only unknown-save
exception. Actual raw rd updates are consumed, not CFG call summaries.
The pinned CFG walker invalidates caller-clobbered registers at every call.

Full reference audit must check all 4095 source contexts, fresh128SD+SW1028B,
1472 input SH per seed, all original mask groups16SD, original13 helper PCs,
physical source/vector results, full128LD+LW oracle reads, guards and vstart.
HTIF is not EOF acceptance: all remaining records must be exact effect-free
EOFPARK. Source helper retirements are not claimed as M9 backend token evidence.
Source flags scope is unchanged; this integer family does not add FP checks.
Old failed profile/Host and all original source/compiled assets are preserved.
