# Initial Packed Preparation Blocked

Tesla identified a real C pointer-arithmetic defect before any reference:
`in + offset - 32` is left-associative and can form an intermediate pointer
beyond the input array even when the final pointer would be inside it.
Host02 PASS did not detect this and is not proof against this UB.

Initial bound `0f228fad4293ba8ebc00182dea34150411c4450bba7ea5026ee29e5bcf7faf96`
and its source/ELFs/Host records remain unchanged. No reference was executed.
`corrected02` is a separate successor with `in + (offset - 32)` and new
artifact paths; the integer subtraction occurs only after overlap/empty guards.
Recompile and affected Host binding are required, not a new packing algorithm.
Unchanged gate/cache tests may be reused only by exact source hash identity.
