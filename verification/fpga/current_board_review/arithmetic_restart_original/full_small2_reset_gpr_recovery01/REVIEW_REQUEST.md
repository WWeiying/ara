# Frozen Successor For Confucius Static Review

**HOST_ONLY_READY_PENDING_INDEPENDENT_REVIEW_AND_MAIN_OFFLINE_AUTHORIZATION.**
No DUT/reference/build or full CSV audit ran. No old helper, worker, consumed
entry/parent approval or terminal record was modified. e32 remains CANCELLED;
e8 remains historical postcheck ERROR until a separately authorized full audit.

## Exact Change

checker.Strict subclasses the exact legacy checker SHA
`18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f`.
Its consume/finish methods are inherited unchanged, including all original
source/setup/window/result/guard/CSR, signed-load, store equality, CTRL raw0,
console and original-park checks. Host asserts method identity, not a copied
approximation. No observed wdata supplies initial state or a golden value.

Only after profile/spec/model/ELF validation, replace the legacy initial
`{0:0}` with the32 hardware-proven reset zeros. No unknown-source bypass exists:
deleting x8 from the state still raises the unchanged store check; a known7
versus observed0 still fails and does not rewrite x8 to0.

## Narrow Profile

Pinned reset_profile.json SHA
`308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4`.
Exact M6 image/snapshot/compiled manifest/configuration, executable image files
and10 relevant frozen RTL sources are checked. All imported project Python
dependencies are verified against the immutable original plan before import.
FpgaEn=0 selects the FF regfile, whose reset clears all32 GPRs. Testbench reset
precedes original _start; legacy first-retirement/order and full BSS checks
remain mandatory. This is not an ISA-generic reset assumption or midstream CSV
state. Changed profile/path/hash/initial values must fail closed.

Only `rvv_matrix_e8_mf8` exact SoC spec and unchanged4095-call model/ELF are
accepted by this successor. e32 is deliberately excluded pending e8 acceptance
and a separate parent decision. The original two-case plan is only an immutable
identity source; this module does not relabel or rerun that failed batch.

## Small Host Evidence

host01:8 methods PASS; actual subprocess wait0/9.437741s within60s, one attempt.
The test reads saved first_failure.json only, never the DUT CSV. Its four real
captured retirements are jal-main, sp decrement, ra save and s0 save. The fixture
starts at the documented pre-main boundary using captured known registers and
completed BSS/startup state; it is not presented as a whole-trace acceptance.

Positive: exact prologue including reset s0 save passes. Legacy checker still
reproduces the original failure. Negatives reject wrong mask/read-mask/address/
value, an explicitly removed unknown source, a changed known source, mismatched
FpgaEn/regfile/image/reset values/origin/shape, and a trace missing original
startup. No full-matrix Host or original14-method rerun was needed.

## Review And Next Gate

Please statically review exact profile binding, unchanged inherited checks and
small regression evidence; no full CSV parse is authorized by this request.
After Confucius no-blocker review, main must explicitly authorize one bounded
offline e8 full-CSV audit with actual process wait outcome and first-error
preservation. There is intentionally no CSV audit or DUT launcher entry point
here yet. Do not replace imports in the sealed old terminal auditor/worker.

Future recovery must still prove all4095 e8 calls,65520 results,8190 guards,
original model/history, exact artifact/image/command/exit/pins and generic trace
validity. Passing this prologue alone does not establish later correctness.
