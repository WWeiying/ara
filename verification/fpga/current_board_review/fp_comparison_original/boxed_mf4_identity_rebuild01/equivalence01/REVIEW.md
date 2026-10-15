# Whole-Program Mapping Feasibility

**UNKNOWN: no SEMANTICALLY_EQUIVALENT_RECONSTRUCTION claim.** The permitted
j-stutter/address-relocation rules do not yet yield a complete instruction
and edge relation. No semantic counterexample was established either.
Historical C remains NOT_RECOVERED; the earlier byte-identity failure stands.

## Sole Static Analysis

`ALGORITHM.md` records the rules before execution. One bounded invocation:
`timeout --signal=KILL 120s python3 -B .../equivalence01/analyze.py`.
The command tool returned actual exit 0 (chunk `2cf761`); analyzer elapsed
0.06759958388283849 seconds, tool wall time 0.522926797 seconds. Exit 0 means
the UNKNOWN report was successfully generated, not equivalence acceptance.
No additional objdump, compile, Host numerical run, reference, or DUT run.

Both text sections have contiguous complete byte-verified disassembly:
567 old instructions / 568 new. `full_cfg.json` records every instruction,
both conditional successors, direct calls and continuations. Indirect calls,
returns and ecalls are explicitly unresolved boundaries, NOT invented full
dynamic edges. This is a full static inventory, not a complete reachable-state
proof. Exactly 284 non-jump pairs passed local syntactic matching; 283 old /
284 new PCs lack a direct matched pair (these lists also include stutter PCs).
There are 16 reported frontier/boundary obligations. No coverage waiver.

## Exact Unresolved Points

- The reached ordinary-instruction frontier is old `0x104ae: 91098b13
  addi s6,s3,-1776` versus new `0x104b0: 91898b13 addi s6,s3,-1768`.
  The immediately preceding `lui s3,0x11` gives concrete addresses
  `0x10910` / `0x10918`, the same rodata offset 240; the following `+40`
  reaches the pointer table. This looks precisely relocatable, but the
  implemented conservative rule only accepts adjacent same-register lui/addi.
  It does not certify cross-register address provenance. This is a checker
  limitation, not evidence that these pointers are wrong. No rerun/expansion.
- Independently visible beyond that frontier: old `0x1045e: 9a62 add
  s4,s4,s8` versus new `0x1046e: 0a05 addi s4,s4,1`. These differ in opcode
  and register/immediate input, not merely PC or section address. A proof
  requires the incoming-state invariant `s8==1` on every edge; the local
  preceding assignments noted earlier are not a whole-program invariant
  certificate. The permitted syntactic rules cannot simply replace s8 by 1.
- Old `0x1045a` BNE versus new `0x1042c` BEQ needs predicate-complement plus
  successor-swap reasoning; old `0x10374` BNEZ versus new `0x10454` BEQZ
  likewise. These are not identical-opcode matches or j stutter. The earlier
  manual oracle analysis is supporting evidence, not a full edge certificate.
- Actual helper dispatch old `0x102f6: jalr t2`, new `0x102e2: jalr t2`
  needs a proven function-table load/index range relation through all loops.
  Seeding the ten checked helper pairs does not prove dispatch membership.
- Return opcodes match locally, but saved ra values, stack slots and mapped
  continuations need a relational call-stack proof. Ecalls need an explicit
  matched Linux syscall observation contract. The capacity-error self-loop
  at `0x101ce` is retained as a divergence obligation, not skipped forever.

## Data Coverage and Limits

All 12648 rodata bytes were checked, excluding only the exact ten 8-byte
pointer slots at offsets 280..352, which were individually decoded and
checked to point to corresponding helpers (+2). All other bytes, including
strings, input and expected tables, match exactly. BSS address/size/alignment/
type match. Capacity plus ten helpers remain identical 744 bytes. Input pins
match before/after. This does not replace a proof of every effective address
or memory access in the unmapped scalar code; no arbitrary address masking
was used to hide such a gap.

Conclusion: the evidence supports unchanged inspected oracle logic, but is
insufficient for the requested strict whole-program reconstruction label.
Do not infer an inverse historical C edit from these differences. Stop here;
exact C recovery still requires external source/history, while any broader
semantic proof would require separately authorized invariant/ABI reasoning.

## Artifact Hashes

- `analyze.py`: `2cda48347b758ade683c8b559cc2121224258d98e3b09241b51bd8f5d4430f73`
- `result.json`: `795984f4fc05bbb36827b9cd30576cfa711b05fa9a4dec1e6fcb8da5c3831004`
- `partial_mapping.json`: `839739b879e2ce7278092871bf3a9d215f2f18ec7aba1b914f6b419c0e248099`
- `full_cfg.json`: `4494e6c318bc0955f485c0003cd72fe17ece6797ed6b2794b01e311baeaf0442`
- `pins_pre.json`: `6486a05f4e1aff47192653515a62a4afea3f07b83473c1071e790b4df157a9ca`
