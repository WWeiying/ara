# Prepared Private Acceptance

`python3 -B verification/qbs/m4_prepared_reuse/packed_stride/rvv_fallback/repair_accept/accept-prepared.py`
uses fresh output `verification/out/m4-stride-rvv-repair-20261027-03`.
It preserves both earlier tooling failures and reuses the exact -02 object,
ELF, source and linker map. Nothing is recompiled, relinked or installed.

The corrected ownership audit uses the actual emitted ordinary trait
`tensor_traits<block_q4_K, 1l, 32l, (ggml_type)15>`, specifically its
`compute_forward` entry and vtable. The private repack object supplies both.
The source defines the ordinary Q4_K 32x1 instance with Q8_K (enum 15),
selects it at VLEN1024 for row counts divisible by 32, and forwards MUL_MAT
through `forward_mul_mat`. This is not a QBS-tag instantiation. The incorrect
nominal-symbol expectation remains preserved in the earlier failed runner.

Inherited pins merge conflict-rejecting, and every -02 artifact is additionally
pinned in -03 before execution. All are rechecked after execution, including
the unchanged active 1880-entry VCS inventory. The original test object and four
normal archives remain those in the frozen link command. A new initramfs uses
the -02 ELF; only its path changes in the original QEMU command.

Acceptance requires all four M4/M7 padded/element-stride Q4_K N32 K512 cases,
704 finite bit-exact outputs, zero native QBS calls, and the original numeric,
ownership, callback, integrity and completion checks. The existing explicit
successor checker differs only in the required producer accounting: two K512
dense calls followed by two K256 gathered calls. No checker is edited here.
The existing mutation suite is run against the resulting raw QEMU log.

QEMU is bounded to 180 seconds; host elapsed time is workflow information only.
Commands, exits, raw logs, symbol audit, comparison and final result are in -03.
This is private functional evidence, not installed-runtime, QBS, Q8_0,
MUL_MAT_ID, RTL or performance acceptance. No commit; parent review required.
