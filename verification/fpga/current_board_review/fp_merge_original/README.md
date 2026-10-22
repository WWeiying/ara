# Original FP Merge Prefix195

Status: **PREPARED_HOST_SPIKE_PREFIX195_PASS_NOT_DUT**. No DUT launch entrypoint,
RTL edits, or changes to shared/sealed helpers. All artifacts belong to this
new directory. `prepared01/complete.json` anchors its input/output pin ledger.

## Provenance And Boundary

Original: `rvv_fp_move_restart_e16_m8_ops0`, ELF SHA256
`d8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710`.
Both archived ELF copies match. The oracle, generator and floating input source
match their archived manifest hashes exactly, and original S/header generation
matches. Rebuilding the original complete partition with its original compiler
and flags produces the identical ELF, not merely a behavioral reconstruction.

The historical report is `rvv_failure_retest01/supervisor44/terminal_recovery257.json`.
All26 printed trial records match enumeration of the recovered source. Its
`completed=194` is printed before the call; the increment follows the complete
original oracle. Thus the requested boundary is call195 (zero-based194):

`seed=0 scalar=0 invalid_box=0 op=0 VL=512 mask=0 vstart=256 sticky=0`.

There are32 calls per VL position: four masks, four start positions, two sticky
states. Six earlier VL positions account for192 calls; calls192/193 have
start1 and sticky0/1; call194 has start256/sticky0. No duplicate VL/start tuple
was deduplicated. The prefix retains all194 preceding calls and stops only after
call195's complete original oracle. `prefix.diff` and `runtime.diff` expose the
only source changes: this stop and the entry/I/O/exit/tty-drain adaptation.

## Preserved Checks

Original op0 instruction bytes match the archived ELF in both prepared ELFs.
The assembly saves/restores fflags, loads the complete SEW16/m8 source and old
destination plus mask, loads the boxed64-bit scalar, sets VL/vstart and sticky
fflags, executes `vfmerge.vfm`, reads vstart/fflags, restores fflags and stores
the full512-element destination. The original oracle checks every destination
element, prestart/tail state, both guards, the untouched scalar-result sentinel,
returned vstart and sticky fflags. No oracle or input reduction was introduced.

The full host model covers21504 calls, including all scalar patterns and invalid
boxing, using independent integer bit-move semantics. The first195 full-run
input snapshots (source, old destination, guards, all128 mask bytes, control,
scalar and scalar-result sentinel) are byte-identical to the prefix snapshots.
Nine injected corruptions are rejected: active/prestart/tail/mask-zero-source
data, two guards, returned vstart, flags and scalar-result sentinel.

The actual prefix reaches only scalar0 (boxed +0), seed0 and valid boxing.
Invalid-box handling is preserved in source and checked by the full host model,
but is not claimed as executed Spike/DUT coverage of this195-call prefix.

## Reference And Cost

One bounded120-second Spike invocation completed with raw process rc0 and
architectural exit a0=0, exact original `cases=195 errors=0` and case/replay PASS
markers. Debugger sampling checks all195 real target executions: VL, vstart,
fflags, packed control and boxed ft0 before execution, then cleared vstart,
unchanged sticky flags, packed returned status and restored caller fflags.
Debugger sampling changes reference wall time, not the retired source sequence.

- Spike retirement delta: **3,382,750** (`minstret` 5 -> 3,382,755).
- Observed local reference wall time: **0.621859 seconds**, not DUT time.
- SoC target PC/opcode: `0x800005e6` / `0x5c805c57`.
- Original target PC/opcode: `0x10666` / `0x5c805c57`.
- SoC ELF SHA256: `01b9f6e58dec5ee13082e64211d23a37b94411d72051f517e3a0b46af479d124`.
- Spike ELF SHA256: `98a4eae64f271a4318d239fb5da4dc12fb0ba7e4a3aa9d29ecd5d3f35ff29778`.

No DUT runtime limit is inferred from Spike wall time. A later parent-reviewed
plan needs comparable measured M4 throughput, resource admission and explicit
inner/outer budgets. This preparation provides no authorization to launch it.

## Independent Review

Run `python3 -B verification/fpga/current_board_review/fp_merge_original/audit.py`
from the worktree for a read-only pin/source/ELF/raw-reference audit. It writes
nothing and invokes no compiler, Spike or DUT. `prepare.py` is fresh-output-only
and is not an audit command; do not rerun it against this existing preparation.

Acceptance scope remains the original ops0 partition's195-call source prefix,
not its full21504 calls, the separate parent ELF, historical Linux/tty/OS timing,
or proof of the internal cause of the archived no-retirement observation.
