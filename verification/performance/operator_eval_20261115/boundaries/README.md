# Group 6 QBS Boundaries

Only two ELFs, each with two calls. New sources/outputs only; every earlier
QBS/reuse/Attention file and build is read-only. `derivation.json` names copied
helpers and the archived SDK tests used to reconstruct the contract.

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/boundaries -p 'test_*.py' -v
python3 -B verification/performance/operator_eval_20261115/boundaries/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_boundaries_prepare_20261115_all_01
```

Preparation uses `git archive` SDK `dbe2b78817ef45b912444afcb85ad6e01a2be135`
and llama `a2b7f30da9aadf88b0a068c447383ed2e26ee867`. It reverse-checks the
already registered quantizer patch, uses no overlays or dirty AKV assembly,
and compiles host tests/firmware only. No VCS, Verilator, URG or production edit.

The parent runner consumes `manifest.json`. The checker command is
`python3 -B check.py --build BUILD_DIR --log {log} --output {result}`.
The outer pin map seals helpers, comparator/tests, archives, tools, data,
goldens, ELFs, build receipts and manifest. Do not edit pinned files after handoff.

## Genuine Input And Execution

Both workloads select the first 2/3 genuinely distinct Qwen3 attention-Q prefill
rows and first 35 weight channels from the reviewed eight-row capture. K=2048
is complete, not cropped, repeated or synthetically extended. M1 Decode, other
formats, full projection width and whole-model inference are not claimed.

M2/N35 uses ordinary global R4 and two native commands, N32+N3, each K-blocks8.
M3/N35 uses the SDK segment-major R4 storage and matching plan constructor,
three complete K segments 3+3+2 and six native commands. Device capabilities
are queried unchanged; no synthetic lower hardware K limit is advertised.
This proves the explicit software segmentation contract, not K larger than the
physical maximum of 256 blocks. The workspace has FP32 partials and gathered
row-major activations; its exact full post-execution bytes are independently
predicted and checked, including retained bytes outside the last active tail.

R4 is padded to 36 weight rows. Output stride is 38, while only columns0..34
are logical outputs. The expected output retains 0x5a bytes in every row-tail
hole. The target checks all 76/114 stored float elements, not merely 70/105
active outputs. All original input, padded weights, Q8, active activations,
workspace, command-activation snapshots and 12 raw guards are checked fully.
No numeric hash replaces comparison, and no tensor UART dump is required.

The independent host packer reconstructs segment-major bytes including padded
rows, checks them against the archived SDK packer, and checks every logical
output/K-block coordinate occurs exactly once. Each command is executed by
independent ordered `qbs_ref`; split-K results are combined in the exact FP32
RNE SDK order. Command flags plus FP32 addition exceptions form the golden flags.
No unsplit captured output is silently substituted for a split-K golden; no
tolerance is used or relaxed. A second host path executes the actual SDK with
the reference executor and checks every output and workspace byte against the
independently assembled golden.

## Reject And Fallback Contract

After first-call validation, real SDK checks must reject unsupported activation
context, short weight buffer, short workspace when applicable, K2047 and a
segment larger than the real capability maximum. A tripwire executor must see
zero calls. Outputs, row holes, workspace, Q8/input/weights/guards and seeded
fflags/VCSR/VSTART must remain unchanged. Only then is the second native call
issued through explicit caller `qbs_execute` DIRECT fallback.

This is not automatic RVV fallback and not retry after a native execution error.
M2 row-major context is unsupported even when its payload equals SRAM capacity;
M3 split-K/gather cannot use context. Rejections happen before native issue and
must not generate hardware exceptions. The parent retains independent protocol
checking and source/image identity gates.

## Timing And Flags

Two commit markers bracket each call; consecutive rdcycle stamps cover quant,
pack, plan, execute and final drain. The native callback records descriptors and
copies command activation bytes for later comparison; that bounded proof-tap
overhead stays charged to execute. This is a directed functional boundary probe,
not uninstrumented SDK performance. No overhead subtraction or cache claim.
Full comparisons and rejection checks are outside both timing ROIs.

Real llama quantization leaves VCSR2 (VXRM=1, VXSAT=0). Before/quant/pack/after
CSR snapshots are checked; VSTART remains0. Execution flags equal independent
gold with seeds0/8, so newly generated NX is not hidden by preseeded NX and sticky
DZ preservation is separately exercised. Command counters use actual N-tail
rows; M3's inactive fourth issue slot contributes capacity, not useful pairs.
Issue capacity is not physical lane utilization. Cooperative capability may be
on or off; neither M2 nor M3 is an M8 cooperation command.

## D256 Gap

The real Gemma capture and original model golden exist at the path recorded in
`cases.json`: D256, four query heads/one KV head, activeKV17, capacity256, captured
scale1, original atol0.004/rtol0.002. These tolerances are not changed.

The current `attention_real` registered reader accepts only D64/D128 and uses
128-dimensional padded strides/workspace. Its exact ordered tile64/expf/flag
oracle is not a validated adapter for the legacy segmented D256 online-FP16
schedule. The old D256 host diagnostic explicitly is not a replacement golden.
An isolated D256 layout/arithmetic/flags adapter and independent original-golden
comparison remain necessary. This delivery intentionally emits no D256 ELF and
counts no historical RTL PASS as current acceptance.
