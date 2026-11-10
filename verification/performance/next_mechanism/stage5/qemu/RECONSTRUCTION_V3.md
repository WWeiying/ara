# QEMU Reconstruction V3

Successor to sealed recipe_v2.py. No adapter, model, archive, predecessor helper,
or failed preparation is modified. prepare01 failed on the upstream absolute
Xcode link; prepare02 safely extracted the archive and then rejected a legitimate
inherited file symlink. Neither is a model or numerical failure.

Before V3 implementation, the complete read-only prepare02 audit at
OUT/stage5_qemu_reconstruction_audit_20261110_01 found 34,940 inherited entries:
34,800 identical regular files, 8 regular replacements, 122 new regular files,
and 10 matching symlinks in six resolved-target groups. All eleven overlay
transforms, the trace append and seven new-file destinations were checked.

V3 plans the entire inherited overlay before any copy. All 72 retained archive
links are checked for exact topology and in-root resolution. A pinned symlink
is kept only if its target and content agree with the frozen source and pin;
it is never opened for writing. Conflicting aliases, changed targets, hardlinks,
unsafe parents, special files and writes affecting any archive alias fail closed.
There is deliberately no automatic unlink or alias-content reconciliation.
Changing an alias group requires a separately reviewed explicit plan.

All input copies, new destinations and exact-anchor transforms are checked
against the planned reconstructed bytes before writing. Regular copies are
limited to changed/missing files, use O_NOFOLLOW, and are verified; every
inherited pin and retained link is verified afterward. Link verification also
runs after the adapter overlay. Full source membership and minimal build
environment gates from V2 remain unchanged.

Host checks reuse the original 22 adapter/archive tests and add 12 reconstruction
tests, including the full read-only prepare02 dry-run. They do not reconstruct
the real tree, build QEMU or execute a guest. Synthetic copy tests use temporary
trees only. A fresh reviewed prepare03 must use recipe_v3.py; neither the host
receipt nor preparation proves native model behavior. Directed AKV, unchanged
Stage4 ELF and native QBS execution gates remain required on the new binary.
