# Continuous Original777 Scalar Optimization

Preparation and one Spike reference only. No DUT run or Linux replay has occurred.
The new M8 worker requires a pinned independent no-blocker review before execution.

## Source and Scope

- Canonical source: `../recovery01/`, original archive `rvv_fixed_restart01`.
  Original ELF SHA256: `ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
  The historical C bytes remain unavailable; surviving C plus original assembly
  and header rebuilt that entire Linux ELF byte-identically. This is the existing
  binary-equivalent source proof, not recovery of the missing historical C bytes.
- Derived from sealed `../prepared01/prepared/case.c`. The new
  `prepared01/prepared/optimization.diff` enumerates every scalar change.
- All 777 calls, including 776 predecessors and 480 `vstart>=VL` calls, execute
  in original order. The final call is seed0/op0/e8m4/VL512/mask0/start256/control0.
  Global RNG operations and loop order, all128 mask bytes, helper setup and
  source policy tu/mu are retained. No easier representative substitution.
- This remains seed0/op0 only, not original10752 calls or historical Linux closure.
  Earlier M4 single776/pair775_776 results are performance inputs, not this result.

## Scalar Cost and Equivalence

The original `-Os` disassembly has two byte initialization loops at
`0x8000050e` and `0x80000528`: 514+512 writes per call, 797202 total.
Its full512 oracle retains per-element generic branching, `selected()` calls,
and original `__int128` `extra_value()` arithmetic for 19560 active elements.
These are static source/disassembly counts, not an invented old dynamic profile.

The optimization retains `-Os`, disabling both automatic vectorizers. It uses
54 deduplicated deterministic expected rows and exactly64 scalar SD plus two SB
for initialization, then64 scalar LD plus two LBU for full comparison per call.
Each row covers all512 destination bytes and both guards. No hash-only oracle.
The original C scalar oracle independently checked all397824 result bytes and
1554 guards against the generated table. Original and optimized Host execution
each matched all777 inputs/controls. Nine data/guard/vstart/sticky-saturation
negative mutations were rejected, without stopping or shortening the history.

## Aliasing and Storage

- `out[1026]` is aligned8; its original helper argument remains `out+1`, not a
  newly aligned vector destination. Scalar word operations cover out[0..511];
  out[512] and out[513] are byte operations. They neither read nor write the six
  padding bytes of the last expected-table word into the real output.
- The scalar word typedef has GCC `__may_alias__`; accesses are volatile. The
  expected table is a real `uint64_t` array. The selected compiler is pinned,
  including its host/target little-endian table equivalence check.
- SoC BSS is `[0x800083c0,0x80009088)`, stack top `0x800ffff0`, gap1011560 bytes.
  Main's fixed frame is208 bytes; no recursion/VLA or footprint near the stack.
- Original capacity and all four helpers retain exact machine encodings in both
  new ELFs. op0 is24 instructions/90 bytes. All additional vector instructions
  are statically rejected. `code_identity.json` contains actual PCs/opcodes.

## One Actual Reference

`prepared01/reference01/status.json`: numeric child rc0, 19.4022076 seconds,
790055 firmware instructions to `replay_exit`, versus old16249331 (20.57x fewer).
Hard bounds were3000000 instructions,120 seconds,256MiB output; actual raw is
93275459 bytes. No second Spike invocation, budget extension, or software hint.

`bridge01.json` is the initial observer result. `bridge_setup02.json` strengthens
the same closed raw's setup verification; neither is a new reference execution.
The full raw has795055 retirements, including HTIF completion after the recorded
firmware endpoint. It proves777 continuous24-instruction windows, 51282 full
oracle loads, 777 actual returned vstart0/vxsat values,1554 saved-CSR restore
operands,1472 exact original RNG stores and8758 exact mask-reset/update stores.
All unused helper ranges have zero execution. No register is assumed zero merely
because its initial software tracking slot is zero: operands require known bits.

The program does not read vxrm/vxsat after the final restore. Restore instructions
and actual saved operands are checked; final restored CSR state is not directly
measured. A Spike bridge has no RVFI/CVX/uop evidence and is not DUT acceptance.

## M8 Checker and Run Contract

`check.py csv` checks actual opcodes, exact call arguments and history, complete
setup write sequences (not just leftover memory equality), original inputs and
mask128, full512+guards, returned CSR values and restore operands. Relevant
actual RVFI memory addresses, byte-enables and store data must equal independently
decoded addresses/operands; full output loads must equal the independent oracle.
CVX starts/requests/responses/retirements and backend owner alloc/done pair exactly;
all3885 compulsory full-capacity memory owners must allocate, not merely satisfy
an aggregate counter. The original M8 monitor and RVFI source are pinned.

`test_check.py` includes unknown operands, missing initialization, wrong inputs,
addresses/BE/data, oracle omissions, CSR values, unused helper interiors,
ownership errors, and deletion of one complete alloc/done pair despite aggregate
surplus. `vcs_m8_prepared02/host_exit.json` records the frozen Host subprocess rc;
the dryrun does not launch a simulator.

M8 image SHA256 `bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0`.
The inherited image gate checks all frozen inputs and explicit configuration
digest equivalence. New worker persists numeric simulator outcome before any
postcheck; checker exit is separate. No unknown rc, timeout, abort or pin drift
can be accepted, and terminal publication checks the sticky signal latch.

Budget estimate, not a guarantee: old M4's slowest selected case gives
542126/621.051587=872.916 cycles/s; measured full helper duration is3279 cycles.
Charging that duration for every call plus all790055 scalar/reference instructions
gives3337838 cycles,3823.8 seconds. A2x uncertainty allowance is7647.6 seconds,
below the fixed9000-second simulator budget. Service outer limit10800 seconds
includes postcheck/teardown. No automatic retry or budget growth is permitted.

Review entry: `vcs_m8_prepared02/READY.json` and its exact `plan.json`.
Worker preparation: `python3 worker.py prepare` (already prepared when READY exists).
Future launch uses `worker.py run --plan-sha256 SHA --review FILE --review-sha256 SHA`
in direct systemd unit `ara-fixed-full777-m8-01.service`, RuntimeMaxSec10800,
KillMode=control-group, Restart=no, stdout/stderr appended to a local service log.
Independent review must bind that exact plan and current unused reserved slots;
fresh admission enforces24 live/reserved slots and32GiB available memory.

The initial worker preparation `vcs_m8_prepared01/` completed Host negatives and
dryrun, then exited1 before plan publication: its pin collector passed a string
to a helper requiring Path. Those artifacts remain untouched. The narrow Path
conversion fix is prepared in fresh02, without a Spike or simulator rerun.
