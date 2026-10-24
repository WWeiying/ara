# Prefill F32 PV integration candidate

The leaf has actual RTL acceptance in
`verification/akv/results/paired-f32-pv-rtl-20261024.json`. This directory now
also prepares a full-runtime candidate, still not canonical deployment.

`runtime.h` supplies stateless admission and pair/odd-head routing. F32 output
row stride is4*D, score stride256B and scale stride4B. Admission requires actual
VLEN1024, F16 cached payload, row/tail/D capabilities and enough heads/context,
but intentionally does NOT require QK PANEL4. PV only uses existing V-row
delivery. Preserve D128/GQA6's already shared six-head PV. Unsupported shapes,
missing capabilities, absent getenv or requests other than exact
`AKV_PREFILL_PAIR_PV=1` retain generic execution.

The candidate reads the environment and determines a call-local decision after
original Prefill validation and before the first FULL. It uses the existing
device capabilities supplied by the caller. It does not add a context, global
selection state, second cache, instruction or arithmetic unit. The original
whole-context ownership rule still applies. Pairing heads does not pair Query
positions or alter any token's softmax recurrence.

```sh
gcc -std=c11 -Wall -Wextra -Werror -O2 -I. -Isoftware/akv/include \
  verification/akv/paired_heads/f32_pv/test_runtime.c -o /tmp/akv-f32-runtime
/tmp/akv-f32-runtime
python3 -B -m unittest discover -s verification/akv/paired_heads/f32_pv \
  -p test_prefill_candidate.py -v
python3 -B verification/akv/paired_heads/f32_pv/prepare_prefill_candidate.py \
  --output <FRESH_CANDIDATE_DIRECTORY>
```

Actual preparation:3072 host routing schedules PASS; mandatory/dimension
capability absence, bad VLEN and six-head preservation checked. Two source
scope/mutation guards PASS. Fresh GNU candidate compilation succeeded in
`verification/out/akv-prefill-pv-candidate-20261024-01`. Its three substitutions
are visible in `candidate.patch`; canonical Decode is unchanged except the
new private include, and original QK/softmax/mask/normalization code is retained.
This is `PREFILL_CANDIDATE_COMPILED_NOT_EXECUTED`, not whole-operator acceptance.

## Next real-operator measurement

The genuine SmolLM2 M64/D64/GQA3 capture exists at
`/home/wangwy/llama/captures/smollm2-135m-q4_k_m-prefill-m64-20260901`.
Its metadata has9 Query heads,3 KV heads,64 Query tokens and256 physical KV
capacity. The causal visible prefix increases from1 to64. This exercises pair
plus odd-tail routing without replacing an already efficient six-head path.

A bounded representative tile can select original Query positions32--35 and
one actual KV group, preserving their original K/V and causal mask columns and
matching golden outputs. It must be labelled a real Prefill slice, not a full
M64 run or proof that GGML's M>=64 dispatch selected a sliced M4 input. Include
packing/selection, original QK, softmax, PV and output in OFF/ON timing. Each
output's token order and F32 scale/FMA semantics must stay unchanged. Use
actual counter semantics for resident versus active tokens.

Full-M64 GGML admission/integration and performance remain separate work. Do
not extrapolate a slice's cycles into measured full-model latency or silently
replace original golden tolerances. Negative or neutral measured performance
must remain a valid functional result and prevent unjustified default enablement.
