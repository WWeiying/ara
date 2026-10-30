# Real Prefill whole-call comparison preparation

The source is a genuine SmolLM2 M64 Prefill capture, D64,9 Query heads and3 KV
heads. The prepared case selects original Query positions32--35 and keeps all
heads, original K/V, original causal masks and the corresponding golden outputs.
This is a derived M4 slice with32 past tokens, not a new model capture, full M64
measurement or proof that GGML's M>=64 selector admitted M4.

`prefill_slice_data.py` checks original type/shape/byte strides, finite Q/K/V/
golden and original scale/tolerance. Each copied Query coordinate is checked.
Mask rows must have exact zero prefixes33,34,35,36 followed by negative
infinity. A synthetic coordinate ramp independently tests head/token/channel
ordering; a read-only genuine capture check also passes. No tensor is modified.

The new main calls actual `akv_attention_execute_v2_prefill_native` in
OFF/ON/ON/OFF order. Native validation, block preparation, QK, softmax, PV,
normalization, command lifecycle and drained output are inside timing. Poison,
workspace reset, golden/bit/flag comparisons and UART are outside. The candidate
only changes F32 PV dispatch; QK, masks, softmax and accumulation order remain
the original native implementation.

Each call compares all2304 finite outputs to unchanged original
`atol=.004 + rtol=.002*abs(golden)` and all9216 output bytes across modes. RNE,
VCSR5, exact FCSR and256 outer guard bytes are checked. No speedup is assumed.
This test does not provide unsupported-capability or multithread execution
evidence, and it does not claim runtime K/V immutability checking.

## Expected work from the actual schedule

One64-Query software block contains these4 Query positions. For each of3 KV
groups, FULL brings36 resident tokens, then the4 Query calculations have active
prefixes33--36. Generic QK uses3*64 columns per query, unchanged by PV pairing.
PV uses3 rows per active token OFF and2 rows ON (one pair plus odd tail).

| Per complete call | OFF | ON |
| --- | ---: | ---: |
| FULL / RELEASE | 3 / 3 | 3 / 3 |
| K column commands | 2304 | 2304 |
| V row commands | 1242 | 828 |
| All commands | 3552 | 3138 |
| Resident replay bytes | 324864 | 271872 |
| External payload bytes | 28992 | 28992 |
| Logical external ranges | 228 | 228 |

Four calls total13380 commands. These are static expected counts, not measured
hardware records. Column replay uses resident36 tokens, not a query's active
33--36 tokens; column bank groups are ceil(36/8)=5.

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads/f32_pv \
  -p test_prefill_slice_data.py -v
python3 -B verification/akv/paired_heads/f32_pv/build_prefill_slice.py \
  --output <FRESH_BUILD_DIRECTORY>
```

Actual prepared build:
`verification/out/akv-prefill-pv-slice-build-20261024-01`,
`BUILT_NOT_EXECUTED`. Fresh GNU objects, candidate scope, original feature/
Prefill validation code, libm, source/capture pins, real symbols and ELF bounds
are checked. The strict raw-record checker now passes synthetic count,
corruption, missing/extra-record and neutral/negative-performance tests. The
bounded worker independently rechecks the accepted F32 PV leaf result, its
original oracle log, typed build/image, UVM and all source/artifact hashes.

Actual preflight02 passed in
`verification/out/akv-prefill-pv-slice-preflight-20261024-02`. Preflight01
stopped before simulation because Python imported a parent-directory namesake
runner; explicit file-path loading and a module-identity test now guard this.
No old accepted checker or build was altered to make preflight pass.

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads/f32_pv \
  -p test_prefill_slice_check.py -v
python3 -B -m unittest discover -s verification/akv/paired_heads/f32_pv \
  -p test_run_prefill_slice.py -v
python3 -B verification/akv/paired_heads/f32_pv/run_prefill_slice.py \
  --build verification/out/akv-prefill-pv-slice-build-20261024-01 \
  --prerequisite verification/out/akv-paired-f32-pv-rtl-20261024-01 \
  --output <FRESH_RUN_DIRECTORY>
```

Use direct systemd ownership and a10800-second simulator bound. The worker
requires actual simulator exit0, original independent UVM/AXI checks and
pre/post inventory/hash identity after numerical/raw-work checks; it does not
accept partial logs or require positive speedup to label functionality PASS.
Freeze all pinned helpers while running. Existing leaf PASS does not substitute
for this complete-call gate. Full-M64 integration remains separate.
