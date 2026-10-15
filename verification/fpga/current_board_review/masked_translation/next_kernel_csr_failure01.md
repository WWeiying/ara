# Next Authentic Failure: Zero-Stride e64/m4 Full16

Static selection only, 2026-10-12. No compiler/reference/DUT/build/RTL changes,
no live-job queries, no new matrix or approval framework. This follows main's
latest instruction: prefer the strongest original vector-fault evidence and
retain the complete small program rather than guessing its unknown stalled
inner tuple. The inspected M6 source paths below still match frozen M6.

**One next program:** `rvv_fault_replay_strided_zero_stride_e64_m4`, all16
original configurations in order, one continuous process-equivalent replay.
Do not substitute the separately recovered e16 active-STORE single, split
the16 into reset jobs, infer the active historical trial, or call Sv39 PASS
closure of the original Linux/kernel stall.

## Actual Evidence And Source Identity

`C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`;
`R=/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`;
`G=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`.

The exact released, QEMU-reference and stopped-board ELF copies all hash
`f9ef7eecca757fe9f006a325e73fcd814afc89ea6b615afbd20fc357846b30ec`:

- `C/rvv_additions57/binaries/rvv_fault_replay_strided_zero_stride_e64_m4`
- `C/rvv_zero_stride_reference57/source_nf1_m4/overlay/opt/ara-tests/rvv_fault_replay_strided_zero_stride_e64_m4`
- `C/rvv_recovery08_41/terminal_scene/rvv_fault_replay_strided_zero_stride_e64_m4`

The recovery41 original report records this exact name as `stalled`, empty
output, error `Confirmed no retirement; scene preserved`. Snapshot cycles
41352661786 ->41936136756 advance while retired15459365213 and trap_count2012486
remain unchanged. Last/head PCs are0xffffffff80013a16/0xffffffff80013a18.
The accepted Image's actual bytes decode `add a5,a5,a4; csrr a0,vstart`;
then `csrr a1,vtype; csrr a2,vl`. Both DDR channels have zero outstanding/errors.
Head-PC has **no captured valid bit**: accepted CSR or VLSU transaction is
not proved by these PC values alone.

The strongest distinct fact is last recorded cause13 at **user PC0x10846**,
whose exact ELF word is **09c57c07**, `vlse64.v v24,(a0),t3,v0.t`;
tval **0x3f87fed000**. Source operands specify zero in the ordinary register
t3, not the special x0 stride encoding. This is an authentic vector-load
fault followed by a stopped kernel CSR boundary, not an observed store fault.

Source files are directly recoverable, not reconstructed substitutes:

| File | SHA256 |
| --- | --- |
| R/fault_replay_oracle.c | 631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a |
| R/fault_replay.py | 47765b894cde708521c8a32ce02539e9bd140ebc1be464824252817a05755ff9 |
| C/rvv_zero_stride_reference57/source_nf1_m4/manifest.json | e6db74adae36d24f3b450cbe06a3145751993b179367e31af8ada3d985887058 |
| C/rvv_zero_stride_reference57/source_nf1_m4/rvv_fault_replay_strided_zero_stride_e64_m4.S | 12de337c732da7a81b8ff584cc2a5cbdfda030cfda0cac7645a39e3065e5aff0 |

The first two current files exactly match that original manifest's source
hashes. Original helpers: capacity0x1082a..0x10830 (3 instructions),
load0x10832..0x10856 (10), store0x10858..0x1087c (10), target store0x1086c
word09c57c27. Preserve all23 actual helper instructions, ordinary t3 stride,
post-target vstart reads and full-capacity output stores. Also account for
the **three compiler-generated RVV setup instructions** at0x104c6/0x104ca/
0x104d8 (e64/m8 VL3 initialization of sigaction storage). They are in the
actual original ELF despite disabled tree vectorization; do not silently
declare all original RVV confined to the hand-written helper.

Existing exact-ELF QEMU Linux references each record rc0,
`RVV_FAULT_REPLAY_PASS sew=64 cases=16 signals=12 errors=0`:
`C/rvv_zero_stride_reference57/reference_512.json` SHA
fe8d7e4a3a82d5af25693234c47d73ce6d525738df15307764def4d089321abb;
`reference_1024.json` SHA
52d12ba16fe8ca66f455a38b9f6e1a0c0fae5f1ce38907a15a9d1ae881530796.
These are historical QEMU results, not a newly executed Spike reference or
M6 proof. A faithful SoC/Spike adapter and its reference are not prepared yet.

## Original16 Scope, No Invented Warmup

Loop order in original C: unmapped0..1, store0..1, boundary0 only, mode0..3,
split0 only. Therefore0..3 are protected LOAD,4..7 protected STORE,8..11
unmapped LOAD,12..15 unmapped STORE, each maskff/aa/24/00 in that order.
There are8 load and8 store calls,12 expected faults (6 each),4 all-off
nonfault cases. No extra predecessors or external batch warmup are proved.
The exact stopped inner trial remains unknown; all16 are retained to avoid
guessing it. This does not promise to reproduce Linux scheduling history.

At VLEN1024, e64/m4 capacity is64, VL8, tu/mu, vtype26, initial vstart0.
Target is P=mapping+4096, stride0. Expected fault starts by mask are0/1/2,
with no fault for00. Fault address stays P, making vstart/predicate ownership
essential: a correct address alone cannot detect an inactive-element fault.

Retain original physical arrays and typed values: input512 uint64 entries
(first64 initialized101, remaining storage originally BSS), output514
uint64 entries initialized **0x5b**, offsets512 with original unused-index
setup, mask64 bytes with the selected repeated mask. Output pointer is+1;
original guards are elements0/65, not513. Preserve full1024-word8KiB initial
memory formula37*i+11, both page permission/unmap modes and each refill.
Do not truncate these to the existing e16/m1 fixture's128-element arrays.

Per-call original final oracle: all64 outputs, both guards, all1024 memory
words, one/zero expected fault, exact target PC/address/start/VL/vtype and
returned vstart0. Across16 this is1024 output elements,32 original guards,
16384 full-memory word comparisons and16 returned-vstart checks, in addition
to handler/context checks. Loads place original(P)=18955 in active elements
below8 and retain0x5b elsewhere. Stores retain all64 source values101 and
change only memory[P] to101 when active. The duplicate-store inputs are
uniform intentionally: do not invent distinct per-element values or claim
the source oracle counts every physical memory transaction.

Every expected fault is the first active access; prestart elements are all
inactive. Thus the original active-prefix poison loop makes **no writes**.
Do not import negative-stride prefix127/poison36/retry166 into this test.
Both kinds of unmapped cleanup refill the upper page, including all-off
post-check cleanup:8*512 uint64 refill stores total. Original fault-time
saved-vector checks cover only its prestart region; do not impose extra
unchanged post-fault suffix constraints as though they were the source oracle.

## No Duplicate Acceptance Or Store Attribution

CURRENT_SCOPE still leaves kernel CSR waits/3 and segment alignment/9 open.
Its NF2 current-M6 full40 and NF7 current-M6 full96 are different geometries;
indexed-overlap and the now-accepted negative STORE/LOAD are not stride0.
`G/masked_translation/sv39_extended/REFERENCE_REPORT.md` selects only e16/m1
protected masked zero LOAD and all-off zero STORE. It explicitly excludes
active zero stores, other widths/LMULs and unmap/remap. No exact e64/m4
full16 current-M6 acceptance was found in that ledger. This is not a rerun
of the accepted negative STORE or of an existing zero-stride full program.

The original3 stall/store association was checked separately:

| Scene | Last recorded trap | Supported conclusion |
| --- | --- | --- |
| recovery12 e64/m2 | kernel0xffffffff80b8754e, scalar `sd t3,48(a0)` | Does not identify a vector STORE or active inner trial. |
| recovery41 e64/m4 | cause13, user0x10846, masked `vlse64.v` | Strongest direct vector-fault evidence; select its full16 program. |
| recovery76 e64/m8 | cause15, kernel0xffffffff80b8759e | Not proof that the target was a vector STORE. |

The genuine e16/m1 active STORE single u1/s1/b0/m2/f0 does exist and reports
vstart0 instead of2, but main's latest priority supersedes selecting it here.
Do not use its failure to explain any of those three kernel scenes. Likewise
the segment9 phase-store/vlseg3 boundaries lack active geometry/acceptance;
they are not substituted with an arbitrary aligned segment single.

## Current RTL Risk And Falsifiers

Live dispatcher/sequencer/AddrGen/VLDU/VSTU hashes were compared with frozen
M6 and all five are equal. Existing repairs are present, not proposed anew:
AddrGen:604..633 selects predicate owner/element;924 onward emits inactive
skip descriptors without translation. VSTU:454/460 suppresses W and B-count
increments for skips;578 waits for the owning pending-B count zero, discards
faulted operands and reports done even if no W beat occurred. Sequencer:989
latches the faulting load's own done;1025..1029 waits for it before fault
response and for the owning store completion. These already address plausible
old causes; **no current-M6 root cause is proved by the old snapshot**.

The residual causal chain is falsifiable: fault descriptor -> owning consumer
cleanup/done -> global running-mask empty -> WAIT_IDLE_FLUSH -> CSR response.
Dispatcher:1239 still waits for ara_idle before flush;4661 still waits for
idle before vector CSR access. Capture actual valid/ready/VID and CSRs, not
only a head PC. On failure distinguish:

1. Incorrect first-active translation/start0 vs1/2: predicate coordinate,
   descriptor elem_start/is_skip, exception_vstart and unchanged target P.
2. No-W fault cleanup: VSTU issue/commit owner, pending_b, exception_pending,
   operand/mask drain, pe_resp done; or VLDU exception queue/final-grant drain.
3. Consumer done but global not idle: MASKU running/remaining mask entries,
   sequencer running IDs, dispatcher WAIT_IDLE_FLUSH/lsu_ex_state and CSR
   request/response handshakes. Do not equate VLSU local idle with ara_idle.
4. Correct response but bad context/retry: first actual vstart/vtype/vl CSR
   values, same target MRET, saved group v24-v27 and the complete final oracle.

Aquinas separately reported an unmeasured masked multi-maskword cleanup
candidate. This program's VL8 does not exercise a third mask word; do not
inflate its acceptance or alter its VL to cover that hypothesis. Keep such
work source-bound and separately authorized.

## Bounded Preparation Next

Reuse the existing real-Sv39 fixture/observer read-only in one new owned
adapter. Preserve16-case order without reset partitions; keep original setup,
full arrays/oracle and group v24-v27. Replace only Linux services with actual
Sv39 permissions/unmap/repair and saved-context return. Read vstart/vtype/vl
immediately after the real exception, before diagnostic vector instructions,
matching the observed kernel CSR order. Keep MRET at the original relocated
target with t3=0 and precise start; no helper re-entry. This probes the
internal chain, not Linux signal-frame/sigreturn equivalence.

Original compiled-code cost is tractable, but not yet a bound on the new
firmware. Main memory loop0x10666..0x107c0 uses at most8 logical-address
iterations per1024-word scan. Nonmatching address path is about141 retired
instructions/word including the9-instruction element-address subroutine;
16*1024*141 =2310144. Initial fills plus8 remap fills add245760 at12
instructions/word;514 output seeds/call add24672. Output/context/setup and
the one matching address path give roughly2.7M **user-body** instructions.
Linux syscall/kernel cost is excluded; Sv39/checkpoint overhead must be
measured after compilation. This is not a claim that the port already fits
an approved reference limit.

Comparable measured M6 negative STORE:851704 retired/1111.624556s =766.18
retired/s. A3..5M firmware envelope at that rate plus20% is about78..131min,
below3h; this is a proxy, not a promise. At the historical slow273/s the same
range exceeds3h, so do not present a guaranteed budget or enlarge timeouts
after launch. First compile source-faithfully, inspect actual loop bounds,
then use one prebounded Spike reference with numeric wait receipt/full raw
and source/helper proof. If the port cannot fit a reasonable fixed <=3h DUT
budget, report that before launch; do not trim16/history/oracle.

Immediate deliverable should be one software/reference preparation, not a
matrix service: exact original ELFs/source/provenance, original helper and
bootstrap-RVV accounting, all16 ordered tuples and full independent oracle,
bounded reference cost and actual exit. Main reviews those before any M6 run.

## Evidence Receipts

Primary static references: `R/repro/ALL_FAILURE_REVIEW.md` SHA
c72e20fc1f85d6ca670c9b182dac85bf366c141dbe79d890e57f71282a54caaf;
`R/repro/STALL_TRIAGE.md` SHA
da22b7f558a327ef14312e4a06aac58e464e06867e0c2f363becbfccb667e8a7.
Current-scope snapshot inspected before concurrent main ledger updates:
355bc50ee9c69f0b18c866f142e583d1a01932c81f0cfd91c9218dd98c2ed61e.

Accepted-Image evidence is in `C/rvv_recovery41_zero_stride_annotation01/`:
summary.json SHA52c77bd9d5fbf221fe99f1c14c68ba7df2068dac62bd118471b0a67e059a45e9,
kernel_window.txt, elf_window.txt and accepted_image.config. Original scene:
`C/rvv_recovery08_41/terminal_scene/{report.json,hashes.json,batch_progress_0001,batch_progress_0002}`.
The summary binds Image716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285
and report21ee51538fd44b4591476f4edcf6e7e1afd1d8bbe4235b6e66a8d124936b31da.
Do not disassemble this kernel PC against a different current vmlinux.
