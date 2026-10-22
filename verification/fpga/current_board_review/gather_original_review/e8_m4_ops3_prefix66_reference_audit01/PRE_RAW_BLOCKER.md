# Pre-Raw Identity Blocker

2026-10-12. HOLD. No independent reference acceptance and no raw audit started.
The authorized single raw traversal has not been consumed.

The actual READY matches the main-authorized SHA exactly:
`f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649`.
However it explicitly records entire_original_linux_binary_rebuild_proven=false.
Its pre_adapter_binary_proof.json matches the pinned SHA
`e9e504107006cce96cd4c922e14cbf87b0b6440e23bf3f885fcec6de10c6c491`
and explicitly claims NOT_BYTE_IDENTICAL_NO_BINARY_EQUIVALENCE_CLAIM.

Independent hashes of the actual two ELF files confirm:

- Original: `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
- Rebuild: `1217bd89da691b7b9f0a9d838120ac3bc3b70db4116a0a47b1807ceefdf16143`.

The producer reports different compilers (Buildroot14.3.0 versus Xuantie14.1.1).
Matching source and13 helper encodings is a narrower claim than the required
exact original rebuild. This report does not assume the binary difference is
only compiler metadata or assert that the adapter's numerical result is wrong.

Main required original rebuild proof before the one audit. Under this exact
READY that prerequisite is not met; no raw was opened or hashed and no Host,
compiler, Spike or DUT was invoked. Full pin verification and raw-driver
execution were not started. Producer freeze confirmation is also not recorded
here; a completion label alone was not treated as freeze authorization.

Resolution requires either independently checkable exact original-rebuild
evidence with a newly authorized frozen readiness identity, or an explicit main
decision accepting the narrower source/helper-equivalence prerequisite. Do not
silently modify this READY, infer byte equality or rerun Spike to address it.

The preparer also labels original_stopped_tuple unknown. The independent audit
will retain the main's recovered numeric endpoint66 (VI31/VL256/start128/cap512)
without extending it to an unrelated unknown-stall reproduction claim.
