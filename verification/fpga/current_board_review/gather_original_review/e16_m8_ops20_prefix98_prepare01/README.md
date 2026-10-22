# Authentic e16/m8/ops20 Natural Prefix98

Host/Spike preparation only. No RTL image build, DUT launch, existing live-job
query, ZCC, or Verilator. New software ELFs and all generated evidence reside
only in this owned directory. Frozen e16ops1 references and shared helpers are
read-only baseline dependencies, not overwritten or regenerated.

## Authentic Source and Boundary

Selection follows `../NEXT_REMAINING_GATHER_SOURCE_PLAN01.md`.
Original child is `rvv_permute_restart_e16_m8_ops20`, from
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01`.
Recovery178 scene ELF and report are independently matched to the manifest
and triage; the historical `last_trial` remains null.

| Source | SHA256 |
| --- | --- |
| Original Linux ELF, both partition and scene copy | `21a28efe2ef7b79f9511c9b793bf0235bbc81944b27f1196179642f2a5a8c888` |
| Original shared C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Original e16m8 `operations.S` | `40bce22639d00865881e06337270ed76fd37e01c7891296471934accbf7afbcf` |
| Original `operations.h` | `886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4` |

The complete original C is copied without modification. The established
Linux startup/output/exit adapter is applied, followed only by a stop after
call98's full oracle and guard checks, with an exact PREFIX98 summary.
Both transformations are retained in `source_diffs/`. Build definitions are
SEW16, RESTART_PERMUTATIONS1, PERMUTE_OP_MASK1048576 (op20).

All97 predecessor calls, original seed0 xorshift13/7/17 input generation,
both index arrays, predicate and old output91 initialization remain. Disabled
ops0..19 are not replaced by synthetic warmup: their original loop filtering
remains in the C (17920 source-level empty iterations before selected op20).
No per-call RNG reset, hint, extra vector drain or reduced oracle is introduced.

Natural endpoint is tuple `[seed0,op20,scalar-slot0,length-index6,mask0,trial1]`:
cap512, VL512, vstart256, scalar0. Call66 is VL256/start128. The archived last
DETAIL at VL256/start128 is a post-return observation, not proof of the later
stopped tuple. This prefix is **not** exact historical-stall reproduction,
full2688-child acceptance, complete parent acceptance, or original Linux replay.

## Actual Assembly and ei16 Oracle

`source_elf_proof.json` binds disassembly of the actual original ELF and both
new software ELFs. All13 encodings match, including fullcap data/index/old-vd
loads, predicate load, requested VL, scalar move, vstart write, target,
returned-vstart read, fullcap restore/store and ret. The unused scalar move is
not removed. Original target PC is `0x10994`, SoC target `0x80000aac`, opcode
`38880c57`: `vrgatherei16.vv v24,v8,v16,v0.t`.

Actual call argument a1 must address `indices16`, not ordinary `indices`.
The independent model retains the original16-bit stream:
`0,1,511,512,513,RNG%544` selected by i%6. Active, selected output is
`input[indices16[i]]` when index<512, otherwise0. Source index is bounded by
capacity, **not VL**. Outside `[vstart,VL)` or under a false predicate, exact91
is required by the original tu/mu oracle; both guards remain91.

The natural stream includes both terminal-index forms: `indices16[255]=512`
(OOR at VL256) and `indices16[511]=1` (in-range at VL512). Endpoint98's active
half includes85 OOR indices. These are source/Spike facts, not measured DUT
FIFO/no-data-token behavior. No common RTL root cause is claimed.

## Host and Raw Reference

`host/host_gate.json` records one positive and seven negatives, all passing:
active, prestart, inactive, tail, guard0, guard1, returned-vstart. The actual
original C oracle is exercised against independently generated fixtures.
Prestart corruption is at VL2/start1/element0; tail corruption is at
VL1/start0/element1. They are distinct nonempty-body cases, not both VL0.
Host uses vector mocks only; Spike executes the actual original helper.

| Reference observation | Measured |
| --- | ---: |
| Calls / each of13 helper instructions | 98 / 98 |
| Full-capacity scalar results | 50176 |
| Guard checks | 196 |
| Unique scalar output/guard reads | 50372 |
| Returned-vstart zero | 98 |
| Actual vset results | 294 |
| Source/setup values per call | 2178 |
| Retired firmware through successful HTIF store | 2134409 |
| Spike elapsed / exit | 3.476708207s / 0 |
| Raw commit bytes | 137442674 |

Full raw `reference/commits.log` is retained, including vector values; no
filtering or representative-element reduction. `reference/reference.json`
records each call's actual arguments, target, returned CSR and reconstructed
console. `host_expected.json` retains full inputs, indices, masks and all
per-call expected values. Missing initialized bytes, missing scalar checks,
incorrect values/guards, helper drift, unexpected trap or nonzero exit reject.
Success requires PREFIX98 plus BOARD markers and no raw DETAIL/FAIL text.

Exactly one restart-gold Spike execution used the existing120s/5M-instruction/
768MiB-per-output-file ceilings. Actual raw trace is131.08MiB. No retry or
limit increase. `audit_reference.py` rechecks the same raw evidence offline
and exercises five corrupted traces; it does not launch Spike. Its inherited
EOF negative expects the known generic incomplete-execution diagnostic rather
than reproducing the earlier e16ops1 diagnostic-expectation bug. Any failure
would remain in its own directory and would not be overwritten.

| Prepared ELF | SHA256 |
| --- | --- |
| `soc01/gather_prefix_e16_m8_ops20.elf` | `c4d681ad58bf1e46e121ffc3c3652cabc1b2a62100fc3987012c502e53fc89fd` |
| `spike01/gather_prefix_e16_m8_ops20.elf` | `893422ed87ef3a2fcc91440ea9c9fd57b0f4284c794087d6884fcda6f2844181` |

Spike uses the reference runtime variant, not the SoC ELF. A byte-identical
rebuild of the entire original Linux ELF is not claimed. Both prepared helpers
are byte-equivalent to the selected original helper.

## Cost and Handoff

Measured reference cost2134409 retired implies3107..3125s at earlier accepted
M5 prefix rates687..683 retired/s, or7818.35s at conservative273/s. With20%
time margin the latter is9382.02s (2h36m22s): below3h, but above a9000s case
budget. These are estimates, not this case's measured VCS throughput or a
timeout/launch decision. No DUT runner or service is created here.

`READY.json` seals source proof, reference, Host/offline checks, executable
ELFs and evidence pins. Baseline pins include the frozen e16ops1 reference and
shared helpers. Independent Averroes review follows this producer preparation;
its acceptance, if issued, is separate from any later DUT admission.
