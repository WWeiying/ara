# STORE M6 combined input and worker review

Decision: **NO BLOCKER FOUND FOR FUTURE PARENT ADMISSION. NOT LAUNCH APPROVAL.**
This combines the sealed source/reference ENTRY with static worker/CSV-checker,
actual ELF marker, prepared-plan, and existing Host/dryrun evidence review.
No DUT, Host, reference, compiler, service or live-resource query was executed.
No CSV/reference raw was parsed. Producer and existing ENTRY files are unchanged.

## Exact bindings

Producer: `../negative_stride_store_vcs_m6_plan01/`.

| Artifact | SHA256 |
| --- | --- |
| READY.json | a2ead20f220931d684a16f7b5aa2900ab651045f4b81584c0c479bde6881fa01 |
| prepared01/plan.json | ea7add04987278b6c92bdcb720663ee5689021b26384f23111204b6938ed7a81 |
| replay.py | 7739e9f16ee05a18fb90acebf98fdc7266ec88340338b7eac52f0e24e8bb45bb |
| checker.py | 92ac01900766b116e8c8a589b8abab054b83801624d82fad38e24f0d03f570f8 |
| csv_check.py | ea1884f31ea747b7a60f3deb6860bbfed8d63e22bc2559df67d4a8f08931f8cf |
| ../store_entry_review01/ENTRY.json | e8f1d31fcf521c988178e20ac07052329d7cb654d66795f2274b03db68e6e55e |

All692 plan pins were hashed and matched, retaining all66 original reference
pins and both actual ENTRY artifacts. The M6 snapshot membership is all539
files, image membership all66 files. Image SHA is
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`;
configuration SHA is
`6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785`.
The shared image gate explicitly verifies configuration, source manifest,
snapshot, image files and frozen runner import root, not merely image.json.

## Discriminating actual marker check

The existing SoC ELF SHA remains
`bdeaefcb2a25106578d2c78ca4bcb30f634dc73db9a4be03ac1607f2989235fb`.
Actual PT_LOAD bytes contain these NUL-terminated strings:

- PASS: `NEGATIVE_STRIDE_STORE_SINGLE_PASS\n`, VA0x80000fe8, file offset0x1fe8.
- FAIL: `NEGATIVE_STRIDE_STORE_SINGLE_FAIL\n`, VA0x80000fc0, file offset0x1fc0.

The saved, pinned disassembly shows main selects PASS at0x80000b7a or FAIL
at0x80000b84, then calls replay_text at0x80000b88 after mx_completed and the
full checks. The prepared case's sole pass_markers entry is the actual PASS
string. `checker.console_gate` requires exactly one such line and rejects
FAIL/MISMATCH; it does not require BOARD_CASE_BEGIN or BOARD_CASE_PASS.
Those two strings are absent in this ELF, and neither inherited oracle path
requires them: integration/run.py:44 uses the explicit pass_markers list,
so its default BOARD_CASE_PASS branch is not taken.

SUCCESS/tohost=0 and $finish are simulator/TB output, not invented ELF markers.
Frozen hardware/tb/ara_tb.sv:1543 prints the exact SUCCESS string and :1558
calls $finish. The SoC checker requires the original CTRL0 exit, not the
Spike reference's HTIF1. No synthetic BEGIN-marker admission issue was found.

## STORE checker and full oracle

The frozen source observer remains the source of the full byte-map oracle,
not a LOAD result substituted for STORE. csv_check.Checker requires the actual
SoC PC/encoding, ten-instruction store window and full unused-load exclusion.
The faulting target may have an optional RVFI trap row; it is not required to
produce the eleven commit-format records seen by Spike.

RVFI does not expose vector write payloads. The checker invalidates only the
expected written bytes when the target completes/faults, then requires actual
scalar observations. Other bytes retain their prior known state, so a real
inactive write is rejected when observed. It checks prefix127 before snapshot
fence/repair, PTE installation/SFENCE, all2048 refill halfwords, full phase2,
same-PC retry with baseP+22/stride-8/start5, final retry166 and poisoned prefix36.
Source v24 remains input data across fault/retry; output64 and its two original
guards, extra physical sentinels, snapshots, mask/offsets, page tables and
all four ordered4096-halfword reads remain required.

All17275 scalar comparisons and fixed checkpoint counts4117/8451/12564/17053
are checked, with actual handler CSR reads compared to stored records. Final
done magic, original full output-read order, CTRL0 and closed CVX state are
required. No reference result is used in place of observed DUT data.

Each store backend allocation/completion is paired by architectural order and
VID. The handler cannot enter with a pending store or without a completion for
each observed target owner. Generic trace validation additionally checks the
request/allocation/completion protocol and one CVX exception. This is evidence
of backend completion plus architectural prefix visibility, **not direct AXI
B handshake or arbitrary delayed-B coverage**. The code and result labels keep
that distinction explicit.

## Worker failure and outcome gates

- Exact runtime TESTCASE is distinct from the historical name; the adapter
  validates both then changes only the copy passed to shared command checking.
  Seed1, private ELF, working directory, image and full command are exact gates.
- Actual monitor numeric returncode, timeout/failure/abort and command SHA are
  persisted with fsync before inherited postchecking. The separate unvalidated
  child outcome is persisted before strict checking; neither is a PASS label.
- Abort during checking remains sticky. Terminal requires exact one-case
  COMPLETE/PASS, no abort, consistent summary, pins and image. The deadline
  timer is cancelled/joined and elapsed deadline rechecked before publication.
  The shared publisher checks latched/pending signals before atomic replace;
  its save function supports overwrite of its pending file, unlike the earlier
  unrelated exclusive-save failure pattern.
- Jobs1; simulator5400s, worker7200s, service7800s. The direct service must own
  MainPID and cgroup, with Restart=no, KillMode=control-group and local append
  logs. No rebuild/retry/automatic budget extension is present.
- Missing exact new parent authorization refuses run. ENTRY itself explicitly
  does not grant launch. The fresh launch gate counts live simvs plus this job
  and unused reservations against24, with32GiB available-memory minimum.
  The sealed plan reserves0 additional unstarted external jobs: parent must
  account for any new reservations at admission; this review made no live scan.

## Existing tests and review limits

Reviewed without rerun: metadata Host12/12, synthetic CSV213559 rows/17275
checks with16 negatives rejected, and dryrun with actual DRY_RUN/null child
returncode. These are checker/plumbing tests, not DUT success. Negatives cover
missing completion/prefix, wrong fault opcode, output/tail/guards, wrong retry,
missing checkpoint/CTRL and prefix replay. Synthetic rows are not a measured
instruction count or performance estimate.

Independent pin/membership verification completed exit0 in3.04241892s, tool
chunk94b232. An earlier scratch membership lookup used an incorrect assumed
`frozen/repo` path and raised KeyError; using snapshot.json's actual `root`
(`frozen/sources`) completed the review. No producer change or test rerun was
involved. Actual ELF-marker verification also completed exit0 (chunkae66d9).

Input/reference acceptance remains exactly the single described in ENTRY.md,
including its original96/Linux exclusions. No source/oracle weakening or
additional launch approval is introduced here. Parent can now bind this exact
plan and review in a separate authorization after its resource/budget decision.
