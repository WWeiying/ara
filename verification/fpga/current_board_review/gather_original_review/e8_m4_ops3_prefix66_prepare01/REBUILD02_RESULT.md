# Exact Original Linux Binary Supplemental Proof

**PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL**. One Buildroot compile, actual
numeric rc0, elapsed0.417814985383302s within30s. No second compile, new SoC build,
Spike/reference execution, DUT/VCS or RTL change.

Both archived and rebuilt full ELF SHA:
`a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
Direct complete-byte comparison also verified equal after proof publication.

Actual partition generator SHA01d338cd72204e644598afdc324a1a74c7d46733d0a625c26d95aa8bf20194d6
matches the archived manifest. Its original compiler-command AST was evaluated
with exact source/header/assembly, e8/m4/restart1/opmask8 and the installed
Buildroot2026.02 GCC14.3.0 driver. No flags were guessed, relaxed or tuned;
`original_linux_rebuild02/command.json` and `archived_command_source.txt` preserve
the derivation, actual original parameter order and concrete paths. Wrapper and
`.br_real` compiler hashes, original sources, archive ELF, actual command/exit,
compile log and rebuilt ELF are pinned by the new supplemental proof/readiness.

## Immutable Handoff

- Old `READY.json` remains SHA
  `f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649`.
- New `READY02.json` SHA
  **11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc**.
- Supplemental `original_linux_rebuild02/proof.json` SHA
  **7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd**.

READY02 explicitly binds the unchanged old READY plus the new exact full-binary
proof. Its `full_linux_rebuild_proof_path`/SHA is the supplement; the old Xuantie
rebuild proof and old source proof's historical unproven flag are intentionally
not edited or misrepresented as passing. The original full Linux program now has
proven binary identity before any adapters. The retained adapted prefix itself
still is not execution of that Linux ELF.

The same original66 ordered calls/65 predecessors/cap512,33792 results,132 guards,
858 helper instructions and one previously generated reference remain the scope.
Old SoC/Spike ELF metadata and reference SHA are exactly unchanged. This closes
the missing binary-identity prerequisite only, not the pending independent raw
audit, a DUT test, full2688 execution, Linux schedule or unknown historical stall.

All readiness-bound inputs are now frozen; no further edits or runs. This later
handoff note is separate from both readiness pin sets.
