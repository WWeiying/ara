# Missing59 History Edges: Prepared Reference

Status: HOST_SPIKE_ALL59_EDGES_118_CALLS_PASS_NOT_DUT.
Accepted output: `prepared02/`; initial stopped attempt: `prepared01/`.
No DUT launch, RTL/sealed-input change, or NF7/NF8 progress query occurred.

## Exact Selection

The source-proven original order is seed, op, mode, start. The original1134
executed calls have1133 adjacencies;20 operation partitions retain1074 and
introduce40 different adjacencies. This supplement contains exactly the59
missing edges:57 cross-operation transitions and2 cross-seed transitions.

Each of59 independent ELFs executes exactly its original predecessor and
successor,118 calls total, retaining117 intervening original exclusions.
`prepared02/edges.json` records every pair's two original executed-call IDs,
full tuples, candidate ordinals and individual skipped tuples. Cross-seed
pairs19 and39 are original executed IDs[377,378] and[755,756].

The two-line selection guard is the only change to sealed `case.c`:
`prepared02/selection.diff`. Original setup, skip predicate, input pattern,
whole-register assembly, status/vstart checks and1088-byte oracle remain
unchanged. No warmup/reset is inserted between a pair's calls. The surrounding
loop still traverses unselected candidates as scalar control flow; this adds
selection overhead and is not instruction-for-instruction timing equivalence.

## Verification

-59 positive host executions,413 rejected oracle corruptions and4 rejected
  coverage mutations. Every corrupted host execution reports exactly one
  original oracle error, without skipping either call.
-59 genuine Spike pair executions PASS, zero raw exit, exact markers and no
  trap.59 SoC ELFs compiled;59 corresponding Spike ELFs compiled and run.
-Commit evidence:118 exact target-PC/opcode retirements,236 whole preloads,
 118 output whole stores, complete1024-byte input initialization per call,
  full1088-byte old-destination initialization and128384 ordered output-byte
  oracle loads across118 calls. No tail/guard scan is replaced by a sample.
-The second call's entry vtype is verified before its original whole preloads:
 48 inherited VILL states `0x8000000000000000`,11 inherited e64/m1 states `0x18`.
 In particular, pairs15/35/55 retain op15 -> op16 with inherited VILL.
-All29 input pins,118 ELF hashes,59 trace hashes, pair/aggregate membership and
  ELF BSS bounds were independently rechecked after completion. No current
  production tree state is claimed validated by these software references.

## Instruction Counts

`COUNT_AUDIT.json` separates reference work from HTIF exit batching:

| Measurement | Sum over59 pairs | Per-pair range |
| --- | ---: | ---: |
| Retirements before raw replay_exit, matching minstret |4422790|71875..79947|
| Full commit logs including HTIF exit batching |4717790|76875..84947|

All59 traces contain exactly5000 additional retirements beginning at replay_exit
before Spike observes HTIF completion. These are not1088-byte oracle work and
must not be silently added to the useful-work estimate. Measured Spike process
time sums to67.909s; it is not a VCS performance measurement.

For feasibility only, the previous plan's assumed500 retirements/s gives about
2.46h serial for the raw-exit prefixes, or18.4min ideal aggregate work at8-way
parallelism, before packing/startup/checker/contention overhead. No DUT budget,
jobs reservation or launch is authorized by this estimate. Real partition
measurements and a separately reviewed bounded pilot are still needed.

## Identity and Limits

Original Linux ELF SHA256:
`f6ca381157fa767ab774017136af26d139e5c4776a1e7771f062251bbb7a2ecc`.
Original C SHA256:
`c7ab8b2293bf3583140cc8679126f0303a04e21e7c7d722833093da61da6a7ff`.
Unchanged original assembly SHA256:
`6d1278b29554907aff09d4a7730b1728cb8dc4c6b1fcf32e1bc57a20b7e8f218`.

Accepted complete.json SHA256:
`36d3e1b15f276e3b438edb6cbc8d64a888e1e56f39f66e6207cde81c5afde273`.
edges.json SHA256:
`0a7fe8eabc226663399e9435b0ef890b763a2dee0b44aebd860d90babbbf2de1`.
input_pins.json SHA256:
`b1a5e8d47283e8597291103af7af11fb47f9b534f5e2ed912f1257b2d181851a`.

Each pair begins from a fresh runtime. Its first call lacks the earlier
original history. Local predecessor effects, including observed inherited
vtype, are covered by these references; arbitrary deeper VRF/layout/queue
history is not reconstructed or proven equivalent. This is not full1134
continuous-history acceptance, original Linux/OS execution, or DUT PASS.

## Preserved Preparation Failure

`prepared01/failure.json` records a pre-Spike decoder refusal: GNU objdump uses
the valid `vl1r.v` alias for original `vl1re8.v`. The successor parser accepts
that alias and also checks the exact independently calculated target encoding.
Neither assembly nor setup/oracle was changed. `prepare_failed01.py` preserves
the original failed helper under that directory. No failed DUT was rerun.

The two pair00 Spike ELFs differ in12 bytes of non-allocated `.strtab`, caused
by assembler temporary-file symbol names. All executable/allocated bytes are
identical; do not claim whole-file ELF identity across the two compilations.
Only prepared02 ELF hashes are the accepted reference identities.
