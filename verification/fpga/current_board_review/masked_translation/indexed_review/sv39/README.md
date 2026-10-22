# NF7 Real-Sv39 Reference

Software-only source-derived adaptation, **not Linux ELF replay** and not a DUT
result. No VCS entry point, RTL edits, image build, or successor8 changes.

## Source Identity

Parent `../geometry01.json` supplies the pinned archived ELF, exact assembly,
current C oracle, generator and delivery evidence hashes. The adapter verifies
all identities and regenerates all 96 geometries before execution. The archived
assembly is copied byte-for-byte as `prepared/original.S` and linked directly.
The archived Linux executable is hashed, never executed as bare metal.

The current C oracle is not byte-proven to be the C compiled into the archived
Linux executable. This limitation remains explicit in each prepared provenance.
Original geometry and formulas are retained: NF7, e32/mf2, VL8, index EEW32,
v16, v24..v30, boundary 1/3/5, masks ff/aa/24/00, field split 0/3,
scrambled nonoverlapping indices, input `101+13*i+29*f`, memory `37*word+11`,
and prefix XOR poison 0x5b. At VLEN1024 each field capacity is 16 words.

## Grouping

24 fixed groups of four trials: group g contains original trials 4*g..4*g+3.
All 96 trials and all 72 expected faults are represented. No favorable-case
selection changes their formulas. `reference.py --groups` selects these groups
at build time, producing separate `soc.elf` and `spike.elf` per group; no runtime
hint changes an instruction, oracle, or test geometry.

The first measured four-trial reference has 1,098,601 Spike commits and 11,924
scalar checks. Spike time is not a VCS budget prediction. Do not schedule all96
as one SoC ELF. A future VCS plan must review this cost against measured SoC
throughput; further fixed subdivision can be prepared as a separately reviewed
successor if four trials exceed its agreed budget. No VCS is authorized here.

## Privilege and Restart

Real S-mode Sv39 uses two data pages, real three-level tables, and an executable
identity mapping for code and stack. Traps go to a private M-mode handler.
The cold-reset runtime supplies MXR=0. The ACCERR derivative uses an execute-only
valid leaf (`0xc9`), denying data reads/writes; the MAPERR derivative uses an
invalid leaf. This models the data-permission distinction, not Linux's exact
PROT_NONE PTE encoding or signal `si_code` machinery.

The handler checks cause, original target PC, VL8/vtype23, element vstart,
S-mode trap status, SATP, fcsr/vcsr, PTE, and lack of a younger completion marker.
It accepts only an original permitted protected-field tval. It snapshots full
registers, validates the completed active prefix, repairs the PTE, executes an
addressed SFENCE, poisons completed active prefix memory, and resumes the same
PC with the captured vstart. MAPERR also refills the restored page using the
original formula; physical allocation and Linux signal return are not modeled.

## Oracle Boundaries

- Fault-phase completed elements are exact. A faulting load segment is not
  assumed atomic; active fault/suffix register fields are captured but not used
  as strict intermediate gold. Store source registers remain fully exact.
- Accessible partial store fields may have committed before the fault. Their
  intermediate memory is recorded without requiring atomicity; protected fields
  and all non-target memory remain checked. Final memory is fully exact.
- Final load/store field results include all 16 original-capacity words and the
  full physical upper halves under tu policy. v23/v31 guards, full v16, seed,
  all 898 output words, 896 input words, 128 offsets, mask bytes, snapshot guards,
  both entire data pages and all page-table words are checked.
- Alloff must have no page fault or target accesses, retain its denied PTE, and
  preserve destination/memory. Physical M-mode checks require no premature
  permission restoration to inspect the data.
- Final vstart, archived routine's VL16/vtype23, fcsr/vcsr, trap count, completion
  marker, and restoration of machine/vector CSRs are checked. Full-group magic
  and one successful HTIF exit are required for reference PASS.

`ix_firsterror[6]` records trial, phase, kind, index, actual and expected. Phases:
0 setup, 1 fault, 2 completion, 3 CSR restoration. Kinds: 0 setup, 1 CSR/trap,
2 snapshot, 3 data memory, 4 PTE/guard, 5 buffers, 6 counts, 7 restoration.
The first error prevents subsequent trials. Trace extraction rejects a mismatch
call immediately and independently checks every scalar comparison, exact trap
sequence, S-mode target encodings/accesses, all checkpoint memory and restart
ordering. Field-partial validity is tested separately in `test_reference.py`.

## Evidence

- `reference01/host.json`: all96 host formulas, 467040 rows, independent Python
  against host C.
- `reference01/group00/status.json`: original trials0..3 Spike PASS, not DUT.
- Additional groups have their own status files under subsequent reference
  directories. A missing status or `failure.json` is not PASS.
- Every run retains prepared sources, Linux provenance, input pins, both ELF
  hashes, symbols/disassembly, raw Spike trace, checkpoints and negative checks.
- `host_tests01.json`: independent corrupted-tail/guard/PTE/index/vstart/prefix
  rejection and partial-field validity checks. No hardware coverage admission.
