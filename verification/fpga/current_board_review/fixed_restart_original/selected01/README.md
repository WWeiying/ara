# Source-Selected Boundary Discriminators

**Host/Spike preparation PASS only. No DUT execution or authorization.**
The existing `../prepared01/`777-call prefix and all its input pins remain
unchanged. Neither selection is full-prefix or original-Linux acceptance.

## Exact Calls

Both cases derive from the already byte-equivalent original C configuration
and unchanged archived S/header. Original ELF SHA256 remains
`ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.

| Selection | Original index | VL | Predicate | vstart | vxrm | Initial vxsat |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| single776 |776 |512 |mode0/all enabled |256 |0 |0 |
| pair775-776 first |775 |512 |mode0/all enabled |1 |3 |1 |
| pair775-776 second |776 |512 |mode0/all enabled |256 |0 |0 |

All are seed0/op0,e8/m4 `vsmul.vv v24,v8,v16,v0.t`. Actual host call rows
match the corresponding lines of the sealed777 trace byte-for-byte:

```text
CALL 775 0 512 1 7 a01acacf8faeb073
CALL 776 0 512 256 0 a01acacf8faeb073
```

The hash covers complete a/b arrays,128-byte predicate storage and the
initialized destination including both guards. VL/start/control are checked
separately in each exact row. Control7 means vxrm3 plus initial sticky1.

## Preserved and Skipped

The original source executes RNG/source initialization and original loop
enumeration/mask generation. After the original start/control tuple is
computed, a source-index filter admits only the requested call(s). Each
admitted call runs its original destination initialization, unmodified
assembly and complete original scalar oracle. Stop is after the final
selected call's oracle, not before checking it. Source diffs are retained
under each case's `prepared/selection.diff`.

Skipped vector calls, their destination initialization and their oracle
are not executed. There is no invented warmup. Thus these programs preserve
the selected calls' generated inputs/control but intentionally do **not**
preserve the full architectural history of calls0..774/775. Pair preserves
the genuine775-to776 adjacency only. A PASS cannot close a longer-history
stall; a FAIL would be a smaller authentic boundary counterexample.

New `FIXED_ORIGINAL_TRIAL index=` markers name original indices. The
original `RVV_TRIAL completed=` counts only actually completed selected
calls here (0 for single's boundary,1 for pair's boundary), not skipped
calls. Original summary `seeds=3` remains a source constant; only seed0
executes in these selections.

## Verification and Cost

Both positive host checks and both Spike full-oracle runs PASS. Thirteen
applicable oracle mutations are rejected: active/prestart/guards/vstart/
spurious-vxsat in both, plus lost-sticky-vxsat in the pair. Masked-off/tail
mutations are inapplicable because both selected tuples use full VL and
all-enabled masks; single has no initial sticky1 call. These limitations
are recorded rather than reported as passing mutations. The unchanged
777 preparation separately retains its broader oracle-negative coverage.

All24 op0 instruction bytes match the corresponding original/prefix helper
in both SoC and Spike ELFs, including loads and CSR setup/read/restore.
All185 input/generated-artifact pins reverified unchanged.

| Program | Vector calls | Spike retired to exit | Spike host wall time |
| --- | ---: | ---: | ---: |
| single776 |1 |477331 |0.135s |
| pair775-776 |2 |371229 |0.129s |
| preserved prefix0..776 |777 |16249331 |2.575s |

These independently measured instruction totals include scalar selection,
initialization and the full oracle, not just vector work. Do not infer
linear cost from call count or equate Spike host wall time with DUT cost.
Raw references and comparison: [costs.json](costs.json).

## Reviewable Inputs

[soc/programs.json](soc/programs.json) contains both exact SoC ELF paths,
hashes, target counts and strict original-oracle completion markers.

- single target PC `0x800008dc`, opcode `9c880c57`, expected target count1;
  ELF SHA `a2c977c473ad2c5ec482988ede51764f14b792de9d2a1e82d1f6807d45d7dcb1`.
- pair target PC `0x8000091c`, same opcode, expected target count2;
  ELF SHA `5fde53195658852cfd74602ebe1f6777916aaf8f5e4a7de7b39440ab66b64d9d`.
- Pin-ledger SHA:
  `0847eb8c5268802a2fb8d7d8297e9bc3cfcdb87d1a7d209b453d5282e49ace88`.

Recommended next review scope is these two discriminators, not a blind
777-prefix launch. No image, timeout or DUT launch has been selected here;
parent review and separate measured-run authorization remain necessary.
