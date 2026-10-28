# Ordinary RVV stride repair acceptance

Authoritative strict result:
`verification/out/m4-stride-rvv-repair-20261027-04/result.json`: PASS.
The original normal-library failure remains at
`m4-stride-rvv-fallback-20261027-01`: 96/128 mismatches.

| K | N | M | Element stride | Row padding (floats) | Compared outputs | Mismatches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 32 | 4 | 4 bytes | 16 | 128 | 0 |
| 512 | 32 | 7 | 4 bytes | 16 | 224 | 0 |
| 512 | 32 | 4 | 8 bytes | 3 | 128 | 0 |
| 512 | 32 | 7 | 8 bytes | 3 | 224 | 0 |

All 704 outputs are finite and bit-exact against dense controls. Input values,
backing storage, weights, scheduler ownership and actual strides are checked.
QBS is disabled in software and in the QEMU CPU; ordinary Q4_K 32x1 RVV
repack ownership is verified. No native QBS calls occur.

The repair extends blockwise collection to the shared INTER_SIZE=1 Q8_K/Q8_0
preparation path. Arithmetic, output layout, dense preparation, other interleave
sizes and MUL_MAT_ID are not changed. Actual execution here qualifies Q4_K
with Q8_K activations; it does not establish all-format fallback coverage.

## Preserved intermediate evidence

- `-01`: Python preflight incompatibility; no simulation.
- `-02`: object and ELF built, but the provider checker expected an incorrect
  template symbol spelling. No simulation.
- `-03`: original unchanged driver ran all four cases and all outputs matched.
  Strict trace acceptance failed because tensor-decision diagnostics deduplicate
  by an unlogged tensor pointer. A separate audit correctly remained incomplete;
  data/extra pointers were not substituted for missing tensor identity.
- `-04`: reused the same repaired object and libraries. Only the driver's main
  loop isolates each original case in a child process so each case has an empty
  diagnostic dedup table. The calculation and comparison function is unchanged.
  The strict checker now passes, including all per-case dispatch evidence.

The successor numerical checker differs from the original only in the expected
producer-call accounting: two dense K512 preparations and two gathered K256
blocks replace three K512 preparations. It retains bitwise checks and does not
change tolerances. Three checker tests pass, including corrupt-evidence tests.

Raw strict log SHA-256:
`0edfb38200d686bfe05d5fd37cc802d89f3378ce85c23709ad233b62b08a13d3`.
The QEMU run took 10.593 host seconds, a workflow measurement, not hardware
performance. The original same-process numerical evidence remains available.

This closes the bounded private functional reproduction. Normal-library
installation, combination with the packed producer, adjacent QBS regression
and model execution remain separate integration gates. RTL is unchanged.
