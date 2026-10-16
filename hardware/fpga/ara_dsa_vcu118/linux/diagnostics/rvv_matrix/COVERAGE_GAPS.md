# RVV Coverage Review

This is a coverage audit, not an ISA certification or a list of confirmed
hardware bugs. The campaign leaves RTL and the accepted bitstream unchanged.
Immutable failures and reference-only results must remain distinct.

## Supplemented

Additions21 covers 21 integer vx operations at 22 legal SEW/LMUL shapes:
logic, shifts, signed/unsigned min/max, multiply/divide/remainder,
reverse subtraction and high-half multiply. Five scalar boundaries include
zero divisors and signed division overflow. Additions22 covers four integer
multiply-add/subtract operations in vv/vx form, with the old destination in
the oracle. Together these add 44 ELFs and 89320 configurations per reference
VLEN. Both VLEN512 and VLEN1024 pass; board execution is separate.

Additions23 adds 22 shapes for arithmetic/logic signed immediates -16/15
and unsigned shift immediates 0/31 (29568 configurations). Additions24
adds 66 unmasked encoding tests for scalar, multiply-add and immediate
families (118888 configurations). The same four v0 patterns are loaded
but must not affect any active result, including when v0 is all-off.
Both reference VLENs pass; these are pending board results, not acceptance.

Additions25 adds 44 data-result and mask-result carry/borrow ELFs (40656
configurations). Vector/scalar and legal immediate forms distinguish carry
input from execution predication; mask outputs also cover no-input encodings.
Reference arithmetic uses full-width intermediates for carry/borrow bits.
No reserved unmasked data-result or subtract-immediate forms are generated.

Additions26 adds 22 merge/move/gather/slide ELFs (309792 configurations).
It distinguishes v0 selection from predication, passes full-XLEN indices
and offsets, and checks out-of-range gather/slidedown and untouched slideup
prefixes. Three seeds, eight scalar boundaries, seven VLs and four masks
include VL=0 and all-off predicates. Gather-ei16 loads EEW16 indices where
legal; e8,m8 excludes that opcode because index EMUL16 is reserved, while
other operations still execute in that shape. Both reference VLENs pass;
aliasing, floating slide1 and nonzero restart remain separate coverage.

Additions27 adds 44 integer multiply-add/subtract ELFs with five old-destination
patterns: zero, all ones, sign-bit boundary, alternating bits and varying
per-element values. All eight vv/vx operations run in both masked and unmasked
encodings at 22 legal shapes (246400 configurations per reference VLEN).
The oracle uses the actual old destination for accumulation and destructive
multiplication, and checks its preservation in inactive/tail elements.
Both VLEN512 and VLEN1024 pass. Board execution is queued after additions26;
source/destination aliases and multi-instruction dependency chains remain gaps.

Additions28 adds 15 FP16/32/64 packed-comparison ELFs (268800 configurations).
Four vv and six vf encodings use pinned SoftFloat boolean/exception fixtures,
32 distinct input rotations, seven VLs, four predicates and two initial
fflags values. Inputs include signed zero, subnormal, infinities, quiet and
signaling NaNs. Only active comparisons contribute exception flags; mask
tails admit old bits, ones or the permitted VLMAX comparison results.
FP16 scalar sources are explicitly NaN-boxed. Both reference VLENs pass;
hardware execution is queued after additions27. The fixture table covers
all 16x16 pairs, but runtime rotations do not claim exhaustive pair coverage
at every shape/VL. Unmasked encodings, aliases and scalar/vector moves remain
separate gaps.

Additions29 adds 15 bit-exact FP16/32/64 merge, broadcast, masked/unmasked
slide1 and scalar/vector move ELFs (559104 configurations). Sixteen scalar
patterns include raw quiet/signaling NaN payloads, subnormals and signed
zero; FP16/32 use valid and invalid NaN boxes. Merge consumes v0 as a
selector, unmasked moves/slide1 ignore it, and masked slide1 preserves
inactive elements. Scalar extraction must run at VL=0 and return a boxed
raw element; scalar insertion must not write at VL=0. All operations must
preserve initial fflags, including signaling NaN transfers. Both VLEN
references pass; board execution is queued after additions28. Nonzero
restart, register aliases and physical fractional-group tails remain gaps.

Additions30 adds 60 FP comparison ELFs (1075200 configurations): an unmasked
release with four ignored v0 patterns, and masked releases writing v8, v16
or v0. The overlap oracles derive old destination bits from the loaded vector
source or predicate, not a sentinel that was never loaded. Different-EEW
source overlap permits inactive one bits when VL>0; VL=0 remains unchanged.
The vf/v16 case does not overlap an actual vector source and retains ordinary
mask-undisturbed checks. All four releases pass both reference VLENs and are
queued after additions29. Unmasked-plus-alias combinations, nonzero restart
and invalid scalar boxing are not implied by these passes.

Additions31 adds 15 FP merge/broadcast, slide1 and scalar/vector move restart
ELFs (2236416 configurations). Start points are one, half VL, VL and the
last capacity element; some boundaries coincide at small VL. FP capacities
are below the maximum integer VLMAX, so these starts are representable.
The oracle checks preserved prestart elements, end/beyond-VL no-ops, fflags,
guards and cleared vstart. Scalar extraction still reads element zero at
any start; scalar insertion writes element zero only when start<VL, including
nonzero starts. These scalar rules are tested separately from the normal
vector prefix rule. A small drained first-merge trace helps identify a stall.
Both reference VLENs pass; hardware execution is queued after additions30.
No result here repairs or covers the known arithmetic/memory restart stalls.

Additions32 adds nine target-only segment-alignment diagnostic ELFs (3816
isolated child scenarios), separate from independent coverage ELF counts.
NF3..8 legal groups test unit and positive/negative stride, aligned and
boundary-offset target addresses, VL=0/1/VLMAX and all-on/all-off masks.
Staging and readback use aligned buffers. Shared phase stores bracket only
the target instruction, so a preparation fault cannot masquerade as target
misalignment. SIGBUS is an optional-capability result only for an active,
misaligned target at phase1; no-active faults, aligned faults, other signals
and numeric mismatches are failures. Unsupported cases produce exit77 and
never count as board passes. Both reference VLENs pass; board execution is
queued after additions31. Other index EEWs and fault/restart remain gaps.

## Remaining Checks

### Original ELF Numerical Completion

`rvv_original_partition_gap_audit01/gaps.json` reconciles all original2767
ELF identities with their selected board report outputs, rather than treating
every terminal exit as a complete numerical result. There are97 originals
without completed numerical markers:87 stalled and10 signal-terminated.
The FP-move and extension follow-ups map to28 of those originals by exact
parent name/hash. They do not supersede original outcomes. The other69
originals (59 stalled and10 signal-terminated) have no children in these two
follow-up packages. The audit records every gap's evidence, exit codes and
child identities and hashes all source reports. Completing the176-child
queue cannot by itself close the whole campaign's internal-trial coverage.
These are coverage gaps, not97 newly discovered RTL bugs; unsupported
misalignment and illegal-instruction exits retain their separate review.

`rvv_original_partition_gap_audit02/gaps.json` revalidates every source hash
from audit01 and adds the19 permutation parent mappings described below.
There are still97 original numerical gaps:47 now have operation-partition
follow-ups, while50 (40 stalled and10 signal-terminated) have none in these
three packages. Mapping a follow-up is not board execution or numerical
completion; no original result is superseded and the earlier audit is retained.

### FP-Move And Extension Partition Execution

`rvv_partition_inventory57/inventory.json` binds all176 child identities
to reference-validated releases and exact board report/run identities through
recovery146. All176 have now been attempted:72 passed,47 completed numerical
failures and57 confirmed stalls. Only119 have complete numerical results.
The120 FP-move children comprise44 passes,47 numerical failures and29 stalls;
the56 extension children comprise28 passes and28 stalls. No child is pending.
This closes the execution queue, not the stalled children's internal trials
or the original97 numerical gaps. Parent results remain unchanged; broader
ISA acceptance and whole-campaign coverage are not established by this count.

### Permutation Restart Operation Partitions

`rvv_permute_partitions01` selects the19 stalled original permutation-restart
parents from additions36. Its398 single-operation children retain the same
oracle, assembly operation IDs, three seeds, eight scalar boundaries, seven
VLs, four masks and four restart trials. The reserved e8/m8 gather-ei16
encoding remains excluded. Both VLEN512/1024 pass all398 exact ELFs and
1069824 configurations per VLEN. `parent_mapping.json` binds each original
name/hash to every legal operation and verifies equal configuration totals.
Recovery147 queues all398 exact children after the archived recovery146
stall, with no omissions or changes to case metadata. Transfer hashes and
batch-observer preflight pass before the hidden Windows task starts. The
release is reference-validated; board completion is still pending. Parent
stalls remain immutable and are not replaced by reference passes.
Only op0 children emit the28 drained first-gather boundary lines; the mapping
clarifies that the inherited manifest trace description does not apply to
other single-operation children. No trace changes were made to the frozen ELFs.

### Recovery14 Observation Continuity

Recovery14's report-replacement permission failure interrupted its host observer,
not the guest batch. A separate passive UART/two-snapshot capture confirms ongoing
retirement. A hidden gap-aware observer reconnects without a command or reset;
ordinary numerical failures still continue, and no-retirement diagnosis retains
the two-snapshot requirement. Original reports and raw UART remain immutable.

An exact-ELF partial audit verifies105 additions41 passes against the complete
VLEN1024 marker lines and both VLEN reference identities:417200 configurations.
`rvv_recovery14_release41_partial01` is explicitly not full release acceptance.
The frozen gap plan `rvv_recovery14_observation_gap_plan01` binds27 additions41
and20 additions37 ELFs to original release metadata/hashes. All47 are incomplete,
not passes, and require selective later retesting at a safe batch boundary.
No already accepted result is scheduled for repeat because of this interruption.

After reattachment, additions37's two remaining e64/m4,m8 cases pass with6912
configurations and exact reference markers (`rvv_recovery14_release37_partial01`).
Its other20 cases remain observation gaps. Additions38's14 released unit-stride
NF3..8 restart ELFs all pass137088 configurations with full VLEN1024 marker
equality and immutable two-VLEN reference/ELF identity checks
(`rvv_recovery14_release38_partial02`). Indexed segment restart continues;
this is not all31 additions38 cases, NF2 unit-stride coverage or arbitrary
fault/restart acceptance. No gap result is inferred from neighbouring passes.

Subsequently all31 additions38 ELFs complete and pass251328 configurations,
including17 EEW32 indexed NF2..8 restart cases. The full immutable verification
is `rvv_recovery14_release38_results01`; it binds every ELF hash, both reference
report identities and exact VLEN1024 marker equality. This supersedes the
partial31-case status above, not the separate fault-replay, alias or arbitrary
boundary gaps. Additions39's first5 independent-index-width restart ELFs also
pass31920 configurations with exact reference outputs
(`rvv_recovery14_release39_partial01`); its remaining17 are not yet accepted.

Additions39 later completes all22 released independent-index-width restart ELFs:
131040 configurations pass with exact VLEN1024 reference markers and both
reference identities, verified in `rvv_recovery14_release39_results01`.
This supersedes the partial5-case status above. It covers the resident-memory
restart scenarios in that release, not unordered page-fault replay, arbitrary
fault boundaries or source/destination aliases. Additions40 continues in the
same guest batch without restart or RTL changes.

An independent Fraction-based resident indexed segment domain audit verifies
additions38's17 EEW32 cases plus additions40's51 EEW8/16/64 cases against all
338 legal NF2..8/data-SEW/LMUL/index-EEW combinations at ELEN64. Counts are
18/18/17/15 ELFs for EEW8/16/32/64; field lists and physical register bounds
match independently derived legality. All68 immutable ELF disassemblies also
contain exactly the expected unordered/ordered load/store segment opcodes at
the declared index widths. Evidence is
`rvv_recovery14_index_domain38_40_audit01`. This validates the released shape
and encoding domain, not current board completion or arbitrary VL/restart
points; EEW8 retains its declared representable-capacity restriction.

Additions40's EEW8 source subgroup completes all18 released ELFs and passes
115584 configurations. `rvv_recovery14_release40_ei8_results01` explicitly
selects that source manifest, validates its membership in additions40 and
binds exact ELF/two-VLEN reference hashes plus full VLEN1024 marker equality.
This is subgroup acceptance, not all51 additions40 cases; EEW16/64 continue.

The EEW16 subgroup subsequently completes all18 ELFs and passes115584
configurations, audited in `rvv_recovery14_release40_ei16_results01` with the
same exact-ELF/two-VLEN identity and complete marker checks. Together EEW8/16
close36 of51 released board results; EEW64 remains in progress. This does not
remove their declared arbitrary-boundary, overlap or page-fault exclusions.

All51 additions40 cases subsequently complete and pass340032 configurations,
verified in `rvv_recovery14_release40_results01` with immutable ELF/reference
hashes and exact VLEN1024 numerical markers. This closes the released resident
indexed segment shape domain together with additions38's17 EEW32 cases:
68 ELFs,338 NF/SEW/LMUL/index-width shapes,454272 executed configurations.
It does not imply arbitrary fault boundaries, aliases, misalignment or all
possible data patterns. Integer multiply-add restart coverage continues in
the same batch;47 observation gaps remain unresolved and are not passes.

Recovery14 later stops on a confirmed masked `vmacc.vv` no-retirement boundary
in additions42 e8/m4, VL512/vstart256 (RVV-02 additional scenario). Five preceding
multiply-add restart ELFs pass112000 configurations; no full176-case release acceptance
is claimed. Complete UART/report/two-snapshot/ELF/disassembly evidence is in
`rvv_recovery08_14/terminal_scene`. After the observer/task stop, recovery15
prepares523 exact ELFs:476 never-attempted cases plus47 observation gaps,
explicitly recorded in `recovery.json`. It prioritizes the27 missing additions41
cases, retains the20 additions37 gaps and defers the masked accumulator restart
family. Prior216 passed results and all historical failures remain immutable.

Recovery41 subsequently completes48 more masked multiply-add restart ELFs:
12 each for disjoint, first-source alias, second-source alias and both-source
alias destinations. Each subgroup covers SEW16 mf4/mf2/m1/m2/m4,
SEW32 mf2/m1/m2/m4 and SEW64 m1/m2/m4. The strict frozen partial audit
`rvv_recovery41_release42_partial04` binds the exact ELF metadata, run
protocol, both VLEN references and numerical markers: all48 pass806400
configurations and56985600 oracle element comparisons. These element
comparisons are not executed vector-instruction counts. This adds measured
non-m8 coverage without accepting the stalled SEW8/m4 cases or any pending
m8 combination, and does not make the full176-case release accepted.

The same recovery41 batch completes12 SEW16/32/64 non-m8 packed mask
logic source-alias restart ELFs. The exact-ELF/two-reference partial audit
`rvv_recovery41_release36_mask_logic_partial01` verifies64512 passing
configurations with zero errors. This is the mask-logic source subset of
additions36, not its permutation subgroup or its still-pending m8 cases.
The earlier SEW8/m4 mask-logic completion stall remains a separate recorded
failure; no common internal cause or repair is inferred from these passes.

Recovery15 completes the27 missing additions41 ELFs with75600 passing
configurations. A disjoint cross-run audit joins them with recovery14's105
verified passes: all132 released multiply-add alias ELFs pass492800
configurations. `rvv_recovery14_15_release41_results02` binds both run IDs,
protocol hashes, frozen report/partial-audit hashes, exact ELF metadata and
actual VLEN1024 reference rows. Results remain distinct runs, not an invented
uninterrupted batch. The27 observation gaps are resolved by new measured
results; the20 additions37 gaps are still being retested, not inferred.

Recovery15 subsequently completes all20 missing additions37 ELFs and passes
80352 configurations. Joining them with recovery14's two verified results
closes all22 released resident-memory restart ELFs:87264 configurations pass
with exact reference markers. `rvv_recovery14_15_release37_results01` binds
each run's protocol, report and reference hashes, retaining separate histories.
Together with the additions41 audit, all47 observation gaps are now resolved
by measured new results. The original incomplete records remain immutable;
they are not retrospectively changed into passes. Other pending cases,
confirmed stalls and numerical failures still prevent overall acceptance.

Additions42's disjoint unmasked restart subgroup completes all22 ELFs and
passes492800 configurations (`rvv_recovery15_release42_disjoint_unmasked_results01`).
The masked disjoint e8/m4 stall and its five preceding passes remain separate.
The complete release contains176 ELFs, not only the44 disjoint masked/unmasked
cases; source-alias restart subgroups continue in the same batch. No result
here fixes or implies acceptance of the masked restart boundary.

Recovery15 ends after74 numerical passes on the masked first-source alias
e8/m4 VMACC/CSR boundary, again at VL512/vstart256 (RVV-02 additional scene).
All47 observation gaps are already retested; no incomplete gap remains in
this batch. Full scene/ELF/disassembly/snapshots are preserved before recovery16,
which retains448 never-attempted cases and defers the masked first-alias family.
The22-case unmasked disjoint acceptance remains separate from the two masked
stalls and the unfinished176-case release.

Recovery16 completes the first-source alias unmasked restart subgroup:
all22 exact ELFs pass492800 configurations. The frozen audit
`rvv_recovery16_release42_first_unmasked_results01` binds the run protocol,
ELF identities and VLEN1024 board markers to the accepted reference results.
This is subgroup acceptance only; the176-case release remains incomplete,
and masked alias restart stalls are not resolved by these passing results.

Recovery16 then confirms a masked second-source alias e8/m4 stall at
VL512/vstart256 (RVV-02 additional scene). Its27 completed ELFs pass548800
configurations in `rvv_recovery16_release42_partial01`; the stalled ELF
has no completed numerical result. The complete scene is preserved in
`rvv_recovery08_16/terminal_scene`. Recovery17 retains420 never-attempted
exact ELF identities and additionally defers the masked second-alias family,
without dropping it from the coverage inventory or changing the original image.

Recovery17 completes all22 second-source alias unmasked restart ELFs,
passing246400 configurations. The exact-ELF/reference-marker audit is
`rvv_recovery17_release42_second_unmasked_results01`. This does not accept
the masked second-source alias cases or the incomplete176-case release.

Recovery17 subsequently confirms the masked both-source alias e8/m4 stall
at VL512/vstart256 (RVV-02 additional scene). Its27 completed cases pass302400
configurations in `rvv_recovery17_release42_partial01`. Full stall evidence
is retained in `rvv_recovery08_17/terminal_scene`. Recovery18 continues all392
unattempted exact ELFs, with this masked family additionally deferred, not omitted.

Recovery18 completes all22 both-source alias unmasked restart ELFs,
passing246400 configurations in
`rvv_recovery18_release42_both_unmasked_results01`. Together with the
disjoint, first-source and second-source unmasked audits, all88 released
unmasked additions42 ELFs pass1478400 configurations across distinct runs.
The four masked subgroups remain incomplete; these passing results do not
repair or accept the observed masked restart stalls.

Recovery18 subsequently stalls on additions32's
`rvv_segment_alignment_e16_mf4`, with no completed numerical marker.
Both exact-ELF references pass432 configurations, but the board scene only
establishes no retirement at the phase1-store/segment-load boundary (RVV-18),
not the active offset/VL/mask or internal RTL cause. Full evidence is in
`rvv_recovery08_18/terminal_scene`. Recovery19 retains369 unattempted ELFs
and defers the segment-alignment family; these cases remain uncovered,
not silently removed or accepted based on reference results.

Recovery19 executes five additions33 vector fixed-point restart ELFs,
passing53760 configurations in `rvv_recovery19_release33_partial01`, then
stalls on e8/m4 at VL512/vstart256 during the VSMUL/CSR boundary (RVV-02
additional scene). Full evidence is preserved in
`rvv_recovery08_19/terminal_scene`. Recovery20 retains363 unattempted
ELFs and additionally defers vector fixed-point restart, without dropping
the separate scalar/immediate restart subgroup or changing the original image.

Recovery20 executes five additions33 scalar/immediate fixed-point restart
ELFs, passing201600 configurations in `rvv_recovery20_release33_partial01`,
then stalls on e8/m4 at the masked VSMUL.VX/CSR boundary, VL512/vstart256
(RVV-02 additional scene). Complete independent evidence is in
`rvv_recovery08_20/terminal_scene`. Recovery21 retains357 unattempted
exact ELFs and additionally defers this scalar restart family. The failure
at the first opcode does not provide coverage of later opcodes in that ELF.

Recovery21 passes additions08's `rvv_extension_e32_m2_vf4` (168 checked
configurations, `rvv_recovery21_release08_partial01`) and then confirms
the e32/m4/vf2 high-end overlap no-retirement scene (RVV-06), distinct
from nonzero-restart arithmetic. Full evidence is preserved in
`rvv_recovery08_21/terminal_scene`. Recovery22 retains355 unattempted
exact ELF identities and defers extension overlap cases; their internal
partial work is not counted as completed numerical coverage.

Historical recovery10 additions44 results are now independently audited:
all352 three-instruction multiply-add dependency-chain ELFs pass1478400
configurations with exact VLEN1024 reference-marker equality. Evidence is
`rvv_recovery10_release44_results01`. This older observer has no protocol
nonce; the audit explicitly binds its immutable report inputs to the
archived transfer manifest and verifies contiguous case identities, exact
ELF/archive/source hashes and both reference runs. It does not invent a
modern nonce or require repeating already measured board tests. This closes
the stale board-pending table entry, not the remaining restart/stall coverage.

Recovery22 completes two independent additions08 source subgroups:
all15 narrow low-end-overlap ELFs pass2520 configurations
(`rvv_recovery22_release08_narrow_alias_results01`), and all9 FP32/64
extra-arithmetic/conversion ELFs pass60480 configurations
(`rvv_recovery22_release08_fp_extra_results01`). Both audits bind exact
ELF identities, the active nonce protocol, source/archive hashes and both
reference runs with exact VLEN1024 marker equality. The floating-point
subgroup covers five rounding modes, sticky flags and nonfinite/subnormal
inputs at vstart0; it does not accept the separate FP restart failures.
Remaining extension/segment cases still prevent full additions08 acceptance.

Recovery22 subsequently completes all14 resident NF3..8 unit/positive/
negative-stride segment ELFs at vstart0, passing34272 configurations in
`rvv_recovery22_release08_segments_results01`. This closes the pending
segment source subgroup above; it does not accept separate target alignment,
page-fault replay or nonzero-restart scenarios. Together these three source
subgroups account for38 completed ELFs and97272 passing configurations.
The additions08 extension-overlap cases still prevent whole-release acceptance.

Recovery22 ends with38 complete numerical passes and one confirmed
e32/m4/vf4 extension-overlap stall (RVV-06 additional scene). Full evidence
is preserved in `rvv_recovery08_22/terminal_scene`. Recovery23 continues
all316 unattempted exact ELFs; no completed or stalled case is relabeled
pending, removed from the inventory or inferred passed.

Recovery23 confirms the e32/m8/vf2 legal-extension-overlap no-retirement
scene (RVV-06), preserved in `rvv_recovery08_23/terminal_scene`, leaving315
unattempted exact ELFs for recovery24. To remove manual gaps between risky
cases, the local `rvv_campaign_supervisor.py` starts at recovery23 using
the already verified observer identity. Its nine scheduling safety tests pass.
It validates nonce/input identities, contiguous results and two unhalted live
snapshots; only a stopped observer/task with a confirmed stall can call the
existing evidence-preserving original-image continuation launcher. Active
execution, timeout, incomplete observation or transport failures cannot
authorize a reboot. All pending ELF identities are retained across launches.
`rvv_auto_supervisor01` records decisions, terminal reports and launch logs;
execution exhaustion explicitly does not claim numerical/ISA acceptance.

The four completed additions42 unmasked subgroups now have a strict
disjoint cross-run join: `rvv_recovery15_18_release42_unmasked_results01`
binds all88 exact ELF identities and1478400 passing configurations to
the accepted source manifests, reference rows, frozen report hashes and
nonce protocols. `whole_release_selected` is false; all masked subgroups
remain outside this acceptance. No historical failure is overwritten.

Recovery24 confirms e32/m8/vf4 legal-extension-overlap no retirement,
preserved in `rvv_recovery08_24/terminal_scene` (RVV-06 additional scene).
The automatic supervisor verifies the stopped task, observer identity and
two live snapshots before invoking the existing continuation launcher.
Recovery25 retains all314 unattempted exact ELFs; no incomplete observation
or timeout is used as reboot authority.

Recovery25's first three SEW64/m1 extension ELFs (vf2/vf4/vf8) pass504
configurations with exact reference-marker equality in
`rvv_recovery25_release08_partial01`. Their source EMUL is fractional and
the generator does not enable high-end overlap for these shapes. These are
independent numerical passes, not acceptance of the stalled overlap shapes.

Recovery25 subsequently confirms the e64/m2/vf2 legal-overlap no-retirement
scene (RVV-06 additional scene), preserved in
`rvv_recovery08_25/terminal_scene`. The three completed numerical results
remain separate from the stalled ELF. The evidence-gated supervisor
continues310 unattempted exact ELFs in recovery26; the original bitstream
and kernel are unchanged, and no timeout is treated as confirmed failure.

### Board Milestone After Recovery11

All319 additions45..53 cases have executed:78 passed and241 failed.
The immutable milestone summary and metadata/numerical verification are in
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery11_additions45_53_results01`.
All78 ordered indexed fault-replay shapes pass with48 cases,36 signals and
zero errors per ELF. All22 unit-stride shapes report48 cases,48 signals and
32 errors; all86 unit-stride segment shapes report96 cases,96 signals and
64 errors. Reference expectations are36 and72 signals respectively, with
zero errors. All133 FP comparison cases fail. This separates measured
address-mode outcomes, not internal RTL causes or arbitrary fault boundaries.

Recovery11 subsequently preserved a masked fractional-LMUL slideup restart
stall (RVV-14). Recovery12 queues662 reference-validated additions54..57
first, then652 previously unattempted cases, with stall-prone restart
families last. All1314 remain individually hash-checked and numerically
classified by an opt-in guest batch runner. Historical paragraphs below
describe release-time staging; this milestone supersedes their pending
board status for additions45..53. A queued case is not a board pass.

Additions54's108 positive-strided shapes are now fully executed and failed.
Immutable exact-ELF/two-VLEN verification is in
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery12_release54_results01`.
All22 NF1 shapes report96 cases/96 signals/64 errors (reference72 signals);
85 segmented shapes report192 cases/192 signals/128 errors (reference144
signals). NF8/e32/mf2 instead reports169 errors and remains explicitly
separate. None of these aggregate counters establishes an internal cause.
The batch automatically proceeds into additions55 rather than stopping
after the failed release.

Additions55's108 negative-strided shapes also finish with numerical failures,
verified in `rvv_recovery12_release55_results01`. All22 NF1 shapes report
96 cases/96 signals/64 errors; all86 segmented shapes report
192 cases/192 signals/128 errors. Both immutable reference VLENs expect
72/144 signals respectively and zero errors. No169-error outlier appears
in this negative-stride run. Ordered indexed segment coverage continues
in the same live batch; partial passes are not a completed338-case release.

Additions56 subsequently completes all338 released shapes:337 pass and
the same-width NF7/e32/mf2 case fails with one aggregate check error
(RVV-15). The full release audit is `rvv_recovery12_release56_results01`,
binding exact ELF identities and both reference report hashes. Passing
cases cover32288 configurations and24200 repaired signals, with zero
errors. The failed case finishes96 configurations/72 signals and one
error, so complete execution is not whole-release acceptance. No other
indexed segment failure appears in this run. Zero-stride additions57
continues automatically in the same batch.

Additions57 does not complete in recovery12:13 zero-stride cases finish
with numerical failures, then `rvv_fault_replay_strided_zero_stride_e64_m2`
stalls at a kernel vector-state CSR PC boundary (RVV-16). The confirmed
no-retirement scene is preserved before authorized original-image recovery.
Recovery13 retains all746 unattempted names/hashes; the94 remaining
zero-stride shapes are deferred, not omitted. The stalled case is not a
completed test or a pass, and no full108-case zero-stride coverage claim
is supported yet.

Additions40 supplements NF2..8 indexed restart with index EEW8/16/64.
Legal EMUL/register constraints produce18,18,15 ELFs (51 total). Both
reference VLENs pass340032 configurations. EEW8 uses a representable
power-of-two domain so its index permutation remains unique; small VL
boundaries are clamped, not claimed as distinct exhaustive points. EEW16/64
keep full capacity. Hardware execution is queued after additions39.
Together with additions38's EEW32 this covers resident indexed segment
restart at all index widths, not page-fault replay, aliases or misalignment.

Additions39 supplements resident indexed restart across all legal independent
index EEW8/16/32/64 combinations (22 ELFs,131040 configurations per VLEN).
Four representable starts test ordered/unordered loads, unique-address
stores and ordered duplicates; skipped prefix stores must not determine
the final duplicate target. Whole4096-byte output checks include guards.
Both references pass; board execution is queued after additions38. Index
overlap, actual page-fault replay, misalignment and other segment index EEWs
remain separate gaps.

Additions38 supplements larger-field segment restart:14 unit/positive/
negative-stride NF3..8 ELFs and17 ordered/unordered EEW32 indexed NF2..8
ELFs. Four representable starts check every field and the full8192-byte
output buffer. Both reference VLENs pass251328 configurations; hardware is
queued after additions37. Legal register/index EMUL restrictions remain
explicit. Actual fault replay, other index EEWs, misalignment and aliases
are not covered by this resident-memory release.

Additions37 supplements resident aligned memory restart (22 ELFs). Unit,
positive/negative stride, zero-stride loads, same-EEW ordered/unordered
indices and legal NF2 segments use four representable starts, seven VLs,
four predicates and three seeds. Entire output buffers and second fields
are checked. Both references pass:89568 configurations at VLEN512 and
87264 at VLEN1024. Indexed VL limits, reserved m8/NF2 and zero-stride
duplicate stores are explicit exclusions. Hardware execution is queued
after additions36; actual fault replay, index overlap, independent index
EEWs, larger-NF restart and misalignment remain separate gaps.

Additions36 adds permutation restart and mask-logic source-alias restart
across all 22 legal integer shapes (44 ELFs, 1357440 configurations per
reference VLEN). Four representable starts check prestart/no-body preservation
and cleared vstart. Permutation covers full-XLEN offsets, ignored v0 in
unmasked moves and selector/predicate differences. Mask logic is unmasked
and writes either source; its packed-bit prefix remains unchanged.
Both references pass; hardware execution is queued after additions35.
Permutation aliases, physical fractional tails and arbitrary starts remain
gaps. RVV-08's measured failures remain open.

Additions35 supplements integer scalar/immediate comparison restart and
comparison destinations aliasing either vector source. Its 44 ELFs cover
all 22 legal shapes, four representable starts, seven VLs, four masks and
three seeds (177408 configurations per VLEN). Both references pass; board
execution is queued after additions34. TEST-06's overlap inactive-bit rule
is corrected for new ELFs; old evidence is unchanged. This is not coverage
of mask-logic, carry-result, vid or reserved restart behaviour in other
mask instructions.

Additions34 adds masked and unmasked FP comparison restart (30 ELFs,
2150400 configurations per reference VLEN). Packed prestart bits, start>=VL
no-op behaviour, sticky flags and suppression from skipped NaNs are checked
using the existing independent SoftFloat tables. Four start boundaries
and seven VLs cover all 15 legal FP shapes. Both references pass; hardware
execution is queued after recovery07. Source-alias restart, invalid scalar
boxing, arbitrary starts and exhaustive input combinations remain uncovered.

Additions33 adds fixed-point nonzero restart for all 22 legal integer
shapes in vector and scalar/immediate forms (44 ELFs, 1123584 configurations
per VLEN). Four representable start boundaries check result bits, prestart
and inactive preservation, all vxrm modes, sticky vxsat and cleared vstart.
Both VLEN512/1024 references pass; hardware execution is pending recovery07.
This supplements fixed-point restart coverage, not arbitrary vstart values
or the existing arithmetic/mask/memory restart failures.

| Priority | Gap | Discriminating Acceptance Evidence |
| --- | --- | --- |
| High | Broader arithmetic/mask/memory restart and hardware acceptance | Existing stalls remain open; additions33..37 supplement fixed point, comparisons, mask logic, permutation and resident memory, not arbitrary starts or all opcodes |
| High | Broader indexed/segmented fault replay | additions47..57 cover22 unit-stride,78 ordered indexed,86 unit-stride segment,216 positive/negative-strided,338 ordered indexed segment and108 zero-stride shapes; unordered faults, aliases, broader boundaries and hardware acceptance remain |
| High | Whole-register restart | Multiple EEWs and register counts, byte-offset checks; reference >EVL limitation remains explicit |
| High | Widen/narrow and clip aliases | Enumerated legal overlaps, rounding/saturation and masked-off flag suppression |
| Medium | Remaining operand variants | Integer multiply-add alias/restart and dependency-chain hardware acceptance, partial-group overlaps; floating slide1 aliases |
| Medium | Carry-chain and destination aliases | Multi-instruction propagation; legal v0 destination and source/destination overlap |
| Medium | Permutation aliases and restart hardware acceptance | Enumerated legal source/destination aliases and physical tails; additions36 restart references pass |
| Medium | Remaining FP moves/comparisons | Move aliases and comparison source-alias restart; additions45/46 supplement unmasked aliases and invalid boxing in references, with hardware acceptance and other malformed-box patterns pending |
| Medium | More FP conversions and widening reductions | Integer overflow, signed/unsigned widths, aliases, FP16 widening special values |
| Medium | Unordered inexact FP reduction | Legally permitted reduction-tree results, not a single scalar accumulation order |
| Medium | Segment index-width hardware acceptance and index misalignment | additions38/40 references supplement all index EEWs; actual indexed target misalignment and fault replay remain gaps |
| Medium | Destination v0 and physical tails | Legal source/mask aliases and fractional-group bits beyond logical VLMAX |
| Medium | Broader operating-system state preservation | Live-state fork, signals and preemption soak; single-core system cannot validate migration |

New families mostly use tu/mu. Earlier integer extensions include ta/ma,
but that does not prove every family or all four independent policy
combinations. Unmasked forms outside the supplemented integer families,
arbitrary register placements, all data
patterns and exhaustive VL/vstart values are not covered by this matrix.
Test setup stores and context-clobber instructions are not independent
numerical coverage for their opcodes.

The multiply-add alias supplement explicitly makes v24 both the old
destination and the first vector source, second vector source, or both
sources. The first-source variant includes vv/vx; the other two are vv-only.
Masked/unmasked executions and five initial-destination patterns cover
all22 legal integer shapes (132 ELFs,492800 configurations per VLEN).
The scalar oracle substitutes the old destination into the aliased input
before evaluating vmacc/vnmsac/vmadd/vnmsub modulo SEW. It checks the full
logical destination, including masked-off and tail elements. This is
vstart=0 and exact group overlap only, not dependency-chain or restart
coverage. Reference and hardware acceptance must be tracked separately.
Additions41 passes both VLEN512/1024 references and is queued after
additions40. No board acceptance is inferred from these reference passes.
Additions42 additionally builds176 multiply-add restart ELFs, including
disjoint groups and all three exact source-alias layouts. The independent
VLEN512/1024 reference job passed all176 ELFs and2956800 configurations
per VLEN. They are included in recovery08; hardware acceptance is pending.
This addresses representative restart boundaries, not arbitrary vstart,
partial-group overlap or dependency chains.
Additions44 additionally implements three-instruction homogeneous and
mixed multiply-add dependency chains, including exact source aliases.
All352 ELFs pass both independent VLEN512/1024 references, with1478400
configurations per VLEN. Report identities, numerical markers, exit codes
and immutable ELF hashes were verified. Board acceptance remains pending.
Intermediate results, changed masks and arbitrary opcode transitions
still require separate coverage rather than inference from final outputs.

Additions45 passes both reference VLENs for45 unmasked FP
comparison alias ELFs (v8/v16/v0 destinations, all15 legal FP shapes).
Four ignored v0 patterns, including all-off, distinguish unpredicated
execution from alias hazards; vv/vf result bits and sticky exception flags
use the unchanged pinned SoftFloat fixtures. Both report806400 configurations
per VLEN; identities, hashes, markers and zero exits were verified before
staging the package. Board acceptance is pending.
Additions46 passes both references for88 FP16/32 invalid scalar boxing ELFs across
disjoint and v8/v16/v0 destination aliases, masked and unmasked. Its
1576960 configurations per VLEN include946176 invalid-box scalar checks;
the remaining vector-vector checks retain original source inputs. This
reference identities, markers, zero exits and immutable ELF hashes were
verified. Board acceptance is pending. Other malformed-box
patterns and source-alias restart remain separate gaps.

Additions47 adds four actual unit-stride m1 page-fault replay ELFs. Both
reference VLENs pass192 cases with144 repaired SIGSEGVs. The signal frame
checks exact PC/address/code and vector state; prefix memory poisoning
distinguishes correct restart from reexecuting completed elements. Complete
page/output checks include inactive elements and guards. This supplements
protected and absent page replay, not indexed/segment replay, aliases,
arbitrary fault boundaries or other LMULs. Hardware acceptance is pending.
Additions48 supplements actual ordered indexed fault replay at the four
matching data/index EEWs, m1. Permuted indices distinguish exact physical
fault address from logical vstart. Both references pass192 configurations
and144 signals, while negative restart controls fail numerically as intended.
Unit-stride shared-code regressions also pass both VLENs. Independent index
EEWs, unordered/segment replay and register aliases remain uncovered.
Additions49 adds the12 unequal data/index EEW combinations at m1, completing
the16 legal width pairs together with additions48. Both reference VLENs pass
576 configurations with432 repaired signals. The same exact PC/address/vstart
and prefix-poison checks apply. Index EMUL ranges from1/8 to8, with aligned
v16 index groups disjoint from v24 data. This is reference coverage, not
hardware acceptance; unordered/segment replay and other LMULs remain gaps.
All12 independent-width negative controls also run at both reference VLENs.
Clearing saved vstart produces exit1 with56 numerical errors, while all48
scenarios and36 signals finish in each ELF. These24 results demonstrate
sensitivity to restarting the completed prefix; they are excluded from
coverage counts and board packages. Additions49 is staged on Windows with
matching manifest/archive SHA256, pending exclusive board execution.

Segment fault replay must follow the ISA's whole-segment vstart semantics.
Fields within a segment are unordered, and some fields of the faulting
segment may have completed at trap entry. A future oracle must check all
completed earlier segments, tolerate permitted partial fault-segment state,
and verify the complete replayed final result. Treating a partly modified
faulting segment as an error would falsely report legal hardware behaviour.
Additions50 adds36 ELFs for unit-stride and same-EEW ordered indexed replay
at all18 non-m1 legal integer shapes. Both reference VLENs pass1728 scenarios
with1296 repaired signals. Signal-frame checks derive vlenb from SEW/LMUL
and check the exact fractional/integer vtype encoding. Register groups are
aligned and disjoint; buffers cover the m8 capacity. Only the eight-element
faulting body is tested; full logical tails are checked, not physical tails
outside fractional VLMAX. Ten extreme-LMUL negative reference results
(mf8 unit and all four m8 indexed SEWs, at both VLENs) exit1 with56 errors
each as intended. They are not coverage ELFs. New default m1 ELFs are
byte-identical to the previously validated unit_regression03 and indexed01
ELFs; their prior reference reports remain immutable. Additions50 is staged
with matching Windows SHA256; board acceptance remains pending.
Additions51 adds44 ordered indexed unequal-width non-m1 ELFs, completing
all78 legal ordered indexed SEW/LMUL/index-EEW shapes together with the
prior releases. An independent rational EMUL audit compares the released
shape union with the legal1/8..8 domain; no missing, reserved or duplicated
shapes remain in that domain. Both reference VLENs pass2112 scenarios
with1584 repaired signals. All88 corresponding negative reference results
detect a cleared saved vstart with exit1 and56 numerical errors per ELF;
controls are excluded from coverage and board queues. Batching the44 ELFs
uses only one Linux boot per reference VLEN, retaining per-ELF hashes,
exit codes and numerical results. The package is staged on Windows with
matching manifest/archive hashes. This closes the width/LMUL reference
gap, not arbitrary boundaries, aliases, physical fractional tails,
unordered or segmented faults, or board acceptance.
Additions52 supplements actual unit-stride m1 segment replay for NF2..8
at all four data widths (28 ELFs). Both reference VLENs pass2688 scenarios
and2016 repaired signals. Page boundaries occur before a segment or after
half its fields. The handler validates whole-segment vstart, exact target PC,
si_code and a protected field address within the expected faulting segment;
field-access ordering inside that segment is not assumed. All fields of
completed earlier segments are checked and poisoned to distinguish an
incorrect restart from zero. Final checks cover every field, inactive/tail
elements and the whole8192-byte mapping. NF2/NF8 negative controls at both
VLENs produce exit1 with224/896 errors respectively, without unexpected
signal exits. All100 previously released non-segment shapes were rebuilt
and passed both references after the shared-oracle change; this regression
does not add100 new coverage ELFs or board queue entries. Additions52 is
staged on Windows with matching hashes. Indexed/strided segments, other
segment LMULs, aliases and arbitrary boundaries remain separate gaps.
Additions53 adds58 non-m1 unit-stride segment ELFs. Together with
additions52, the released shape union matches all86 legal NF2..8/SEW/LMUL
combinations under ELEN64 and NF*EMUL<=8, without reserved encodings or
register overflow. Field register stride is ceil(LMUL), including signal
frame lookup; fractional groups occupy separate physical registers.
Both reference VLENs pass5568 scenarios and4176 repaired signals.
NF8/mf8 and NF2/m4 negative controls produce896/224 numerical errors,
respectively, at both VLENs. All128 previously validated non-segment and
m1 segment ELFs were rebuilt and verified byte-identical to their prior
reference-validated binaries. This is an exact-ELF compatibility audit,
not128 new coverage ELFs or invented current reference reports. The
identity evidence binds immutable prior report hashes and each ELF hash.
Other address modes, aliases, arbitrary fault boundaries and physical
fractional tails remain gaps; hardware acceptance is pending.

## Findings To Retain

`ISSUES.md` records RVV-01 through RVV-17. They include indexed/fault
overlap, restart stalls, whole-register restart byte offsets, protected-page
mask/FOF failures, legal widening FP reduction rejection and legal high-end
extension overlap stalls, and missing invalid flags in sparse ordered
FP reduction, large-offset slideup last-element mask mismatches, and
excess NV flags from all-off FP comparisons, FP slide restart prestart
clobber/stalls, FP comparison restart mask-result errors/stalls and integer
scalar comparison restart errors/stalls, and vector comparison
source-alias restart errors/stalls.
Some have source-supported explanations; others
still require internal queue/cycle evidence. Do not merge them into one
assumed cause or claim all findings are equally proven RTL defects.

CAP-01 records nonaligned preparation loads raising SIGBUS before segment
testing. This is not presently a confirmed ISA violation. TEST findings
describe oracle/recovery tooling defects separately from hardware findings.
TEST-06 records the old integer comparison-alias oracle's potential rejection
of legal mask-agnostic inactive bits. Its old board tests passed; no captured
hardware failure is reclassified. New FP overlap oracles follow the rule.
The integer oracle is now corrected for newly generated tests, with
additions35 passing both reference VLENs; board acceptance is pending and
historical ELFs/results remain immutable.
Original failing reports remain untouched even when a future test improves
its instrumentation or capability classification.

## Scalar Fixed-Point Restart Execution

All22 released scalar fixed-point restart ELFs have now been attempted:
19 pass and3 stall (e8/m4, e8/m8, e16/m8). Recovery33's remaining
SEW32/64 nine ELFs pass362880 configurations, verified against exact
VLEN1024 markers and both reference identities in
`rvv_recovery33_release33_partial01`. Together with recovery20's five
and recovery32's five passes, the19 passing ELFs complete766080
configurations. The inventory is frozen in `rvv_inventory28`.
The three independent UART/ELF/two-snapshot scenes remain failures under
RVV-02; later operations blocked by those stalls are still uncovered.
Attempting all22 ELFs does not establish whole-family acceptance or fix RTL.

## Vector Fixed-Point Restart Execution

All22 released vector fixed-point restart ELFs have also been attempted:
19 pass and3 stall (e8/m4, e8/m8, e16/m8). Recovery35's nine SEW32/64
ELFs pass96768 configurations with exact-ELF/two-reference identity and
VLEN1024 marker verification in `rvv_recovery35_release33_partial01`.
Together with recovery19's five and recovery34's five passes, the19
passing vector ELFs complete204288 configurations. `rvv_inventory32`
retains all22 outcomes, separately from the scalar-form results.
The independent three stalled scenes remain under RVV-02; operations
after the stalled VSMUL boundary remain uncovered. This is execution
inventory, not whole-family numerical acceptance or a common-root proof.

## Completion Rules

Count a board pass only when its immutable ELF hash, unique numerical pass
marker and zero exit code agree. Report configuration counts separately
from ELF/process counts. Ordinary failures continue to the next case;
confirmed no-retirement stalls preserve two snapshots before authorized
original-image recovery. Pending cases, QEMU passes and capability skips
never count as board passes. No current result supports declaring complete
RVV coverage or full system acceptance.

Zero-stride fault replay passes both references in
`rvv_zero_stride_reference57` (108 legal NF1..8/SEW/LMUL shapes), with3104
configurations and2328 repaired signals per VLEN, released as additions57.
The nine representative NF1/m8, NF8/mf8 and NF8/m1 shapes pass both
VLEN512/1024 references. Nine skip-body negative controls fail numerically
at both VLENs as intended. The focused/negative diagnostics are not additional
coverage or board passes. Stores use one constant value per field across
elements, so unordered duplicate addresses do not require a particular
winning element. The stride comes from a non-x0 GPR containing zero.
Protected and absent pages, partial fault-segment field boundaries and
all-off masks are checked. No completed active prefix exists before the
first fault, so this does not claim sensitivity to restarting such a prefix
or observable device-memory access counts. The complete108-case report
identities, numerical markers/counts and ELF hashes were validated before
release; the currently running board batch is unchanged.

Additions56 independently covers all338 legal ordered indexed NF2..8
segment/data-SEW/LMUL/index-EEW shapes. Both references pass32384
configurations and24272 repaired signals per VLEN. Narrow EEW8 offsets
use reduced VL to avoid wrapping, with omitted boundaries declared.
The first protected segment is fixed to exercise partial field faults;
fields remain unordered even in ordered segment operations. Eleven
restart-from-zero controls fail numerically at both VLENs. Case identities,
hashes and the independent rational EMUL domain audit pass. This closes
the enumerated reference-shape gap, not unordered faults, aliases,
arbitrary fault boundaries or board acceptance.
