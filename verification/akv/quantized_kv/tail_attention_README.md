# RTL Attention Tail and Reused-Panel Checks

The main strided-cache inquiry measures the original 128-token workload.
This supplemental test is correctness-only: five visible tokens match the
first native model Decode step, while 33 tokens exercise one full panel and
its one-token tail at the same scratch address.

Each encoding uses the real captured two-head K/V bytes in token-major
storage. The tested group is KV head 0 and its six Query heads, D=128,
capacity 256. Only the F16 mask changes between zero-valued visible prefixes
5 and 33; masked rows are not selected or gathered.

## Independent References

`tail_native/prepare_tail_gold.py` links the exact archived host GGML
libraries that produced the original capture. It runs actual 12-Query-head,
two-KV-head Attention graphs for prefixes 128, 5 and 33 in both K formats.
The prefix128 results reproduce the original capture exactly. Each new
reference contains all 1536 F32 outputs; the RTL group checks its first 768.
The reference uses neither QBS arithmetic nor the candidate scheduling code.

`verification/out/akv-quantkv-tail-gold-20261024-01` contains the immutable
reference binary, raw log, loader/library identities, source manifest and
four tail output files. The export and its eight host tests passed. This is
reference preparation, not an RTL PASS.

## RTL Work and Probes

For each prefix, run ordinary RVV once, then native QBS/shared Attention twice.
Both schedules use the same RVV V decoder and production Query quantizer,
scale/mad primitives. Every trial checks all outputs, padding and outer guards;
native repeats must match bitwise and FCSR/VCSR must match the ordinary path.

| Visible Tokens | Ordinary Dots / V Decodes | Native QBS Commands | Native V Decodes | K Panels |
| --- | ---: | ---: | ---: | ---: |
| 5 | 30 / 30 | 2 | 5 | 1 |
| 33 | 198 / 198 | 4 | 33 | 2 |

Across both native repeats and prefixes, each format emits 12 actual QBS
records. Their N sequence is `5,5,5,5,32,32,1,1,32,32,1,1`, with M4/M2 pairs.
The checker verifies geometry, valid payload, read/commit work, no context
fill/reuse, and no commands attributed to the ordinary trials.

The executor wrapper exports the actual packed Query bytes and every QK
score after each command. The host independently replays 456 scores using
the previously accepted QBS arithmetic library and the original K rows.
This is bit-exact score checking, separate from the independent GGML final
output tolerance. It uses the actual exported Query bytes; it does not
independently reimplement or prove the Query quantizer. Query bytes must stay identical across tiles, repetitions
and prefixes. Command-level fflags are not exported independently; the check
is paired whole-trial FCSR, not a claim of separate per-command flag proof.

The probes print integer fields only and do not clear FCSR within execution.
They are intentionally outside any performance claim: this test records no
speedup. A legal vtype and a defined v8 precede each measurement-independent
drain, avoiding the previous uninitialized-register helper error.

## Acceptance

`build_tail_attention.py` creates an independent ELF from the accepted
strided inputs, includes both host golden arrays and rejects a target-linked
QBS reference or scalar V decoder. `run_tail_attention.py` requires the
accepted native model gate, then uses the same sealed VCS image and independent
vector/backend/AXI-write checks. All sources, references, checkers, image and
raw evidence are checked before and after execution.

Only terminal numerical, bit-exact QK, protocol and identity acceptance yields
PASS. Failures and bounded timeouts remain separate evidence; no automatic
repair, reference relaxation or simulator rerun is performed.
