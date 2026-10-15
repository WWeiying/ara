# Authentic e16/m8/ops3 Natural Prefix98

Host/Spike preparation only; no DUT, RTL image build, ZCC, live simulation
query, or changed frozen dependency. This is the original first98 calls
(including97 predecessors), not exact historical-stall, full2688-child,
full-parent, or Linux execution acceptance. Historical stopped tuple remains
unknown. Independent source/reference review and later DUT admission are separate.

## Source Identity

Selection: ../NEXT_REMAINING_GATHER_SOURCE_PLAN01.md.
Original child: rvv_permute_restart_e16_m8_ops3 in
/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01.

The matching archived scene is **rvv_recovery08_177**, not recovery175
(the latter is e16/m8/ops1). recovery168's e8/m4/ops3 multi-process history
does not apply; no warmup is inferred or inserted.

| Artifact | SHA256 |
| --- | --- |
| Original Linux ELF, partition and scene copies | 16a715c87479c206545de7e5e9173fcd5ac93a48fe71a6c9dcfd7466993bd853 |
| Scene report | 15a4bd6236a76e9ef8b3eec69fdf018ffb85ab3989114fad066851c0635f1bbf |
| Shared original C | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| Original operations.S | 40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf |
| Original operations.h | 886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4 |

The complete C and original Linux ELF are retained in prepared/. Source
adaptation is only the established Linux wrapper port and a stop after call98's
complete original oracle. Both diffs are preserved in source_diffs/.
SEW16 / RESTART_PERMUTATIONS1 / PERMUTE_OP_MASK8 select the authentic child.
The original seed0 xorshift13/7/17 input/index initialization, predicates,
old-output91, scalar-slot0, vstart, order and all97 predecessor calls remain.
Disabled ops0..2 retain their source-level filtering (2688 empty loop iterations);
these are not vector calls or fabricated history.

Endpoint tuple is [0,3,0,6,0,1]: cap512, VL512, vstart256, mask0, scalar0.
A bounded prefix reaching this tuple does not establish the unknown historical
stopped tuple.

## Assembly and Actual Source

source_elf_proof.json compares all13 actual instruction encodings from the
archived Linux ELF and both prepared ELFs. Target is 308fbc57:
vrgather.vi v24,v8,31,v0.t. Original PC0x1064a; SoC PC0x80000764;
Spike PC0x800007b0. No vx31 substitution. The unsigned immediate field is31;
a6 and the original unused mv t3,a6 remain0. The unused vle16 index load
is also preserved, with a1 pointing to ordinary indices, not indices16.

The new raw checker verifies actual v8..v15, v16..v23, old v24..v31,
predicate, VL/vtype/vstart before each target, complete target result/reset,
and all512 vector-store address/value pairs. Actual source[31] is **32689**
in every call; source[0] is61881, so scalar0 and immediate31 are discriminated.
Original expected() selects input[31] by capacity, not by current VL.
Prestart, inactive and tail elements remain91 under tu/mu.

## Reference Evidence

| Observation | Measured |
| --- | ---: |
| Calls / each of13 instructions | 98 / 98 |
| Full-capacity scalar checks / guards | 50176 / 196 |
| Unique scalar output/guard reads | 50372 |
| Returned-vstart zero / vset checks | 98 / 294 |
| Setup values per call | 2178 |
| Full vector input/result/store checks, each | 98 |
| Firmware retired through successful HTIF store | 1905086 |
| Spike wall time / rc | 3.125896011s / 0 |
| Raw commit bytes | 120211844 |

One Spike execution used the existing120s / 5M retired / 768MiB-per-file
ceilings; no retries or enlarged limits. Full commits.log, vector values,
reference.json per-call ledger and host_expected.json are retained.
Success requires all checks, exact PREFIX98/BOARD markers, zero HTIF exit
and no FAIL/TRAP/MISMATCH/DETAIL. Missing initialized bytes fail closed.

host/host_gate.json: one positive and seven detected negatives (active,
prestart, inactive, tail, guard0, guard1, returned-vstart). The actual original
C oracle runs against independent fixtures; prestart/tail injections use
distinct nonempty-body cases. Host mocks are not DUT evidence.
audit01/audit.json contains the separate offline replay and five corrupted
trace checks; it does not rerun Spike. READY.json records final audit status.

| Prepared ELF | SHA256 |
| --- | --- |
| soc01/gather_prefix_e16_m8_ops3.elf | c1064255efa0ff19d492d263723d1c7b88ad9521983ae07d12ecf8a753b5cf44 |
| spike01/gather_prefix_e16_m8_ops3.elf | e515e9b39af91af64f83d743a919fc6284512492a1a3f112b27646807cc70760 |

Spike uses its reference runtime ELF, not the SoC ELF. All13 helper bytes
match the archive; rebuilding the entire original Linux binary byte-for-byte
is not claimed.

## Cost and Seal

Reference cost1905086 retired estimates2773..2789s at earlier M5 prefix
rates687..683 retired/s; at conservative273/s it is6978.34s, or8374.00s with20%
margin. This is below3h, but not measured VCS throughput for this case and
not a runtime guarantee or launch authorization.

READY.json binds all owned artifacts. baseline_pins.json binds148 unchanged
source/tool/helper/reference dependencies, including frozen e16ops1 and
e16ops20 preparations. No existing reference or sealed checker is modified.
