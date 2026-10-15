# Corrected Packed Full1134 Entry

The initial parent directory remains blocked by pointer-expression UB and has
never run a reference. This successor changes only `in + offset - 32` to
`in + (offset - 32)` in the target header, plus independent artifact paths.
The corrected compiler emits explicit integer subtraction/zero-extension before
address addition. ELF hashes legitimately differ; no old ELF identity is reused.

Corrected header SHA256:
`6e11dc9edb6dd115fef0b8950cc49ae8e606a656f5c38de385e4cef25600c6e7`.
SoC ELF: `514142ed332ef213be7a2ffff88069a86ddd758ce7d6019ff11228393e1e75ca`.
Spike ELF: `fe632c92dd06a7b37979cc1b84e26b2d7b701890538a373a769be049e5be31b0`.
All20 complete assembly helpers still match original instruction encodings;
no RVV outside their windows and no memcpy libcall. Input/output init still
scalar128sd/136sd each call, all136 output words checked. Source case/original
byte diagnostic fragments, complete1134/366 order and runtime are unchanged.

Corrected Host02: actual exit0/7.341749s, case and corrected header hashes
recorded; 3,706,506 local comparisons including3,701,376 byte corruptions and
864 changed CURRENT-input tests. It does not rerun the full matrix for each
mutation. Corrected actual-main Host: exit0/0.020835s with1134 mocked-helper
calls and exact366 skips. UB instrumentation probe actual-4. Mocking applies
only to Host, not reference or target ELF.

Fresh-store/read-gate six tests are reused from the parent preparation ONLY
after exact byte-identity checks for coverage_gate.py, completion_cache.py and
test_gate.py. The original numeric receipt and code are included in new pins;
the tests are not silently represented as a new execution. Fresh setup starts
after main entry and resets EVERY helper, so old equal-valued shadow memory
cannot satisfy a new call's128+136 word writes. Ordered word reads expand into
all1088 original expected bytes. Early writes require previous full completion.

Nested-path adjustments use the original prepared01 location via OLD;
the decoder path uses OLD.parents[3]/coverage, not an incorrect relative parent.
All evidence remains distinct from original C byte identity and Linux ABI.

The first static freeze check rejected an old expected inactive-ld encoding
(a5 rather than corrected a4). No bound/reference was produced. The assertion
was corrected to the inspected actual0x6318 ld at SoC0x80000874; no target
source, compiler flag, Host result or ELF was changed/reexecuted for this fix.

The independent entry JSON required by reference.py is:
`{"status":"NO_BLOCKER_REFERENCE_ONLY","bound_sha256":"<actual reference_bound01 SHA>"}`.
Additional review fields are allowed. No reference executes without its exact
path/hash binding. Then only one120s/40Mstep/4GiB Spike reference and one600s
parser, numeric waited receipts, complete oracle and before/after pins.
No DUT authorization or launch path is included.
