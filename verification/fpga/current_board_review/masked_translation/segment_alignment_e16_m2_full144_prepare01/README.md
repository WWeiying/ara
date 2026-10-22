# Original E16/M2 Segment Alignment: Complete144 Preparation

Owned software preparation under `segment_full144_preparation_contract01.md`
(SHA `380cec4b5848831d0ee7ddb532efc02b064233834939780c5c1ca151a7ad2b63`).
No 12-call prefix, DUT invocation, RTL edit or image build. Future DUT must use
explicit frozen M8 identity; this preparation is not an M6/M8 acceptance.

## Exact Source And Conversion

Canonical source/ELF/assembly identities are in `software01/source_proof.json`.
Original `rvv_segment_alignment_e16_m2` ELF SHA
`cfcdabf6e7a378d789c01dde8864e4beb16a133712090e805841cb24648db1df`
matches source archive, additions32 and recovery37 copies. Original C and
`segment_alignment.py` match the canonical manifest. Archived `operations.S`
and `operations.h` are used directly; the currently different transitive
`segments.py` is not used to regenerate the helpers.

Retain all144 configurations in original op/reverse/offset/VL/mask order:
eight helpers, NF3/4, unit and positive/negative stride, offsets0/1,
VL0/1/128, active/all-off, capacity128. Both original phase stores, staging,
mask load, target, vstart return and readback remain. All eight helpers and
the three capacity instructions match actual original ELF machine code.
Added target labels do not emit bytes. The port ELF is deliberately different
from the Linux executable; no claim of whole-ELF equivalence is made.

The original deterministic byte formulas are generated into immutable ROM.
Exactly41 distinct full8192-byte expected buffers are deduplicated without
omitting any case. With input/load-memory tables, ROM payload is352256 bytes.
`mx_reset` uses only scalar64-bit loads/stores to initialize all8192 bytes of
input, memory, output and expected, plus all128 predicate bytes before every
call. Intermediate bytewise construction of expected is replaced by its
identical pre-target image. No added vector verification instructions are used.

`mx_compare` reads all1024 actual and expected words on each numerical path.
Unequal words are decoded in increasing byte order, retain the original
first-error byte/value pair and count each bad byte. A nonzero returned
vstart remains a failure even with equal data. Bytes outside the active
fields, including all original guards/tails, are part of the8192-byte oracle.

## Isolation And Capability Semantics

Each call resets all data, so child stores cannot contaminate later cases.
The Host test deliberately poisons every buffer before each reset. Real
Sv39 S-mode executes the original helper with explicit page tables; the
M-mode observer records actual cause/PC/tval/VL/vtype/vstart/phase/return.
This is not Linux clone/COW, demand paging, signals, scheduling or vector
context restoration. The historical phase-store page fault is not forced or
claimed reproduced; that Linux-specific gap remains open.

Only target-PC load/store misalignment (cause4/6 matching direction) with
offset1, VL>0, active predicate and phase1 is a permitted capability branch.
Staging/readback/phase-store traps, page faults, wrong direction, VL0/all-off
traps and unexpected completion traps fail. A terminated-child path has no
invented numerical readback or successful return-CSR record. The port keeps
source exit77 when any allowed capability outcome occurs, distinct from
all-numerical exit0. The expected total is144;96 are no-active configurations,
and24 are eligible for (but not required to take) the capability branch.

## Host And Linked Evidence

`software01/host.json`: actual Host PASS,144 cases;4,718,592 initialized bytes,
18,432 predicate bytes;1,179,648 positive oracle bytes;7776 negative checks.
Two independently organized byte/halfword source models agree for all144.
Negatives include each scalar byte lane, guards/field ends/tails, multiple
errors/first byte, vstart and target/phase/cause/all-off/VL0 gating.
This is software equivalence evidence, not vector hardware execution.

SoC ELF SHA `087f4490b3363f93b48a55f63a14cb90ea87bf9daea7244dc046c69814d9f4cb`.
Spike ELF SHA `97f4b48e9c50b4b43852c7b0c4b13093c68cc8bc3398a20bdf275170af9935e1`.
Linker enforces a1MiB image region with at least64KiB stack space. Actual
stack gaps are626504 bytes (SoC) and618304 bytes (Spike). No ELF rebuild is
needed to perform the prepared reference.

## Reference And Budget

`software01/bound.json` derives the emitted reset loop's23 instructions/word
maximum and equal-comparison path's14 instructions/word. Including4000 other
instructions/case and150000 startup/exit reserve gives a success-path upper
estimate6,181,872. This is a reference admission estimate, not a DUT timeout
or proof that every failure-path execution completes.

Exactly one reference attempt uses `rv64gcv_zfh_zvfh_zvl1024b`, real M/S and
Sv39, eight-million instruction ceiling,120s wall limit and1.5GiB raw limit.
No retries or automatic limit increases. `reference01/attempt.json` and
`input_pins.json` pin the actual command, ELF, checker and transitive scalar
decoder before execution. `execution.json` persists actual child wait status
before the separate bounded600s raw audit; `audit_wait.json` persists that
process's actual exit. Any first failure remains in its original artifact.

The one-pass checker verifies every retired firmware PC/code, scalar memory
address/value/sign extension, every original contiguous helper window, full
initial byte images, target arguments/CSR, actual target attempts and trap
ownership, full numerical words and final HTIF source exit.

The sole actual Spike invocation completed in99.146s, numeric exit77,
without timeout; immutable raw is666779691 bytes. The original checker
rejected an unknown initial callee-saved register spill; its first successor
then rejected Spike's partial target-status row immediately before a genuine
target misalignment exception. Both errors and actual failed audit exits are
preserved. `recovery01/ROOT.md` and `ROOT02.md` document the narrowly scoped
corrections, actual raw evidence and Host negatives. No reference was rerun.

`recovery01/fullparse02/result.json` is the completed corrected raw audit;
`actual_wait.json` records actual offline exit0, not an inferred process
outcome. All144 helpers/targets and288 checkpoints were checked:120 numerical
cases (983040 oracle bytes),24 allowed target capability cases and96
no-active numerical cases. All pre/post pins are unchanged. This is
`REFERENCE_FULL144_CAPABILITY_COMPLETE`, not144 numerical passes, independent
review acceptance, Linux historical acceptance or DUT acceptance.

Measured firmware count is5172628 commit/status records, including24 explicitly
listed partial fault-status rows;5167722 records precede parking. These counts
must not be described as all fully retired instructions. `READY.json` binds
the actual exits, source proof, Host results, full result and evidence hashes.

Use measured firmware cost to evaluate the later <=3h M8 admission. The prior
zero16 proxy is689 records/s and negative-store proxy766/s, not guaranteed
for this scalar-heavy workload. The slower273/s proxy can exceed3h even after
optimization. For the measured count, the two closer proxies plus20% give
approximately135-150 minutes, excluding observer cost;273/s plus20% gives
approximately379 minutes. The <=3h target is therefore plausible at the
closer measured rates, not guaranteed. Independent source/reference review
and parent M8 admission remain pending. No VCS launch is authorized by a Host
result or this README.
