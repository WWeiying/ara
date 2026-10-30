# Ordinary RVV Resource Regression

Preparation only until explicitly authorized. No new kernel, ELF, input crop,
canonical change, baseline rerun, model-performance claim, or PPA measurement.

## Immutable Workload

Reuse `akv-paired-heads-threeway-build-20261023-01/akv_paired_heads_threeway.elf`,
SHA256 `1be2be23ec376dc119c317687fb4dc4614acc11ee14d3303ec647882fd9beddd`.
The baseline is `akv-paired-heads-threeway-20261024-01`. The candidate image is
`shared-storage-integration-soc-build-20261025-01`, unified Q2/KV32 snapshot03.
Paths above are under `verification/out/`; defaults are explicit in contract.py.

The frozen `threeway_main.c` includes the actual application. Its ordinary path
calls `run_attention_rvv`, NOT tiled RVV. The native paths are the original
experimental generic/paired wrappers, not a new production implementation.
Qwen2.5 KV128 captured Q heads0,1,6,7 and corresponding golden are cropped offline;
K/V/mask are unchanged. Four Q heads, two KV heads, D128, 128 visible/capacity256,
512 F32 outputs: a derived subset, not a new model capture or full model.

Order remains RVV/generic/paired/paired/generic/RVV. Native query conversion,
plan construction, capability admission, execution and final vector-store drain
are inside each complete-call cycle window. Both RVV calls use the original
application path. FCSR=0/VCSR=5 reset before each call; CSR snapshot precedes
checks. Poisoning, guard checks and UART printing remain outside timing. All512
finite and original tolerance `0.004 + 0.002*abs(golden)` checks are unchanged.
Repeat outputs/FCSR are exact within variant; generic/paired exact; RVV/native
need not match bits or flags. Cross-image comparison checks each corresponding
checksum/FCSR/VCSR, not different variants. The ELF checks complete arrays on
chip but exports only FNV64: do not claim independent full cross-image byte dumps.

All3864 command records, every field and raw summary, must match the original.
RVV commands=0; generic=1542/call; paired=390/call. Each of the six complete-call
cycle counts must be no larger than its corresponding historical count. A single
regression fails the resource gate even if aggregate improves; measurements and
functional PASS are retained separately. No minimum speedup is required.

## Validation And Ownership

`contract.py` reuses frozen typed build/crop checks, accepted old image and run
validators, then requires all consumed log/vector/commit/UVM/source evidence pins.
`run.py` only runs the unified image, validates snapshot storage typing, pins
both image/build closures, capture, inherited tools and new helper files, performs
pre/post source-manifest and image-inventory checks and the original image contract.
The unchanged independent UVM checker requires events/backend/AXI reads/writes;
actual process exit must be zero. The inherited direct Execution owner records
child PID and cleans subprocess groups on exception, signal or timeout. A fresh
output is mandatory. `contract.py --candidate ... --output ...` independently
replays terminal raw/result/protocol/pin associations without simulation.

Two historical ELF source paths have legitimately changed since the baseline:
`software/akv/src/akv_v2_attention_rvv.S` and `akv_v2_native_riscv.c`. They are NOT
silently accepted at current bytes. `historical_sources.py` recovers them from
commit `585866f9661b0dc7adf9b9853746a983e884d0de` into the new output's
`historical-source/`, requiring exactly the two original SHA256 values recorded
in its fixed allowlist. Private copies of frozen validator functions substitute
only pin verification with this explicit historical mapping; their code and
input receipts remain unchanged. Every other original pin is verified normally.
New source-pins.json records actual archive paths plus bindings.json; old receipts
are separately hashed and retain their original source paths. The terminal audit
checks archived bytes/bindings without requiring git or claiming current software
is the source of this already compiled ELF. Neither old source nor receipt is edited.

Host tests (no simulator):

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads/ordinary_resource -p 'test_*.py' -v
```

Proposed command, NOT executed by this preparation (from signoff root):

```sh
systemd-run --user --unit=ordinary-rvv-unified-20261025-01 \
  --property=Type=exec --property=KillMode=control-group \
  --property=RuntimeMaxSec=10800 --property=TimeoutStopSec=30 \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B verification/akv/paired_heads/ordinary_resource/run.py \
  --timeout 9000 --output verification/out/ordinary-rvv-unified-20261025-01
```

Defaults select exactly the baseline/build/snapshot above. Direct worker is the
service main process. Stdout/stderr are retained by systemd; command/console logs
are also recorded under the fresh output. No queue polling or automatic retry.
`--preflight-only` is available with a separate fresh output; it cannot yield PASS.
After terminal PASS, an additional offline receipt can be written with:

```sh
python3 -B verification/akv/paired_heads/ordinary_resource/contract.py \
  --candidate verification/out/ordinary-rvv-unified-20261025-01 \
  --output verification/out/ordinary-rvv-unified-audit-20261025-01
```

## Runtime Basis

Completed baseline console starts Oct23 19:54 and ends20:39:59 (minute-resolution
start), approximately45-46 wall minutes; VCS CPU2673.490s (44.56 minutes), simulated
time1575879500000fs (1.5758795ms). Baseline complete-call cycles are
245497/81047/58341/58310/80523/245088. This is a compact-summary workload, not the
quantized H/S/B gate with full hex printing. Comparable machine load suggests
roughly45-60 minutes plus evidence checks; changed image and host contention may
increase it. No guaranteed upper performance prediction: simulator bound9000s,
service wall bound10800s, with cleanup grace30s. On timeout retain failure; do not
truncate stimulus or loosen checks. No simulator was launched to prepare this gate.
