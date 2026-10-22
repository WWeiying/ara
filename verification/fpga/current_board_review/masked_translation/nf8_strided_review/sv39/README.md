# NF8 Four-Tuple Sv39 Reference

Owned source-derived software fixture; no production RTL changes.
`reference.py` is reference-only and has no VCS entry point. The separately
authorized VCS adapter and recorded startup are documented below.
Four separately selectable ELFs retain original trial IDs in the
order 19, 17, 67, 31. They are representative original tuples, not recovered
exact failing tuples. Neither the original 169 errors nor the later 128 errors
is localized by this fixture. Full original coverage is 192 tuples.

## Source Binding

`reference.py` rechecks `../selection01.json` source/evidence hashes, the
identity57 C/generator manifest, and regeneration of the exact archived NF8
assembly. It independently enumerates all 192 original geometries, then selects
only the four authorized tuples. The original Linux ELF hash is
`c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282`.
Archived assembly hash is
`63c68bc8c2c935884520082cd423c51e9f14fb7caac7a42816026b9597acb8db`.

The build links an unchanged copy of that assembly, preserving v24..v31,
e32/mf2, VL8, tu/mu, masks, setup and readback. Its original instruction
encodings are e9c56c07/e9c56c27; PCs relocate in the bare-metal ELF. The
identity57 ledger binds the C/generator to a byte-identical original Linux ELF,
but these new executables are **not Linux execution**. Signal-frame ABI,
kernel context save/restore, and Linux fault delivery are outside this test.

Runtime, linker, and startup are the sealed NF2 Sv39 infrastructure. The local
adapter additionally derives whole-register snapshot and archived-assembly
linking from the accepted NF7 fixture. Both read-only ancestors are pinned.
No ancestor files are changed. The reference preparation invokes only the
software compiler and Spike; the separate VCS adapter reuses a frozen image.

## Fixed Cases

| Trial | Operation | Base offset | Stride | Mask | Expected page fault |
| --- | --- | --- | --- | --- | --- |
| 19 | load | 3948 | 44 | ff | cause13, vstart3 |
| 17 | load | 3972 | 36 | ff | cause13, vstart3 |
| 67 | store | 3948 | 44 | ff | cause15, vstart3 |
| 31 | load | 3948 | 44 | 00 | none |

Each has original unmapped=0, boundary=3, split=1. The second page has a
valid execute-only Sv39 leaf (flags c9), with MXR=0, so S-mode data access is
permission denied. This models the original ACCERR data-access distinction;
it is not a literal Linux PROT_NONE PTE encoding. A real M-mode handler saves
cause/PC/tval/status/satp/VL/vtype/vstart/fcsr/vcsr/PTE/younger marker. The
faulting instruction must have VL8/vtype23; archived readback ends at
VL16/vtype23. No-fault alloff completes without changing the denied PTE.

## Oracle Boundaries

- Preserve original memory/input formulas, field register spacing, all cap16
  words per field, old load destination 5b, mask and output guards at 0/129.
  Check the entire two-page physical backing, including stride gaps.
- At fault, require completed active prefix, source registers for stores,
  inactive elements and undisturbed tails. Faulting load segment partial state
  is deliberately unconstrained, as is later active load state not covered by
  the original prefix oracle. Do not require segment-atomic completion.
- Store fault-segment accessible fields may be either original or stored
  value, independently. Protected fields and non-target memory remain exact.
  A third value is rejected. No fixed field commit order is assumed.
- Accept tval only at a protected field of element3: VA+4096/4100/4104/4108.
  Repair that page, execute addressed SFENCE, poison completed active prefix
  memory XOR5b, and return to unchanged target PC with vstart3. Final data and
  prefix poison detect restart from zero or skipped restart work.
- Whole physical v24..v31 upper fractional tails plus neighboring v16/v23
  sentinel registers are additional checks, not claimed original Linux oracle
  coverage. All snapshot/page guards, mask/input/output buffers, page tables,
  CSR state and restoration are checked.
- `nx_firsterror[6]` is trial, phase, kind, index, got, want. Vector kind2
  index r*32+i maps r2..9 to v24..31; memory kind3 index is word offset.
  Phase1 is before repair, phase2 final, phase3 environment restoration.
  Checkpoints precede repair and follow full final checking; counts and magic
  distinguish functional completion from a partial trace.

Independent Python byte-state and target-access validation complements the
C scalar oracle. Host formula checks cover both phases of all four tuples.
Negative checks cover prefix/tails/guards/PTE/CSR/stride/mask/precise traps and
allow legal partial field states. Spike uses real Sv39, S-mode target accesses,
M-mode repair, and Zvl1024b. PASS means reference preparation only, not DUT PASS.

## Reference-Only Entry

Run only in a fresh child directory; `reference01` is already accepted and
must not be overwritten:

```sh
python3 -B reference.py --out "$PWD/<fresh-reference-directory>"
```

Each Spike process has a 90-second limit; this entry calls no RTL simulator.
Accepted artifacts record all software, source, compiler and runtime pins
before/after execution. The earlier preparation-stage requirement for future
VCS approval has been satisfied for the specific run below only.

## Authorized Candidate04 VCS Run

Entry: [vcs_adapter.py](vcs_adapter.py), with separate `preflight` and explicitly
authorized `worker` actions. It uses the existing integration `run.py` without
rebuilding or modifying the image, fixture sources, or accepted ELFs.

- Image: `/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image`.
- Service: `ara-nf8-candidate04-01.service`.
- Output: [vcs_candidate04_01](vcs_candidate04_01/).
- Scope: four independent SoC ELFs, original tuples19/17/67/31; at most two
  concurrent runners, each with one simv. Inner limit1800s per ELF; service
  outer limit5400s. Any failure cancels this batch's remaining work; no retry.
- Admission: accepted host/Spike results, per-ELF independent trace-oracle
  host tests and negatives, ELF/symbol checks, source/image pins and dry-run.
  See [plan.json](vcs_candidate04_01/plan.json) and the exact authorized service
  invocation in [launch.json](vcs_candidate04_01/launch.json).
- Recorded state: **LIVE_CONFIRMED_ONCE_NOT_PASS**, not DUT PASS. The one-time
  [startup observation](vcs_candidate04_01/startup_observation.json) confirmed
  actual candidate04 simv PIDs30782/30783 for trial19/17, each at cycle311,
  retirement order111, PC0x8000004a. This is the saved startup observation,
  not a fresh status query or a terminal result.
- Local stdout/stderr: [service.log](vcs_candidate04_01/service.log). Terminal
  result will be written to `vcs_candidate04_01/complete.json`; per-case
  oracle/checkpoint evidence is under `vcs_candidate04_01/cases/`.

Do not repeat this launch or poll the long-running service. NF7 and other
candidate04 controls are independent and remain untouched. This README update
does not inspect completion or count any VCS PASS. Even a later four-case PASS
would not identify the original169/128 discrepancy or replace full192 scope.
