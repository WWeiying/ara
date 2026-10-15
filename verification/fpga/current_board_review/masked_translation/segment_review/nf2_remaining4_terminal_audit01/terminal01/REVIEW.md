# Independent NF2 M6 Terminal Review

INDEPENDENT_M6_NF2_FOUR_SOURCE_CASES_ACCEPTED_NOT_LINUX.
Actual audit command exit0; audit duration146.208245s.
Actual simulator child rc0, elapsed1759.4446330131032s, persisted before postcheck and bound by strict report SHA; no GC exit inference.
One full CSV parse: 1308379 original rows, 1307708 retired instructions, lastcycle1509943.
Four exact source cases, eight checkpoints, 3567 scalar checks; legal alternate-field flags[False, False, False, False].
Both64-element fields, two output guards and full8KiB memory/PTE/neighbor/CSR oracle retained.
Six handlers: two pagefaults/start2 and5 plus four S-ecalls; same-PC retry, both-field prefix poison.
Two nofault precleanup checkpoints precede PTE cleanup; two unmapped refills each2048 halfwords.
Complete original action order, actual retired PC/code, error-state veto, restore-readback firmware checks, magic and CTRL0 passed.
Pins verified before/after: 721, including700 original plan pins.
Lossless before/after row SHA: `2878ecd25c604434f09fb88d04c04516bc2ad899220c78698cd3e1bbbc96b632`.
Result SHA: `79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee`.
Pins SHA: `9e8a6025c4dd443d4ff4ce65b011b117ad9ecbdd40aaa24a6790b9ce91dba152`.
Audit exit evidence SHA: `f5d1f36a66b674e1636bf64307ef52ce8975b790b655f1db726f80423309eb5e`.
Complete SHA: `39c697f34c0db5b827cdebb428e7e5181ce0631715cfe8cc71f2d63bf554fcbe`.
Plan SHA: `7a644bfd57e314649a92a6512cd6c994c49f7e9b656f0caaa5e172ec0e4d9c55`.
Image SHA: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.

Scope is four exact archived failed-single geometries on frozen M6, not full96/all40 or Linux signal ABI.
Both protection/unmapped cases use invalid Sv39 PTEs; remap/refill distinction retained.
Original mask128B versus fixture16B/helper8B consumed remains a documented port boundary.
RVFI scalar full-oracle evidence is not direct vector payload or internal CSR signal capture.
No reference evidence substituted for DUT. Outer service terminal returncode is UNKNOWN, not fabricated.
