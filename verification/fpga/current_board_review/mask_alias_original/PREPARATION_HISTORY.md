# Preparation History

Initial source preflight refused before creating prepared01 or compiling/running
anything. The adapter incorrectly applied the additions36 source-release hash
742e4fcfa3b4dcd3d326fcf5a2f56979502aecc2ea1a6e066ee9eef1542913a4 to
`rvv_mask_logic_restart01/manifest.json`. That hash belongs to its
`transfer_manifest.json`, as verified by recomputation. The generator manifest
hash is c27b18089d4b7f75359f4e9fefecad120183382b2763c4047d785fd77f9f1aff,
also recorded by both historical reference_512.json and reference_1024.json.

Correction binds both exact files and requires every generator-manifest field
to match the transfer manifest; extra transfer fields contain reference/release
information. No input source, ELF, case membership or oracle was changed, and
no mismatch was ignored. This was an adapter identity-path error, not source
drift or a simulation result. The original rejection is retained here.
