# Reference-Only Prefix66 Ready

Status: **ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT**. No DUT/VCS/build-image/RTL
operation or existing artifact edit. Only this new preparation directory was
written. Main review/launch remains separate; original stopped tuple UNKNOWN.

## Review Entrances

- `READY.json`: SHA **f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649**.
  All61 ready artifact pins rechecked unchanged after preparation. This result
  note is newly added outside that already-produced readiness pin set.
- `scope.py` / `scope.json`: source_label `rvv_permute_restart_e8_m4_ops3`, actual
  runtime/program id `gather_prefix_e8_m4_ops3`, ordered66 tuples and exact counts.
- `source_diffs/adapter.diff`, `source_diffs/prefix.diff`: only existing Linux
  wrapper adaptation and original66-call final-statistics boundary insertion.
  All original enumeration loops remain, including unselected empty iterations.
- `pre_adapter_binary_proof.json` and `source_elf_proof.json`: original identity,
  unmodified-source rebuild comparison before adapter, and all13 original helper
  encodings matched in archive/SoC/Spike.
- `static_validation.json`, `host/host_gate.json`: nine static/model checks;
  one positive and seven expected-negative original-C host executions.
- `reference/reference.json`: strict single traversal of the one generated raw
  trace; SHA **2e48b4b2efd034cdc3876d2761dd7b9d6701879d1d89668824c101c81fd35dbc**.
  `reference/execution.json` preserves actual numeric rc0 before postchecking.

## Actual Scope and Reference Evidence

First66 natural child calls,65 predecessors, cap512/m4/e8/VI31. Endpoint
`[0,3,0,4,0,1]` is VL256/start128/mask all-on/scalar0, not a recovered stopped
invocation. This is additional scope absent from accepted83 and prior prefixes.

- Actual original capacity helper returned512 at `0x80000704`, raw line7274.
  Actual vlenb128 read twice: wrapper at `0x8000008a`/line6777 and original source
  at `0x80000354`/line7294. Vtype2/m4 and every target VL/start were verified.
- Full source xorshift input/ordinary indices/indices16, all128 physical
  predicate bytes (upper64 zero), all514 initialized output/guard bytes checked
  every call: **2178 values /2690 initialized bytes percall**. Original physical
  arrays remain1024/1026; unused array tails are not claimed audited.
- All13 helper encodings in order66 times: **858 helper retirements**,66 returned
  vstart0,66 full source-vector/result-vector/store checks. Mask logical extent64
  bytes is distinct from physical predicate storage128.
- **33792 complete byte results +132 guards =33924 unique scalar LBU oracle
  loads**. No active-only reduction. Original C statistics/error exit retained;
  reconstructed console has prefix PASS66/errors0, exact runtime CASE_PASS,
  REPLAY_PASS, no error/detail/trap markers; HTIF store1 means exit0.
- Last target `0x800007b8`/opcode308fbc57 at firmware retirement1344744,
  raw line1344749: actual source31=177, VL256/start128, a6/t3zero and ordinary
  indices pointer. Full endpoint is128 prestart91 +128 active177 +256 tail91,
  both guards91. VI31 source31 remains valid at earlier VL1.

Independent Python byte oracle and original-C host oracle agree on all33792
results. Host mutations active/prestart/inactive/tail/guard0/guard1/vstart each
produce actual exit1 while retaining66 calls; positive produces exit0. No Host
or Spike automatic retry occurred, and no additional reference probe was run.

## Actual Cost / Fixed Bounds

Exactly one Spike execution: **2.1738387988880277s**, numeric rc0;
**1353294 firmware retirements**, raw line1353299 at HTIF exit;
**85355107 raw bytes**. One strict raw audit took15.761526062618941s.
Fixed limits120s/3M instruction steps/768MiB perfile/2MiB simulated memory stayed
unchanged. They derive from existing cap51298-call references retiring2148472 /
2280966 within120s/5M/768MiB. Compiler commands are bounded30s each and host
executions15s each. This is measured reference cost, **not DUT cycles/walltime**.
No VCS runner/timeout change/launch is included in preparation.

## Binary Identity Boundary

Original Linux ELF SHA:
`a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
Unmodified-source pre-adapter rebuild SHA:
`1217bd89da691b7b9f0a9d838120ac3bc3b70db4116a0a47b1807ceefdf16143`.
They are **not byte identical**: archived comment Buildroot GCC14.3.0 versus
approved integration Xuantie14.1.1. No original entire-binary equivalence claim.
The narrower archive source/assembly identity and13 exact original helper
encodings are proven; runtime/ELF adapters remain explicitly disclosed.

SoC ELF SHA:
`4d2f9139a8edfe482d95386c8a50a5ba2bebde1c1b0ee50bd598a1f7572f0249`.
Spike ELF SHA:
`e224ecb81c8c5b376d1f71c313c7fda11eefbf8684f66a90d753b0dd417fd139`.

This reference does not accept any DUT image, original Linux schedule, original
ELF execution,2688-call child, full parent or historical11 stalls. A later worker
must use the exact runtime id and persist actual unvalidated numeric child result
before postcheck exceptions; it must not infer exit0 from service GC. All existing
sealed helpers/workers and prior acceptance records are untouched.
