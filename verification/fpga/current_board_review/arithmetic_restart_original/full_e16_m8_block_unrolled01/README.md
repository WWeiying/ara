# Original E16/M8 Full4095 Software Preparation

Sole profile: SEW16,CAP512,LMUL8,vlenb128,vtype11. The original512-element
RNG initialization and three seeds are preserved; a/b remain1024 uint16 words
(2048 bytes each). The original13-instruction helpers use v8..15,v16..23,
v24..31. No v32 neighbor or additional helper/vector instruction is added.

The checked output is514 uint16 words=1028 bytes: both0x005b guards and all512
values. The result span is1024 bytes; the original physical out array remains
1026 words=2052 bytes. Initialization is128 scalar full words containing
0x005b005b005b005b plus one32-bit0x005b005b tail. Comparison is128 full words
plus exactly4 tail bytes, never1032 or1088 output bytes. Constant-size builtin
memcpy and byte pointers avoid misaligned uint64 casts or alias extensions.

All4095 calls retain seed/op/VL/mask/vstart order and the original per-element
fallback diagnostics. The exact64-byte dictionary has3598 blocks and17 uint16
IDs per call; ROM369886 bytes. No calls are deduplicated, no checksum replaces
values and no reset/partition changes the original history. The128-byte physical
predicate has upper64 bytes zero and retains original per-group initialization.

Host compares every original C expected16-bit element to the independently
generated model, verifies original RNG and unused physical array bytes, and
executes original and packed full-source loops. All20 actual paired logs match.
Negative classes include active/prestart/masked/tail, both guards, returned
vstart, upper result byte and deliberate UB shift64. Each of1028 output bytes
is separately corrupted, and a protected page verifies exact tail4 access.
Actual source gather out-of-range, reduction with masked-off element0 and
compress cases are exercised. These are software Host proofs, not hardware.

The original C bytes are not recovered. Identity is the retained binary-equal
reconstruction of Linux ELF68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d.
Each original helper machine window matches the original stripped ELF.
Actual linked SoC/Spike images fit1MiB with at least655328 bytes before stack
top;64KiB stack is reserved. Automatic RVV is disabled and no extra RVV appears.

`reference_check.py` is an explicitly scoped immutable-e8-predecessor adapter;
`reference_delta.diff` records each typed16/physical/range change. Its lifecycle
uses actual compiled128SD+SW instruction PCs and scheduled order. StartupBSS
zeroing is checked separately from business initialization. No observer branch
may waive wide/late/unowned writes or missing per-call fresh bytes/reads.

Tesla's actual independently accepted entry hash is required before the sole
complete Spike reference. Fixed120s/4M hard instructions/768MiB raw limit;
3M firmware is the admission target. Over-target costs produce HOLD without
scope shrink, retry or extra run. Actual numeric waits are saved before checks.
No DUT, RTL change, image build or background e8/m4 progress query is authorized.
