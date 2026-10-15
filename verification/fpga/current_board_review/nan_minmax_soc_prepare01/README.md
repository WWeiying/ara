# NaN Minmax SoC Singles

Source-faithful e32/m1 ports of two calls from rvv_fp_redspecial03. Software
and Spike reference preparation only. No RTL/image build or VCS/DUT launch.
Existing ordered-reduction e32/m1 SoC coverage selects scenario3/VL16/op0,
not either VFREDMAX tuple here. The matrix84 evidence is module-level.

| Zero-based original call | Scenario | VL | Mask mode/byte | frm/op/sticky | Bank1 fixture row | Result/flags |
| --- | --- | --- | --- | --- | --- | --- |
| 1294 | 1 | 3 | 3 / 0x24 | 0/2/0 | 647 | 0x7fc00000 / 0 |
| 1234 | 1 | 3 | 1 / 0x00 | 0/2/0 | 617 | 0x7fc12345 / 0 |

Original call = 2*(scenario*420 + length_index*60 + mode*15 + frm*3 + op)
+ sticky. Both use length_index3, VLEN1024/vlenb128/VLMAX32/vstart0.
All input elements and seed words are the archived qNaN 0x7fc12345. Only
element2 participates in call1294; call1234 preserves the exact seed payload.
Each ELF executes one complete original21-instruction op2 helper, not a1294
helper prefix. Original scalar initialization, fixture traversal, mask loops,
144 output-byte oracle, flags/vstart return and frm/fflags save/restore remain.
No claim of original Linux/full6720-call/parent acceptance.

The source C and generator/header hashes must match the archive manifest.
Archived input_bits.h is pinned directly; current floating.py is never used.
Complete op0/op1/op2 encodings are checked against the original Linux ELF;
op0/op1 are forbidden in raw execution at every interior PC.
The wrapper is the pinned existing integration adapter, not an edited helper.

oracle.py is an independent FP32 bitwise maximum implementation, using neither
fixtures nor reference results. Host truth tables include NaN, sNaN/NV,
signed zero, infinities, negative values and subnormals. Both scope results
are cross-checked with original fixtures. Raw checking binds every scalar
input/seed/mask/fixture access, target arguments, full vector input/mask/seed,
CSR context, result, full128B store, and all144 original output reads.
Host mutations cover parsed ledgers, exact raw effects, helper/CSR/boot PCs,
wrong opcode, active payload/alloff canonicalization, flags and guards.

Per-case static upper bound: 2,143,584 firmware instructions. Compiled mask
body, seed memcpy CFG and finite original loop counts are checked before
reference dispatch. Actual source proof, ELF/disassembly, code and tools
are pinned in reference01/admission.json.
Sequential, once per case: max3M Spike steps,120s wall,256MiB per raw file.
These are separate hard bounds, not completion-time guarantees.
First error stops the batch; sentinels and create-only receipts prohibit
automatic retries. Numeric actual_exit_unvalidated.json precedes metadata
hashing/extraction/checking. Raw logs are never edited by Host mutations.

Entry commands: prepare.py, static_cost.py, test_host.py, test_oracle.py,
reference.py prepare, reference.py run. All records are create-only.
host01.json and host02.json are retained preflights; host03.json is final.
Successful READY records remain pending actual independent review. No source
reference record grants DUT launch approval.
