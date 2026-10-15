# Independent M6 e16/mf4 Terminal Acceptance

Decision: **ACCEPTED for this original reduced single only.** No new discrepancy found.
This is independent offline DUT evidence acceptance, not another reference/Host/DUT run.

## Identity and Terminal

- Canonical source: `ara_hw_campaign_20261007_01/rvv_verified_handoff03/rvv_small_redspecial02/rvv_small_fp_redspecial_e16_mf4`. All six prepared C/assembly/header inputs are byte-identical to that canonical single. All three helper instruction windows are compared directly between original and SoC ELF bytes.
- M6 image.json SHA: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
- Private/original SoC ELF SHA: `eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`.
- Active plan02 SHA: `51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c`.
- Terminal complete.json SHA matches parent's exact `c8db1b3ab326c64c2ee00384490ffa02724494487fb65a4591b5693d520507a1`.
- Actual file hashing before and after analysis: all 733 old-plan pins and 738 current-plan pins match, including 539 frozen sources and 66 image files. Combined explicit proof/evidence/plan map has 758 unique pins, unchanged. The old plan remains NOT_ADMITTED_CHECKER_GAP, not an executed PASS.
- Configuration digest is explicitly equal to `6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`; snapshot and VCS source-manifest digests also match. Private ELF, command, inputs image map, and run membership agree.
- Exactly one child result: rc=0, elapsed=3470.2008835258894 s, below 5400 s; retries=0; aborted=false. run.json is marked COMPLETE with one PASS, completed_at populated; summary equals complete.results. No firsterror/firstfailure artifact or leftover complete.tmp.
- Both raw console and run.vcs.log independently satisfy exact source oracle, BOARD_CASE/BOARD_REPLAY markers, Core SUCCESS and `$finish`; failure/DETAIL/firsterror/timeout/cancel vetoes are clear. The existing time-zero RT-NCMUCS startup warning is retained, not erased.
- Parent review SHA `654588cda1cd24f52b212fc7f7554185f47618e0f9432ccf8936b1c4e0267605` matches recorded invocation and authorizes this exact plan/unit. Historical launch.json SHA `03a0a7ee8f7ce93c08ce4bd91071918ac9faebb96b8b3b73f7e99cb521335b6c` recorded PID877501 in the exact service cgroup, KillMode=control-group, Restart=no, outer6600 s.
- **Outer service terminal exit/result is UNKNOWN in this audit.** launch.json records active startup only. No live query or GC-based default rc0 was used. Accepted rc0 above is the recorded simulator child exit, corroborated by its raw `$finish` and architectural exit.

## Single Complete CSV Reconstruction

`audit.py` imports the pinned sealed checker, validates specification encodings against actual ELF bytes without disassembly/compilation, and parses the original CSV exactly once. Its independent observer yields each same row object, unfiltered and in order, then asserts every field is unchanged after the sealed consumer returns. It independently checks transport ordering, initialization values/addresses/order, fixture fields, output bytes, helper ordering, CSR source operands, exit and actual PC encodings.

- CSV SHA: `ac6032665cdb4f72c038c2671cb80af300fcb7591da2e619c616d5dc443f8023`.
- All **1,853,358 original rows** delivered and unchanged; before/after ordered row digest both `52da42636f889ec01dbd0b2f7bde36fa7e2052c2f0a7af9ac75bc74916e78acd`.
- 1,853,301 retirements, contiguous orders; cycles82..2565009; every actual retired PC/encoding matches the private ELF. No architectural trap or CVX exception.
- CVX15 requests/15 responses; architecture15; uop6 allocations/6 completions; no outstanding IDs, duplicate/replayed requests, or unknown events. RVV11 retirements; generic vector classification additionally includes four vector CSR accesses, hence15 rather than11.
- Exactly one capacity3 sequence, VLMAX16, vlenb128; seven original legal startup/C CSR instructions in order, before capacity. No extra vector/CSR instruction outside the allowlist.
- Exactly one uninterrupted original op0 window, all21 instructions. Target `vfredosum.vs` PC80000704/code0c881c57 at cycle1187998, retirement858939 (one-based), CSV line858986. Both entire unused op1/op2 address ranges have zero retirements, not just zero entries.
- Initialization is fully checked, not just counted: 128 input word stores (8 scenarios x CAP16), 512 seed word stores (8 x64), 215040 mask-byte writes (3360 x64), and144 output initialization bytes. Selected setup is alternating +Inf/-Inf input, +Inf seed, mask0x24, original oldvd/guards0x5b, VL8/CAP16.
- Original bank1's3360 fixture rows produce6720 ordered field reads with correct address, load width/BE, destination and numeric value. Selected row1545, flattened4905, is bits7e00/flags16, not bank0's7c00/flags0.
- All144 result bytes are actually read and compared: bytes8..9 are00/7e; all142 other bytes retain0x5b, including126 old destination tail bytes and both8-byte guards.
- Actual DUT reads return fflags16 and vstart0. For restoration, DUT CSV establishes only that the original frm/fflags restore instructions retired with their saved zero-valued source operands x29/x30. There is no post-restore CSR readback or internal CSR signal observation in this DUT evidence: the final restored frm/fflags values were NOT directly measured. Discarded rd=x0 return data is not a restored-value readback. Spike reference CSR logs do not extend the DUT observation scope. This is an evidence limitation, not a finding of a restoration bug; no new readback or run was added.
- Architectural CTRL exit0 at PC8000006e, cycle2565000, order1853294; six subsequent original parking retirements only. No extra target call or premature exit.
- Entire reconstructed generic and strict dictionaries equal sealed producer JSON, not merely their PASS labels. Independent offline audit cost195.307 s; no guest program or Host suite was executed.

## Scope and Outputs

This accepts M6's authentic e16/mf4 scenario3/l4/mask3/frm0/op0/sticky0 source-derived single with complete original helper, setup, skipped-loop history and144-byte oracle. It is not execution of3360 targets, the full6720 parent, all11 records, Linux replay, other shapes, or a newer workspace/image. CSV directly establishes the full144-byte scalar oracle and original CSR read results (including NV16/vstart0), plus retirement/source operands of the restore writes; it does not directly measure post-restore CSR state, vector payload ports, or internal waveforms.

- Machine result: [result.json](result.json), SHA `4df2aa1282ff39e702db2964ffd6730909955e36f3aebe939a2da54b69e00020`.
- Exact verified map: [verified_pins.json](verified_pins.json), SHA `19fc344afacd01d9ab76b9073f55acb7c1b09ce4f782004920f57ebb4eb1013c`.
- Independent reader: [audit.py](audit.py), SHA `99a8136cf242064ab3cff31b8f036ba1d14b0765e4822f662e43fd17ebf4631a`.

No production RTL, sealed helper, source, reference or DUT output was modified. This report does not authorize a followup run.
