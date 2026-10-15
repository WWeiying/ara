# Draft: Original11 Ordered Reduction Architectural Ports

**Static plan only; awaiting Aquinas source/recovery confirmation.** This file
is the only output of this task. No new ELF, Host executable, Spike reference,
VCS execution or RTL image was prepared/built/run. No running VI0M6 process,
service or resource state was queried or operated on. Aquinas owns the source
inventory in this directory; this draft does not substitute for that acceptance.

## Exact Archive And Static Checks

Archive:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_redspecial01`.

Manifest SHA256:
`cb890017f97fa3c6bfa2e4d45dfb745166d4934b5092b9951ad2b86a1b85aa0c`.
All11 cases are named `rvv_small_fp_redspecial_<sew>_<lmul>`; each has
`scenario_role=single_original_trial`, configurations1, and an archived missing-NV
detail. This archive is redspecial01, not a substituted redspecial02 test.

Read-only checks performed now:
- All11 scenario.c files were read and are byte-identical, SHA256
  `fd6870fa4eed43bd660136c9d90577f5cfbe99d7ba834a14fedad96237cd251a`.
- All66 manifest-listed files matched: scenario.c, operations.S, operations.h,
  fixtures.h, input_bits.h, fp_reduction_inputs.h for each shape.
- All11 reduced Linux ELFs in `overlay/opt/ara-tests` matched manifest sha256.
  Each existing `original_rebuilt.elf` also matched its distinct
  `original_elf_sha256`; no rebuild was performed. The archive's
  byte-identical-rebuild assertion is provenance, not a new build measurement.
- All11 fixture JSONs have2 banks of3360 pairs. Every numeric pair parsed from
  fixtures.h matched JSON:6720 pairs per shape,73920 comparisons total.
  This verifies representation consistency, not independent execution of all
  fixture configurations. Fixtures.json itself is not in scenario_sources;
  its additional hashes are recorded below.
- ELF symbols are stripped. An initial symbol-only objdump produced no helper;
  complete read-only disassembly then located unique ordered/min/max targets
  and the surrounding21-instruction windows. No symbol address was guessed.

Read-only objdump:
`install/riscv-gcc/bin/riscv64-unknown-elf-objdump`, SHA256
`736c0afe63f17e4eab376aa9f31d4f07f7ac113384119ec699af22afa1501ac2`.

## Membership And Priority

Every selected tuple is scenario3/l4/mode3/rm0/op0/sticky0. M6 uses
VLEN1024/NrLanes4, so VL=CAP1024/2 and fixture bank1. CAP512 remains in source
and compiler definitions; do not silently substitute CAP1024 for both.

| Shape | CAP512 | CAP1024 | Selected M6 VL | Original ordered PC | Helper slots3 /6 encodings | Priority |
|---|---:|---:|---:|---|---|---|
| e16/m1 | 32 | 64 | 32 | 0x105f2 | 008772d7 / 0086f2d7 | priority gap |
| e16/m2 | 64 | 128 | 64 | 0x105ec | 009772d7 / 0096f2d7 | priority gap |
| e16/m4 | 128 | 256 | 128 | 0x105f0 | 00a772d7 / 00a6f2d7 | priority gap |
| e16/m8 | 256 | 512 | 256 | 0x105f6 | 00b772d7 / 00b6f2d7 | priority gap |
| e16/mf2 | 16 | 32 | 16 | 0x105f4 | 00f772d7 / 00f6f2d7 | priority gap |
| e16/mf4 | 8 | 16 | 8 | 0x105f2 | 00e772d7 / 00e6f2d7 | priority gap |
| e32/m1 | 16 | 32 | 16 | 0x105fa | 010772d7 / 0106f2d7 | existing mapped control |
| e32/m2 | 32 | 64 | 32 | 0x105f8 | 011772d7 / 0116f2d7 | priority gap |
| e32/m4 | 64 | 128 | 64 | 0x105f2 | 012772d7 / 0126f2d7 | priority gap |
| e32/m8 | 128 | 256 | 128 | 0x105f6 | 013772d7 / 0136f2d7 | priority gap |
| e32/mf2 | 8 | 16 | 8 | 0x105f8 | 017772d7 / 0176f2d7 | priority gap |

Prioritize the10 rows other than e32/m1. Keep e32/m1 in the full11 source plan
as the continuity control mapped by existing integration identity
`reduction_fflags`. Existing reduced VMFPU tests carrying all11 VL labels
are not decoder/LMUL/full-program acceptance; their README explicitly excludes
dispatcher, requester, VRF and CPU. Do not count those as10 additional original
source ports. Do not automatically rerun the known control or launch any case.

## Original Source Semantics

The original C has all8 scenario initializations, seven lengths, four masks,
five rounding modes, three operations, and two sticky settings. It fetches
`fixtures[vlenb==128][scenario*420+index++]` before the sticky-loop filter.
Only tuple3/4/3/0/0/0 calls a helper. The full outer loops continue afterwards.

Selected zero-based fixture index:
`3*420 + 4*60 + 3*15 + 0*3 + 0 = 1545`.
Statically there are3360 fixture selections and6720 sticky candidates:
3090 skipped candidates precede the one actual call;3629 follow it.
These are source-level skip counts, NOT3090 prior reductions or a measured
scalar-load retirement count. A compiler may optimize unused scalar work;
the adapter must not hand-delete/reorder these loops or invent vector warmup.

Scenario3 seed is input_bits[12]=+Inf. Even source indices are+Inf, odd are-Inf.
All64 seed words are initialized, source input is initialized through cap,
and the entire64-byte mask is0x24 (bits2 and5 of every byte). At every selected
M6 VL, active indices include2 (+Inf) and5 (-Inf). The independent mathematical
selected-case expectation is canonical NaN and NV16 with rm0/priorflags0:
- e16: seed/source+Inf0x7c00, -Inf0xfc00, expected0x7e00.
- e32: seed/source+Inf0x7f800000, -Inf0xff800000, expected0x7fc00000.

All11 archived `fixtures[1][1545]` agree with that result and flags16.
**VLEN512 is not interchangeable:** e16/mf4 and e32/mf2 have selected VL4;
only+Inf at index2 is selected, so bank0 expects+Inf/flags0. Their bank1
VL8 includes index5 and expects NaN/NV16. Other selected bank0 entries here
also expect NaN/NV16.

Each call initializes **all144 output bytes to0x5b**. a2 points to output+8.
Only bytes8..(8+SEW/8-1) may change to the exact little-endian result. All other
bytes, including the surrounding guards and the rest of the stored m1 vector,
must remain0x5b. Required return is low32bits vstart0, high32bits flags16.
Keep the exact original scalar144-byte loop, flags comparison, flags_seen OR,
capacity guard, details, final summary and returncode.

## Actual Original Helper Encoding

For every shape, op0 is a21-instruction helper, not a13-instruction gather:
m1 seed/old-destination loads; full-cap source and mask loads; requested-VL
vset; save frm/fflags; set frm=a6 and fflags=a7; ordered reduction;
**immediate csrr vstart then fflags**; pack flags above bit31; restore caller
frm/fflags; m1 vset and whole m1 store; return.
The reduction target is `0c881c57 vfredosum.vs v24,v8,v16,v0.t` in every row.
op1 and op2 remain original `14881c57 vfredmin.vs` and
`1c881c57 vfredmax.vs` helpers in the assembly, but the filter never calls them.

Complete21 machine encodings in instruction order (compressed instructions
retained). For each LMUL replace zero-based slots3 and6 using the table above;
all other slots match the corresponding SEW base.

e16/m1:
```text
008072d7 0205d807 02065c07 008772d7 02055407 02b78007 0086f2d7 00202ef3 00102f73 00281073 00189073 0c881c57 00802573 00102373 1302 00656533 002e9073 001f1073 008072d7 02065c27 8082
```

e32/m1:
```text
010072d7 0205e807 02066c07 010772d7 02056407 02b78007 0106f2d7 00202ef3 00102f73 00281073 00189073 0c881c57 00802573 00102373 1302 00656533 002e9073 001f1073 010072d7 02066c27 8082
```

The CSR read order must not be changed to wait for late flags. M6 must expose
NV by the original immediate fflags read. Keep caller CSR save/restore and
actual helper return; a synthetic post-delay CSR sample cannot replace it.

## Wrapper Adaptation Plan, After Independent Confirmation

Use the existing read-only
`verification/fpga/current_board_review/integration/prepare.py:adapt`;
current SHA256 `c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8`.
It replaces only the Linux syscall wrapper with replay_write, renames
probe_main to a per-shape main, turns capacity/final exit syscalls into return
codes, and removes the Linux _start. Its recognized TIOCOUTQ omission is not
present in these source files. It fails closed on unexpected wrapper counts.
Do not invoke its stock freeze/compile CLI: that includes unrelated cases and
only one redspecial shape. A later owned adapter can reuse adapt plus the
existing runtime/startup/linker and compiler settings without editing helpers.

After Aquinas confirms recovery/provenance and the parent permits preparation:
1. Copy/pin each complete original source set and manifest into a new owned
   preparation directory, with exactly11 entries and the table's defines
   SEW/CAP512/CAP1024. LMUL is already in each original operations.S.
2. Preserve exact C except the recognized wrapper transformation; preserve
   every assembly instruction. Use unique per-shape symbols only to avoid
   collisions, with a complete original-to-adapted symbol/address map.
3. Build software-only SoC and Spike ELFs with the established GNU toolchain,
   no ZCC. Do not recreate the RTL image. Independently compare capacity and
   all three original21-instruction helper encodings against these Linux ELFs;
   relocation/symbol prefixes do not authorize changed opcodes.
4. Independently derive selected inputs, seed, masks, fixture index and all144
   expected bytes from source, not just a compiler call to the existing table.
   Confirm both fixture banks and record the smallest-shape bank distinction.
   Future Host negatives should include missing NV, extra flags, wrong NaN bits,
   nonzero returned vstart, wrong mask/SEW/LMUL, wrong fixture bank/index,
   either8-byte outer guard and untouched bytes inside the128-byte m1 store.
5. Only with reference authorization, run a bounded Spike reference for each
   approved port with complete raw logs, all144 scalar byte checks, exact one
   op0 call/zero op1+op2, capacity, original21 order, caller CSR save/restore,
   input/seed/predicate/setup and final successful exit. Preserve original
   initialization and skip-loop semantics; do not collapse to a synthetic
   one-instruction fixture. Report actual retired cost before setting any
   future VCS wall-time budget.
6. Reuse the existing frozen M6 image:
   `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.
   Expected previously pinned image ledger SHA256:
   `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
   Reverify image/configuration/ELFs at future prepare time. M6 RTL build is
   neither needed nor authorized. Future VCS admission is separate, with
   exact-case membership, private ELFs, raw failure veto, strict COMPLETE/
   no-abort/exit, unchanged pins and original full oracle.
   The archive's30s Linux timeout is not a measured host-VCS budget.

No Host executable, ELF, Spike or VCS preparation is authorized by this draft.
Do not count fixture-bank consistency, source identity or mathematical
expectation as a measured architectural PASS. Original Linux process/OS/timing
acceptance remains distinct from a faithful bare-metal architectural port.

## Identity Tables

The common scenario hash above and the complete manifest bind all
six files per case. These independent read-only identities enable a later
review to detect wrong shape, helper or selected fixture reuse.

| Shape | Reduced Linux ELF SHA256 | operations.S SHA256 |
|---|---|---|
| e16/m1 | `7e837e6e6e40cc15ba82987b558de44064883c18fc55c2a2af33e67b16a6abb7` | `6a5ad396eb3f7e89cf84dadfc63243100d99bae0ba2dbb9450a52a11f8cdfac3` |
| e16/m2 | `d993ec579b3181c26f34c395a0b7d481a088099bac4bb59723f51dec64ff0430` | `a4518c32429fc8cf73d71fda5b7f361e6b1c9ccfeb9c0e3a420ec42b62621de5` |
| e16/m4 | `9f6c1502db4c5a129d827a569fe384ee45ddc37df3ea5aac15df432a22477a61` | `b141a10141ec73f91c2f3529fc3771757f33d9d5722da9aa9c129baf3066b0d8` |
| e16/m8 | `0ae64336f9831a3ce659b229c81cad49b05af9a9704a56bb2ab00ac56d62b948` | `9336ee28a5dab2838ee5db6841356818e6161ec210311f561c82adaeb2072662` |
| e16/mf2 | `3b01c7eb7dcf1fa051f974ed373a6dc0336dec9fb63496925779ea9b1f04954c` | `468713e2051d76602d28b5a66ad5793535c965d536d8e0541a9f1087af25ad96` |
| e16/mf4 | `e92ac2c95a795eadca5cd4d5bab4f2d96b6152e59b52591caa497947b9646cdd` | `48a893837032d5e5affa5b5b649f935341e9800b3661cf38af2393d06505a9bf` |
| e32/m1 | `47020ea216c9a925116026e5f55290d6e1987004b844879552a0a296d0003704` | `64859679b372c4ab1f57e7c81d27af03eb41b727314fdf764e0bd342a9d68818` |
| e32/m2 | `4e2e2ee1037925ab9586c9558f6ee1d10fbf580629e652d25bbdb8a96280bd21` | `e0cd550e3bda450843973dcfcf60bccf73ab1132dee4722dcacb8e078c79b300` |
| e32/m4 | `a606ceca440289c0101db1653ba1eb32ecefcdfd1ed70f1d3ca6264cb19c40e3` | `8dcc1d0ecc1adcd089f94292962761ed205ff34cc0b6f0dc9632e21367865875` |
| e32/m8 | `e344aa242be82ab25d2e237e00aaf408d32716d932aade98e82ec90ebc604559` | `0384a741a0df1f4252d40e769dd2e8ddc73675f117f817c4e25aa12dbec02503` |
| e32/mf2 | `092bc664ecbaa804c4add2a5a3194f0c1f792c8fb0428473cee576befee704d0` | `b8b92cb61055eeed5d7c7f6081592a4d7c76e88698554ce75c7fe4aafcdd97c8` |

| Shape | fixtures.h SHA256 | fixtures.json SHA256 |
|---|---|---|
| e16/m1 | `88bbb3d5a1c7336d2699b1aa1097dfb1bbe8a1c738adfb5a5d82cfb2ea01cc1d` | `ab818bd5539bc53e4b3363b26fe5031b66eb2d1d285325b94fb3e6c7a6267074` |
| e16/m2 | `f2b54398292a10db0803e5be232041a1a46cc344cb852d9680767651845c1b37` | `4a31d6b036e7a853a99235a0e43a3c8165986520b5960ca75b15234b1c1ffa35` |
| e16/m4 | `038cf9a44ddceb4abf038b33b21bbf80e7b354368a7f1cd29a1d69babcf62b58` | `6bc9729f2852339c795d7aefb9b9390ab0da3b7615e7905065f18621e2484229` |
| e16/m8 | `b600d00df412bace58ac123c3f11c5a01313809fbecabda6c66074a70e99b3af` | `f25f223906befd223d0bde753d3c84fe64ca44736596dbf75d1195e3baebbf11` |
| e16/mf2 | `68a394a73fdfb4264fb8aa998766b47c003f49da21b06d2b32318fe964424fb4` | `58c4f694e67978f27b8375d764a7b732a415bb8849f5f9f63b76d1969582d1a9` |
| e16/mf4 | `a1f53ed5363cbe34bf1731a6a5e3602589fbd12d9c94e711be9a228f1602663a` | `7a76a6bb25d7764238de659aefdae5daad44a1a5be068ac94bce5442225d4d9f` |
| e32/m1 | `86e55544995f4677ddd1e6819f27d196a9ca697b2197b296481c03db15029a83` | `59bd5276e2306391784b16263818f725424392421bebc355b1db6c25cbebd53a` |
| e32/m2 | `02ce6d8aa50c817f649043af7992ee1102e48f740631ce0737ac1275639dcca0` | `3f37c75fcb787fa49d41d0e5eb7a25b7e0083264f0e37b32bd1d0910a945f686` |
| e32/m4 | `4d080cb0cd37371af0a86c480f0b7e2403ee87eadc5af64debd435aff4a3dd71` | `bdb778392c6f82b9d55514f8265fe4a7937cb439b8415395fe15e4e0546f0ede` |
| e32/m8 | `2a867afaec04564a541530d8ca8b10bc8e99a16a6060a00cb35d5d520597004c` | `76871ff3d536bf50aa761efac8a78fea031aaf2771123a5adea12f742ce9b4c9` |
| e32/mf2 | `88116a3574deaea00131682ec91d5d3c4c5eff178f6a0080d7071cf65db932c4` | `326b0addb52453af53ade00251ba4c052835a57a3f6b9f1de785d422b02ca2f9` |
