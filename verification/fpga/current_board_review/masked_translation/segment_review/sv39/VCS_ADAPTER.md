# NF2 Candidate02 Preparation, Not Launch Authorization

Historical preparation contract below is preserved. Parent subsequently supplied
explicit review and ran the pinned worker: four-case DUT terminal PASS is recorded
in [DUT_REPORT.md](DUT_REPORT.md). No adapter or preflight changes were needed.

Only the four reference-accepted NF2 cases in `reference01/soc.elf` are in
scope. No C/S changes, recompilation, production RTL edit, new matrix, or
simulator launch is part of adapter preparation. The two b3 cases are genuine
archived failed singles; the two b5 later-field cases are historical passing
trials selected from full-sequence source. See `REFERENCE_REPORT.md`.

## Immutable Inputs

- Image: `/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image`.
- Frozen snapshot SHA256:
  `b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9`.
- simv SHA256:
  `6fcdf53ecf2df4526e9d35372ea6bf9d2c49fdd2fc7a6bc3b57044124aeb13b7`.
- Unmodified `reference01/soc.elf` SHA256:
  `2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67`.

Preflight verifies all 539 frozen sources, the compiled source manifest, image
file membership and all image hashes, configuration, OS/PMP geometry, accepted
reference input pins and six prepared files. Symbols are checked against nm
of the actual accepted ELF; ELF entry and LOAD layout are checked without
compilation. Original archive provenance and adapter/tool/helper identities
are retained and pinned. Worker repeats identity checks before and after use.

## Timing And Launch Gate

One runner case `nf2_segment4` contains four architectural subcases, not four
independent invocations. Its inner runner wall timeout is **2400 seconds**.
Reference measured 1,189,205 Spike instructions; the supplied extended8
observation of 740,000 instructions/1200 seconds gives a rough 1928.4-second
linear estimate, not a performance guarantee. No cycle threshold is treated
as functional failure by the observer.

The proposed independent service has **RuntimeMaxSec=3000**, TimeoutStopSec=60,
and KillMode=control-group. The 600-second difference permits runner teardown,
CSV analysis and final input verification; the service must not use the same
2400-second ceiling as simv. A service command is generated as JSON but never
executed by preflight. There is no polling loop or automatic launch on status.

Before a future worker can start, parent must explicitly authorize a review
record matching the preflight hash, image metadata hash and accepted ELF hash,
confirm no overlapping use, and record extended8 disposition plus immutable
evidence path/hash and review note. A reviewed timeout or failure is recorded
as such; it is not relabeled PASS. The generated template has authorization
false and disposition PENDING, so it cannot launch. CLI also requires
`--authorize-run`. This preparation does not supply that authorization.

## CSV Acceptance Contract

The observer requires all four cases in order, eight checkpoints, eight trap
records, correct target PCs/opcodes, actual handler CSR reads matching stored
records, fault PC unchanged, explicit vstart5 restore, addressed SFENCE after
leaf repair, both-field prefix poison before retry, later-marker ordering,
correct post-target VL/vtype/vstart/fcsr/vcsr, completion magic and CTRL=0.
Default trap or mismatch-diagnostic execution is an immediate failure.

Vector stores are not scalar RVFI writes. The observer therefore does not
pretend to reconstruct the full vector snapshots independently from CSV.
It verifies the pinned firmware scalar oracle at every `check` entry: actual
a0 must equal actual a1, and call counts must match each fault/final checkpoint,
case completion, and final firmware total. That firmware checks full both-field
data/tails, neighbors, guards, both data pages and all page-table entries.
The independent Python memory oracle was already checked against host/Spike.

Counts for the observed reference path are 300/302/300/302 at fault checkpoint,
756/758/756/758 per completed case, and 4133 total. The original oracle permits
b3 fault address P+6 OR P+8. Its unchanged C handler explicitly skips one
`check` call when P+8 is reported, so observer counts decrease by exactly one
for each such b3 case, and only when the actual matching CSR/record establishes
that branch. No final-data check is waived. b5 requires fault address P.

Some CVA6 monitors omit faulting instructions from retirement CSV; handler
mepc is mandatory evidence of fault identity. A successful target retirement
after retry is mandatory. If a trapping target retirement is present, its
exact opcode/site is checked and separately recorded, not counted as success.

Final DUT acceptance additionally requires the sealed runner's successful
single-case result, exact executed ELF/image input hashes and run invocation,
one firmware `SEGMENT_SV39_PASS`, no firmware FAIL, and observer PASS. Missing,
partial, timeout or truncated evidence never qualifies as PASS.

## Offline Verification

`test_vcs_adapter.py` builds synthetic complete CSV scenarios, including the
alternate legal b3 fault-field branch. It tests deliberate mismatched firmware
comparisons, missing checks/checkpoints/target/SFENCE, bad PC/vstart/mask/PTE,
missing field1 prefix poison, corrupted completion, malformed/truncated CSV
and unmasked opcodes. Review-gate negatives cover missing authorization,
pending disposition, overlap and identity/evidence mismatches.

It also checks scalar-store decoding on an archived real CSV, including
unaligned byte-lane positions. Those observations validate decoding only and
are not NF2 DUT coverage. Offline synthetic positives are not RTL PASS.

Preparation command (never executes simv):

```sh
python3 -B verification/fpga/current_board_review/masked_translation/segment_review/sv39/vcs_adapter.py preflight \
  --out verification/fpga/current_board_review/masked_translation/segment_review/sv39/vcs_preflight01
```

Preflight runs host negatives, writes pinned `programs.json`, and invokes the
sealed runner without `--execute` to verify a DRY_RUN. Only later parent review
can authorize the separately defined worker/service path.
