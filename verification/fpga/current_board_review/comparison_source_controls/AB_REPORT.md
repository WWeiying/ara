# Same-ELF FP Source-Origin A/B

## Measured Outcome

| Frozen program | Candidate03 console | Candidate04 console | After wall seconds |
| --- | --- | --- | --- |
| vv_restart16 | FAIL, errors=10, flags=1, start_after=0 | PASS, errors=0, flags=1, start_after=0 | 38.64 |
| vv_start0 | PASS, errors=0, flags=1, start_after=0 | PASS, errors=0, flags=1, start_after=0 | 44.14 |
| vf_restart16 | FAIL, errors=10, flags=1, start_after=0 | PASS, errors=0, flags=1, start_after=0 | 44.14 |

These are new independent finite-value controls, not historical original
program closure or a new cycle-level cause capture. The reference/oracle,
source, assembly, and ELF were unchanged between images. No RTL edits, image
builds, or FSDB were performed by this task.

The candidate04 terminal is [PASS_3_SAME_ELF_CANDIDATE04](vcs_candidate04_01/complete.json).
All three runners finished COMPLETE/PASS with simulator and runner returncode0,
exact one-case oracle/pass markers, firmware tohost0, and no failure-marker
veto. An independent postcheck reread raw logs, summaries, commands, private
ELFs, and image identities; all1177 plan pins matched. `+NO_FSDB` was present.

Candidate03's old wrapper labels the two failures NOT_ACCEPTED / Incomplete
runner: integration run.py sets its cancellation flag after a failed single,
which labels the batch INTERRUPTED even though the single finished and printed
its numerical FAIL and firmware tohost1. This is not missing numerical
evidence. The original files remain unchanged. The separate
[baseline terminal audit](baseline_terminal_audit01.json) verifies FAIL/PASS/FAIL
from raw consoles, input/image identities, final summaries and completion
timestamps, without relaxing candidate04's strict PASS gate.

## Oracle And Performance Boundary

The tests check all1024 destination mask bits with explicit architectural tail
alternatives; all64 elements of both sources; all128 predicate bytes; memory
guards; pre/post VL, vtype, vstart, frm, vcsr, and fflags. All values are finite
FP16 ONE/TWO. Expected flags retain NX=1 exactly. Active predicate bits16..31
contain10 enabled positions; golden truth at each index differs from index+16.
The baseline aggregate10 errors is consistent with the shifted-source model;
the fixture does not print per-category baseline counters, so this report does
not claim a separately decoded per-element baseline trace.

The zero-start complete commit CSV is byte-identical between candidate03 and
candidate04: 3,136,949 bytes each, including cycle fields. Thus this control has
no observed cycle regression. Wall times above are not RTL performance metrics.

## Frozen Identities

Reusable manifest: [soc01/programs.json](soc01/programs.json).
Target PCs/opcodes: [preflight01.json](preflight01.json).

| Program | Target PC / opcode | SoC ELF SHA256 |
| --- | --- | --- |
| vv_restart16 | 0x800005b8 / 60881c57 | `8f0376e877154ff4f4fe91e3cbac6fe909003a67c1b55277061f73834d3f336d` |
| vv_start0 | 0x800005b6 / 60881c57 | `7dcc44f98b0a593f8f1abf67fcb9bc9e2a3e91b630dc19a070308dd00fe1ff22` |
| vf_restart16 | 0x800005ac / 60805c57 | `732e45ef1fe697a6a20fecbf7d525c89036d6bac3932ca98607bcb47442812b4` |

- Candidate03 image ledger SHA256:
  `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`.
- Candidate04 image ledger SHA256:
  `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- Candidate04 terminal SHA256:
  `94752530eec94133fa60c61104f5b726127650899879767603d512f7e4ece8e1`.
- [After plan](vcs_candidate04_01/plan.json) pins both snapshots, unchanged
  software/helpers, baseline evidence, and the independent candidate04 wrapper.
- Host156 checks and Spike3/3 PASS preceded both DUT runs. Spike ISA was
  `rv64gcv_zvfh_zvl1024b`; the nonzero-vstart probe also passed.

Candidate04 used jobs1,180 seconds/case, outer900 seconds, independent output,
and the same failure-veto checker. One admission inventory observed total3
live/reserved slots with184.04GiB available, below cap24 and above32GiB.
