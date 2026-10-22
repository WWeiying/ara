# Scalar Move Candidate03 Review

## Final Measured Status

**Candidate03: 11/11 PASS**, using the exact four original port02 ELFs and seven
supplement01 ELFs. Independent audit: [candidate03_audit01/finding.json](candidate03_audit01/finding.json).
The four formerly failing cases now pass the full original oracle, and the seven
baseline-passing controls have byte-identical complete commit traces, including
all recorded cycle fields. This is focused scalar-move acceptance, not a rerun
of candidate02's38 arithmetic programs or the original full Linux partition.

The separate VCS build completed in114.37 host seconds; serial replay totaled
319.07 host seconds. These wall times are not processor performance claims.
`ara-fp-moves-candidate03.service` terminated successfully; no jobs remain from it.

| Previously failing case | Before issue/write cycles, BE | After issue/write cycles, BE | Result |
| --- | --- | --- | --- |
| FP original start1 | 6849 / 6850, 0x00 | 6849 / 6850, 0x03 | PASS |
| Integer plain start1 | 6863 / 6864, 0x00 | 6863 / 6864, 0x03 | PASS |
| FP stored EW64, start17 | 6879 / 6880, 0x00 | 6897 / 6898, 0x03 | PASS |
| Integer stored EW8, start1 | 6879 / 6880, 0x00 | 6897 / 6898, 0x03 | PASS |

Both mixed-layout cases now accept exactly one target-owned VSLIDEDOWN maintenance
at6877: vs2=vd=v24, internal VL64/start0, target EW16, register limit0. It completes
at6892; the scalar request is accepted at6894 and writes element0 with BE0x03.
The architectural CSR start remains17 or1 during that maintenance; it is not
prematurely reset. Stored EEW changes from64 or8 to16, and the full-capacity oracle
confirms that the remaining bytes and both guards are preserved.

Normal-cycle preservation covers original FP start0/start==VL/VL0, integer plain
start0, FP old64 start0/empty, and integer old8 start0. All seven whole trace hashes
match their candidate02 counterparts. The18 required extra cycles on the two
previously broken mixed-layout paths are distinct from these unchanged controls.

The independent audit rehashed251 distinct run/input/image pins with zero drift,
and separately checked all539 files in each frozen snapshot. The only changed
production source is dispatcher; `frozen.filelist` and the frozen Bender adapter
also differ because their absolute snapshot paths were relocated. Each launch
satisfied the24-simv cap including NF7/alias reservations; minimum observed
MemAvailable was186194640896bytes. No other agent's job was stopped or altered.

- Image: `/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image`
- Image ledger SHA256: `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`
- simv SHA256: `d7c37b993c8af577f00578dacff3cb9af4ea250fae95e1bfece7df33213bbd66`
- Snapshot SHA256: `382af2912634002ceecbaa44b8e8f0fb8262ab6aeb30e52d66a9bb0268508a2f`
- [Raw11-case terminal record](candidate03_after01/complete.json)
- [Integer before cycle proof](integer_before_cycle01/finding.json)
- [FP old64 after proof](candidate03_audit01/fp_old64_restart/finding.json)
- [Integer old8 after proof](candidate03_audit01/int_old8_restart/finding.json)

## Static Scope

The parent's candidate changes only the VMVSX and VFMVSF decode blocks in
`hardware/src/ara_dispatcher.sv`: both set the **internal request** vstart to0.
The architectural CSR and the `csr_vstart_q >= csr_vl_q` no-op gate are unchanged.
Reviewed dispatcher SHA256:
`05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd`.
All other `hardware/src/` files matched the sealed candidate02 snapshot at review.
This agent made no production edits.

## Destination Layout Audit

1. Decoder defaults preserve CSR state; scalar decode changes only the internal
   destination interval to `[0,1)` for a nonzero architectural VL. Neither scalar
   insertion uses a vector source. The integer scalar and FP boxing paths remain
   unchanged. Normal arithmetic, slides, and reductions retain their own starts.
2. The layout gate around dispatcher5349 checks architectural CSR start/VL before
   starting any reshuffle. Thus start==VL and VL0 still bypass both scalar execution
   and layout maintenance, even though the speculative request start is0.
3. Destination reshuffle uses `active_group_needs_reshuffle` and
   `active_register_mask`. With internal `[0,1)`, only relative register0 of vd is
   selected. Even though `single_register_result` does not explicitly list these
   scalar moves, this interval makes the register selection correct without
   broadening any LMUL or layout classification.
4. VL1 is not a full physical destination overwrite for these e16 cases. The
   full-overwrite shortcut therefore does not bypass old-tail preservation.
   If stored EEW differs, `prepare_reshuffle` gets base vd and limit0; the existing
   full-register conversion preserves all128 bytes before the two-byte insertion.
   RESHUFFLE transitions to WAIT_IDLE after the final conversion, so the held
   scalar request cannot consume the new layout until the conversion drains.
5. The late EEW update uses the committed `layout_req` interval. With `[0,1)`,
   only vd is tagged e16. Before the fix, internal VL1/start1 or start17 selects
   no register, skipping both destination conversion and useful scalar byte enables.
   No new source snapshot, overlap replay or adjacent-register conversion is needed.
6. The pre-existing blocked-decode helper remains unchanged. The measured profiles
   include decode_blocked, pending reshuffle, base/limit, and old/new EEW so a
   repeated-maintenance claim would require real accepted uops, not held decode.

These arguments establish a coherent two-line repair boundary, not acceptance
of every possible scalar move. The focused runtime checks have now completed
as recorded above; the audit below preserves their original scope.

## Supplement Definition

All seven derivatives retain the original C oracle, complete capacity readback,
vstart/fflags sampling, scalar sentinel, and both guards. The integer variant
changes op6's `fld ft0` to `ld t3` and `vfmv.s.f` to `vmv.s.x`; low16 scalar bits
remain0. No other original function is modified.

Stored-EEW tests keep the original full e16 loads, then run a full-register
`vor.vv v24,v24,v24` under e64 or e8 before restoring e16. This is a real public
instruction sequence, not forced metadata; it changes the stored physical layout
without changing architectural bytes or adding unaligned load assumptions.

| Supplement | Old stored EEW | VL / start | Purpose |
| --- | ---: | --- | --- |
| int_plain_restart | 16 | 2 / 1 | Prove integer same cause on candidate02 |
| int_plain_start0 | 16 | 2 / 0 | Integer normal-cycle control |
| fp_old64_restart | 64 | 18 / 17 | Element0 insertion despite a later lane-local start |
| fp_old64_start0 | 64 | 18 / 0 | Existing destination reshuffle/control cycles |
| fp_old64_empty | 64 | 18 / 18 | No-op must not trigger new destination maintenance |
| int_old8_restart | 8 | 2 / 1 | Integer insertion across another stored-layout direction |
| int_old8_start0 | 8 | 2 / 0 | Integer destination-layout normal-cycle control |

Host oracle/mutation checks:21 PASS. Spike:7 PASS, using the same Zvfh-enabled
reference as the original four. Exact source deltas, original identity, target
addresses, ELF hashes and commands are in `supplement01/`.

## Before Evidence

`candidate02_supplement01/int_plain_restart` reproduces element0 expected0,
actual0x7bff, exactly one error; start0 control passes. The integer opcode is
420e6c57 at SoC PC0x800006ec, ELF SHA256
`d91f91d0e17097217da82551ce51772ca73f84efa79aae24285e95a347450097`.

`integer_before_cycle01/finding.json` confirms internal VL1/start1 at backend
cycle6860, VALU issue6863 with data0/BE0, and result handshake6864 with BE0.
There are no target-owned maintenance requests. This is measured integer
same-cause evidence, not inference from floating-point output alone.

`fp_old64_before_cycle01/finding.json` confirms the layout setup really establishes
stored EW64 (encoding3). The old target accepts internal VL1/start17 at6876,
issues with data0/BE0 at6879, and handshakes at6880. No destination conversion
occurs; its stored tag remainsEW64. Full scalar checking reports the same single
element0 error. This distinguishes skipped insertion from tail corruption.

## Executed Acceptance Plan

Freeze to `/home/wangwy/fpga_runs/current_board_memory_candidate03/frozen`,
build a new VCS image under `campaign/image`, and leave candidate02 immutable.
Require completed baseline7 and the measured integer BE proof before building.
After building, replay the **identical original four port02 ELFs**, then these
seven supplementary ELFs, serially with 180 seconds per case. Check global24
simv slots, reserved NF7/alias slots, and MemAvailable>=32GiB at every launch.

Capture the original FP, plain integer, FP old64 and integer old8 targets without
rebuilding for probes. Require target acceptance, nonzero two-byte write enables,
correct actual data, and full original oracle PASS. Mixed-layout targets must
convert exactly the first destination register and preserve all other bytes.
Compare full commit traces of the seven baseline-passing controls for unchanged
normal/no-op cycles; added required maintenance on previously broken paths is
not a normal-path regression. Do not infer whole-family or Linux acceptance.

The freeze/build/replay runner is `candidate03.py`; it does not edit RTL. Results
are written separately to `candidate03_after01/`, never into old before artifacts.
