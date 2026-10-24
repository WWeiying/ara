# Prefill F32 PV integration candidate

The leaf has actual RTL acceptance in
`verification/akv/results/paired-f32-pv-rtl-20261024.json`. This directory now
also supplies the admitted runtime implementation now included by canonical
`akv_v2_native_riscv.c`. `AKV_PREFILL_PAIR_PV=1` is still explicitly opt-in.

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
python3 -B verification/akv/paired_heads/build_live_ggml_runtime.py \
  --output <FRESH_BUILD_DIRECTORY> --jobs 8
```

Actual preparation:3072 host routing schedules PASS; mandatory/dimension
capability absence, bad VLEN and six-head preservation checked. Two source
scope/mutation guards PASS. Fresh GNU candidate compilation succeeded in
`verification/out/akv-prefill-pv-candidate-20261024-01`. Its three substitutions
are visible in `candidate.patch`; canonical Decode is unchanged except the
new private include, and original QK/softmax/mask/normalization code is retained.
That candidate-generation receipt is historical. Its source-scope tests now
use the exact pre-promotion Git fixture; the generator deliberately rejects
reapplying the transformation to current integrated source. Current canonical
source/object equivalence and actual combined QBS+AKV GGML compilation have
separate receipts. No new post-promotion native ELF or model run is claimed.

## Real-operator measurement

The genuine SmolLM2 M64/D64/GQA3 capture exists at
`/home/wangwy/llama/captures/smollm2-135m-q4_k_m-prefill-m64-20260901`.
Its metadata has9 Query heads,3 KV heads,64 Query tokens and256 physical KV
capacity. The causal visible prefix increases from1 to64. This exercises pair
plus odd-tail routing without replacing an already efficient six-head path.

The completed representative slice selects original Query positions32--35,
all9 Query heads and all3 KV groups, preserving original K/V, causal masks and
matching golden outputs. The whole native API ABBA sums are403898 generic and
380395 paired cycles, a5.819% reduction. Each call's2304 outputs meets original
tolerance and generic/paired bits/CSRs are exact. Original QK, softmax, PV and
output completion are timed, not only the PV leaf. Independent raw-log, work,
image/source pins and UVM rechecking passed. Receipt:
`verification/akv/results/paired-f32-pv-prefill-slice-20261024.json`.

This is a real Prefill slice, not full M64 or proof that GGML's M>=64 admission
selected a sliced M4 input. Resident-versus-active-token counters are checked
against each actual command rather than inferred from timing.

Full-M64 GGML admission/integration and performance remain separate work. Do
not extrapolate a slice's cycles into measured full-model latency or silently
replace original golden tolerances. Negative or neutral measured performance
must remain a valid functional result and prevent unjustified default enablement.
