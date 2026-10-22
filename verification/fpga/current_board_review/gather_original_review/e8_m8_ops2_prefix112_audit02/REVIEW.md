# Independent VI0 Prefix112 Reference Acceptance, Audit02

## Decision and Scope

**ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT.** The explicitly authorized second
complete offline parse passed. No DUT/Spike execution, old Host rerun, build,
live query, production edit or sealed-input modification was performed.
Only the requested new pure-park gate controls and offline parsing were run.
Work stops with this report; this is not DUT launch authorization.

Exact scope: original112 VI0 calls and all111 predecessors, cap1024, first
seed/scalar-slot only. Seven VLs x four mask modes x four original start trials
are retained. Not full2688, original Linux execution or proof of the unknown
historical stalled tuple. No numerical oracle, source or ELF was changed.

## Preserved Failure and Park Correction

Audit01 failed because its reviewer-added condition forbade any record after
successful HTIF. It did not establish an architectural result failure. Original
audit01/script and attempt01.json remain unchanged, hashes respectively:
`896445fd68f96b673ccbef66259be671500186d0856c1ffce252777d5d2a5207` and
`fe8baae29f501260f46a691f13f32450da69e6f7e69ce8c973fdfd417fecf569`.

Audit02 independently disassembles the unchanged Spike ELF's replay_exit:
HTIF store `0x8000007a:00a2b023`, then self-loop `0x8000007e:a001`.
After the original successful store, only a complete core0/privilege3 record
with that exact park PC/encoding and no side-effect fields is permitted.
Other PC/encoding, GPR (including x0), vector, floating-register, CSR, memory
read/write, trap, other core/privilege and unparsed records are rejected.
[park_negatives.json](park_negatives.json): one positive and **13 rejected
negatives**, completed before the full parse. The same script hash is required
for both phases; exclusive parse_started.json prevents an automatic repeat.

The existing full oracle, source setup, target, return-CSR, old5M-prefix and
5050000-step checks remain. Successful HTIF must additionally be the actual
original ELF store. Park records are counted separately, not hidden or counted
as firmware work, and still count toward the unchanged5050000 total ceiling.

## Exact Measured Counts

| Independent raw observation | Count |
| --- | ---: |
| Total commits through successful HTIF value1 | 5002737 |
| Boot records, PCs1000/1004/1008/100c/1010 | 5 |
| Firmware commits through HTIF | 5002732 |
| Subsequent original pure-park commits | 2263 |
| Entire raw commit count, including boot and park | 5005000 |
| Original calls / retirements of each of13 helper instructions | 112 /112 |
| Full-cap result bytes / guards | 114688 /224 |
| Distinct actual LBU oracle reads | 114912 |
| Zero returned-vstart / helper vset return-and-CSR checks | 112 /336 |
| Original capacity vset, return1024/vtype3 | 1 |
| Full vector input/result/store checks | 112 each |
| Initialized source/index/predicate/output values per call | 4226 |
| Active selected results185 / preserved results91 | 6319 /108369 |
| Raw bytes | 327291090 |

Allraw5005000 is below5050000. Recorded reference execution was8.289970975s,
process exit0, ISA rv64gcv_zvl1024b;120s/805306368-byte limits were unchanged.
This review did not execute Spike. Three software PASS markers were rebuilt
from committed console stores and exactly matched runtime.log; failure/trap/
DETAIL/mismatch markers are vetoed. HTIF value1 is the reference runtime's
success encoding, not the SoC runtime's CTRL convention.

## Original Source and Full-Span Evidence

Archive child rvv_permute_restart_e8_m8_ops2, recovery172, ELF cc5015d9...b1d712,
original shared C b6e5fa03...65ec5ca and mask4 selection are verified against
manifest and retained originals. Independently reconstructed source diffs permit
only the established baremetal wrapper and exit after complete call112 oracle.
Both original112 software ELFs are reused unchanged; all13 helper encodings
match the archived Linux ELF. No whole-Linux byte-identical rebuild is claimed.

Target `30803c57` is masked VI0, not VX: original PC0x10600, SoC0x8000071a,
Spike0x8000077a. Actual a1 is ordinary byte indices, a6/t3 remain0, imm0 is
independently decoded. Raw1024-byte v8..v15 source matches independent64-bit
xorshift13/7/17: source0=185, source31=177. Raw unused index group, old-vd,
full1024-bit predicate, requested VL/vtype3/vstart, complete target result and
each of1024 vector-store address/value pairs are checked, followed by full
scalar readback and both guards. This does not infer internal DUT handshakes.

Each VL0,1,2,3,512,1023,1024 has all16 original calls. Four mask modes are all-on,
odd, i%7==2 and all-off. VL1024 starts remain1,512,1023,1023; duplicate starts
are original, not deduplicated. Four256-bit chunks of the **actual architectural
predicate** and active-element counts are retained per call in audit.json:

| Call | VL/start/mask | Selected counts across chunks0..3 |
| --- | --- | --- |
|97|1024/1/all-on|255,256,256,256|
|98|1024/512/all-on|0,0,256,256|
|103|1024/1023/odd|0,0,0,1|
|112|1024/1023/all-off|0,0,0,0|

Last tuple `[0,2,0,6,3,3]`, raw target line4988643/firmware-retired4988638:
all four predicate chunks are zero; all1024 results, including element1023,
and both guards preserve91. These are software-visible raw facts, not measured
MASKU packed-word transactions or ready/valid timing.

## Old Bound and Stored Controls

The same new-raw traversal independently hashed bytes through exactly5000000
commits: **327020339 bytes**, SHA af0735ff3e02120d96dd93cd79f157a5ed754a62731a6f1a4ec5d0548fe7d5b3,
identical to old raw. At that point all112 helpers had retired, firmware count
was4999995, oracle reads114832 and last-call reads946. Missing were78 results
(elements946..1023), both guards and successful HTIF. Completion takes2737
additional commits. Old NOT_COMPLETED_WITHIN_BOUND remains valid and unchanged.
The producer phrase 'first5M bytes' denotes bytes through5M commit records,
not literally5000000 bytes; the exact byte count above removes that ambiguity.

All410 input pins and22 successor artifact pins matched. Admission05c5c38d...
authorizes only one reference successor with5050000 steps (+1%), unchanged ELF,
120s and768MiB, not a DUT bound change. The successor checker is byte-identical
to the old checker except this ceiling. Its retained Python compatibility
preflight error is not relabeled as a Spike run or discarded.

Old Host12 logs/fixtures, including upper-active768, final-active1023 and
final-inactive1023 negatives, were hash-checked and compared to the independent
oracle, not rerun. Successor7 stored negatives (old5M/noHTIF semantic projection,
wrong encoding/result/both guards/vstart/missing oracle) were inspected and
hash-checked, not rerun. Old raw was hashed but not reparsed in audit02.

## Identities and Budget

| Artifact | SHA256 |
| --- | --- |
| Successor READY | `e6962c38c215ec69ec0f0b3aaf5ebadaa9fb33341027a6c8d7f31fba0f135520` |
| Unchanged SoC ELF | `a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74` |
| Unchanged Spike ELF | `93cfba245d048b057891ed94db7feacac71cd41a2076569de4d130c9917e0f78` |
| Full new raw | `d193e349e23df14e39c6e58671748849bbba3688f30f012c0cca3aff02b91ba6` |
| audit02/audit.py | `0e1921e942127fbf64321755cf05c52f723f033947fc56bf96bb04a029153d55` |
| audit02/audit.json | `e4fa3b3850826cec964014821c9e497917df60c86542d7a08f2e603f4be1ed5b` |
| audit02/park_negatives.json | `8d93a76b6e40f4a9456687a7e3821b1e2996f1f61838ef072117e96f36fbe271` |

DUT throughput is unmeasured for this112.5002732/273 estimates18325s,
21990s with20% margin. Conditionally using the separately parent-reported M6
e8VX rate (2672460 retired/4052.291789s) estimates7586s, or9103s with20% margin,
already slightly beyond the unchanged9000s case budget. Different operation,
estimate only, no completion guarantee, automatic enlargement or launch approval.
