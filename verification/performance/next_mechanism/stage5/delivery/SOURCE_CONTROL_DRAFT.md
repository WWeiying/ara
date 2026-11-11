# Stage5 Source-Control Inventory DRAFT

Snapshot: 2026-11-10, before adding this inventory itself. Paths below are
relative to stage5. This is a review list, not git add authorization. No commit,
push or index staging was performed.

## Ownership And Selection

| Group | Proposed disposition | Dependency / final entry |
| --- | --- | --- |
| delivery/README.md, qemu_source.py, test_qemu_source.py | Include unchanged source trio | qemu_source.py is the sole portable QEMU source entry; standard library only |
| delivery/qemu_bundle/{manifest.json,payload.tar.xz} | Include exact small artifacts | Primary archive external; provenance in BUNDLE_AUDIT_20261110.md |
| DELIVERY_DRAFT.md, delivery/BUNDLE_AUDIT_20261110.md, delivery/SOURCE_CONTROL_DRAFT.md | Include draft documentation | Parent acceptance and RESULTS remain authoritative |
| qemu/execution/ | Include reviewed worker/checker/test closure, not only newest files | run_v4 -> check_v4 -> check_v3 -> check_v2 -> check.py; predecessors also provide worker preparation/launch logic |
| qemu/gates/ and rom_probe/ | Include reviewed directed/ROM worker and test closure | run_v10 is current entry; keep older versions only where inherited or required for retained evidence |
| models/binding_v1/ | Model-owner review required | Frozen binding preparation/checker/observation dependencies |
| models/execution/ and execution_v2/ | Model-owner review required | execution_v2 is current provider/worker lineage, not interchangeable with v1 |
| models/launch_s3_v5/ | Current model-launch candidate, acceptance pending | Uses sealed execution_v2 worker in OUT and qemu/execution/run_v4.py acceptance reader |
| models/launch_budget_v3/, launch_s3_v4/ | Historical/support only, not final launch choices | Keep if inherited, pinned, or needed to interpret preserved receipts |
| models/provider_os_smoke/ | Supporting probe evidence | Not a real-model or resident acceptance entry |

Tests should travel with their reviewed helpers. Existing README files may be
sealed dependencies and must remain unchanged. Version suffix does not alone
establish acceptance; retain the exact consumer inventories, including inherited
Markdown pins, before selecting a smaller closure. Do not delete predecessors
or old receipts as part of this list.

Already tracked and still necessary: runtime platform files; all nine
runtime/overlays inputs (prepare.py, auto_pair.patch, entry.c/h, resident.inc,
resident.cmake, host_control.cpp, test_overlay.py, CONTRACT.md); library_build
recipe/plugin and their tests/contracts; QEMU model, adapter, build validators;
original firmware/checkers and external QBS/Stage4 source dependencies.
No duplicate untracked copies of tracked runtime files are needed.

The portable source bundle eliminates old QEMU build helpers as reconstruction
dependencies. It does not eliminate their pins from historical acceptance
workers. The library and model harnesses still depend on sealed OUT receipts
and snapshots; do not advertise them as standalone portable tools yet.

Exclude multi-GB source/archive copies, QEMU executables, compiled SDK/libs,
toolchains, kernel/disk/initramfs images, model/tokenizer assets and run outputs
from this source change. Retain their external locations/hashes in evidence.

## Exact Untracked Snapshot

68 paths at this snapshot; model-agent additions may follow.
New inventory file itself: delivery/SOURCE_CONTROL_DRAFT.md.

```text
DELIVERY_DRAFT.md
delivery/BUNDLE_AUDIT_20261110.md
delivery/README.md
delivery/qemu_bundle/manifest.json
delivery/qemu_bundle/payload.tar.xz
delivery/qemu_source.py
delivery/test_qemu_source.py
models/binding_v1/README.md
models/binding_v1/check.py
models/binding_v1/observe.h
models/binding_v1/prepare.py
models/binding_v1/test_binding.py
models/execution/README.md
models/execution/check.py
models/execution/init.c
models/execution/provider.c
models/execution/provider_test.c
models/execution/run.py
models/execution/test_execution.py
models/execution_v2/README.md
models/execution_v2/check.py
models/execution_v2/csr_probe.S
models/execution_v2/csr_probe.c
models/execution_v2/init.c
models/execution_v2/probe.py
models/execution_v2/provider.c
models/execution_v2/provider_test.c
models/execution_v2/run.py
models/execution_v2/test_execution.py
models/launch_budget_v3/run.py
models/launch_budget_v3/test_run.py
models/launch_s3_v4/run.py
models/launch_s3_v4/test_run.py
models/launch_s3_v5/run.py
models/launch_s3_v5/test_run.py
models/provider_os_smoke/call.S
models/provider_os_smoke/run.py
models/provider_os_smoke/smoke.c
models/provider_shared_v3/provider.c
models/provider_shared_v3/run.py
models/provider_shared_v3/smoke.c
qemu/execution/audit_perf_numerical.py
qemu/execution/check.py
qemu/execution/check_v2.py
qemu/execution/check_v3.py
qemu/execution/check_v4.py
qemu/execution/run.py
qemu/execution/run_v2.py
qemu/execution/run_v3.py
qemu/execution/run_v4.py
qemu/execution/test_run.py
qemu/execution/test_run_v2.py
qemu/execution/test_run_v3.py
qemu/execution/test_run_v4.py
qemu/gates/rom_probe/issue.S
qemu/gates/rom_probe/main.c
qemu/gates/rom_probe/probe.py
qemu/gates/rom_probe/test_probe.py
qemu/gates/run.py
qemu/gates/run_v10.py
qemu/gates/run_v7.py
qemu/gates/run_v8.py
qemu/gates/run_v9.py
qemu/gates/test_run.py
qemu/gates/test_run_v10.py
qemu/gates/test_run_v7.py
qemu/gates/test_run_v8.py
qemu/gates/test_run_v9.py
```
