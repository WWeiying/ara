# Stage5 Unified Delivery DRAFT

Status: DRAFT / NOT COMPLETE. S3 aggregate instruction/graph acceptance and S4
real-model regression remain pending; S5 cannot close without their reviewed
evidence and final version/tag audit. RESULTS.md remains the parent's ledger.
Contract: `hardware/docs/INFERENCE_STAGE5_RUNTIME_DELIVERY_20261110.md`.
No model speedup, new RTL acceptance or board eligibility is claimed.

## Mechanism And Pins

- Runtime baseline: llama.cpp `da56aa750559c180d631b466de983ff2bb5d54d9`.
  `runtime/overlays/prepare.py` uses `git archive`, verifies baseline hashes,
  applies reviewed `auto_pair.patch` (adaptation of `06d046324`), then installs
  the resident entry/CMake overlay and sealed platform files. Do not archive
  dirty llama HEAD or copy the uncommitted AKV assembly.
- SDK archive: Ara `f50092f2d22238c6be4b6c159a1ad71a4ea68678`, paths
  `software/akv` and `software/qbs`. Resident architectural/model contract:
  `c49289ff8f433b8780954e207d6b0149f7bc2c32`. The library recipe checks their
  scoped consistency; these are distinct pins, not interchangeable repo HEADs.
- CMake `GGML_RISCV_AKV_RESIDENT=OFF` by default. ON plus runtime request
  `GGML_RISCV_AKV_RESIDENT=1` still requires an explicitly trusted provider.
  Weak/default NULL provider denies before INFO/custom opcodes. Capability
  index4 stays zero; a test deployment does not grant board NORMAL_MEMORY.
- Single-worker plain Decode, F32 Q/F16 K,V, D64/96/128 only, with shape/type,
  layout, RNE/VLEN/state and exclusive whole-call memory/ownership admission.
  Unsupported/provider-denied calls retain ordinary GGML RVV fallback.
  Nonzero VSTART is terminal; after route fixation SDK failure is terminal,
  never fallback/retry. Legacy native/Prefill/quantized-KV have separate grants.
- QEMU source is variant04 used by BUILD07, with preserved QBS and SoftFloat
  AKV/resident model. `delivery/qemu_source.py` is the standalone reconstruction
  entry; no historical recipe imports or OUT artifacts are required to rebuild
  its source tree. See `delivery/BUNDLE_AUDIT_20261110.md` for exact identities.

## Command Entrypoints

From repository root, set a fresh output name; commands below are reproduction
instructions, not commands executed during this packaging task.

```sh
S=verification/performance/next_mechanism/stage5
OUT=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
python3.11 -B "$S/runtime/overlays/prepare.py" \
  --output "$OUT/stage5_ggml_overlay_delivery_FRESH"
git archive f50092f2d22238c6be4b6c159a1ad71a4ea68678 \
  software/akv software/qbs | tar -x -C "$FRESH_SDK_DIRECTORY"
python3.11 -B "$S/delivery/qemu_source.py" reconstruct \
  --archive "$PRIMARY" --bundle "$S/delivery/qemu_bundle" \
  --destination "$FRESH_QEMU_DESTINATION"
```

`FRESH_SDK_DIRECTORY` must exist and be empty. `PRIMARY` is external
`qemu-10.2.0.tar.xz`, SHA256
`9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`.
Python requires `tarfile.data_filter`. QEMU reconstruction validates hashes,
preimages and full final inventory, but does not configure/build or run guests.
The primary archive, full extracted tree, QEMU binary, toolchains, disks and
models stay external; only the 98528-byte manifest and 255016-byte payload ship.

For complete-library preparation/build, the reviewed entry is
`runtime/library_build/plugin_v2.py` over `recipe.py`; retain its sealed host09,
tool and prepared-input receipts. It is not yet a standalone portable build
kit. BUILD07 used Python `/usr/bin/python3.11`, Ninja `/usr/bin/ninja` and
`--enable-fdt=internal` in addition to the manifest's source-prepare configure
arguments. Those manifest arguments alone are NOT the full BUILD07 recipe.
Source reconstruction is portable; binary reproduction needs the separately
pinned host/tool environment and build receipts.

Current verification entrypoints, not automatically authorized launch commands:
`qemu/gates/run_v10.py` (directed/ROM), `qemu/execution/run_v4.py` (same-image
QBS + unchanged Stage4 ELFs), and `models/launch_s3_v5/run.py` over sealed
`models/execution_v2` (model owner). Do not treat every older `run_vN.py` as a
final command. These workers retain inherited imports/pins and OUT receipts;
they are not made portable merely by copying their latest script.

## Remaining Acceptance

Require the same BUILD07 image for all native gates, checked instruction counts,
complete numerical outputs/flags and unsupported controls. Directed acceptance
alone does not close S3. Model owner must bind provider/launcher/library/model
identities and check complete logits/tokens, guest tokenization and actual
dispatch across the frozen five OFF/ON pairs. Only QEMU functional claims follow,
not RTL timing or end-to-end model acceleration. Parent reviews RESULTS.md,
the source-control inventory and final commits/tag before changing this status.
