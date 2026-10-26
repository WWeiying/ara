# Combined Zvfh Q8_K M4 Candidate

This is an **unapplied** two-guard dispatch candidate. The production runtime,
SDK, running grouped-PV model and VCS inputs remain unchanged. The existing
Q8_K M4 quantizer becomes eligible when QBS and Zvfh are both compiled in;
`GGML_RISCV_QBS_M4_PREPARE=1` remains required. Defaults, Q8_0's Zvfh path,
generic domain/rounding fallback and quantizer arithmetic are unchanged.

Run static admission with:

```sh
python3 -B -m unittest discover -s verification/qbs/combined_zvfh_m4 -v
```

These tests apply the patch only to a temporary copy and reject production
source drift. They do not establish compiler compatibility, numerical equality
or performance. The patch must not be applied to inputs of active workers.

## Isolated Full Translation-Unit Compile

`compile_candidate.py` consumes the actual combined build's compile database,
copies only `repack.cpp` into a fresh directory, applies the two-guard patch
there, and compiles with the original production flags and include paths.
Production sources and original object files are never overwritten. Headers,
source, patch and command identities are recorded and checked for changes.

```sh
python3 -B verification/qbs/combined_zvfh_m4/compile_candidate.py \
  --compile-commands verification/out/grouped-pv-model-build-20261026-01/compile_commands.json \
  --output verification/out/q8k-combined-zvfh-compile-NEW
```

The run `verification/out/q8k-combined-zvfh-compile-20261026-02` completed with
`COMPILE_ONLY_PASS`, effective `-march=rv64gcv_zfh_zvfh`, in 49.41 seconds.
Its object SHA256 is
`ea698aa0ea0706bd66ef14a0343a0a98d687f8b6f5dfa7d6d5715eac4be040af`.
The earlier `-01` attempt stopped before compilation: Git discovered the parent
repository and skipped the temporary-copy patch. The worker now constrains Git
discovery to the isolated output; exact candidate-text validation remains
mandatory. Neither attempt changed live sources. Numerical and performance
acceptance remain pending.

## Required Functional Gate

Rebuild the actual combined GGML translation unit with the effective production
`rv64gcv_zfh_zvfh` ISA and floating-point flags. The enable helper caches its
environment setting, so OFF and ON require separate processes, not alternating
`setenv` calls within a process. Preserve original generic preparation as the
oracle; a one-row quantizer is not the four-row byte-layout oracle.

| Test | Required evidence |
| --- | --- |
| Real captured M4/K1536 Q4_K projection | Complete packed bytes, scales, bsums, output and CSR comparison; actual OFF/ON trace |
| Other captured K-quant projection shapes | Same checks with K-block count and output width varied |
| M=1,2,3,4,5,7,8 | Full groups and remainder dispatch; no claim that M1 uses M4 optimization |
| Multiple workers | Per-worker work partition, output and canaries; do not treat caller-local FCSR as aggregate worker flags |
| Zero, signed maximum ties, tiny/large values, non-RNE | Existing numerical domain and fallback preserved, sticky flags checked |
| Q8_0 weights/activations | Original Zvfh implementation remains selected |

After functional acceptance, measure a same-ELF paired full projection call on
current RTL, including activation preparation, dispatch, commands and stores.
Keep context and wide-M policy equal. Historical 11.66% full-slice improvement
is motivation only, not current combined-runtime or whole-model performance.

See `hardware/docs/qbs_projection_preparation_audit_20261026.md` for the source
audit and historical evidence. Do not broaden this into cross-call activation
caching without explicit lifetime/invalidation contracts and measured benefit.
