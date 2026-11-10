# Stage5 Evidence Ledger

Status: ACTIVE. Native instruction-model execution, actual GGML integration,
representative model regression and unified delivery remain incomplete.
Contract: `hardware/docs/INFERENCE_STAGE5_RUNTIME_DELIVERY_20261110.md`.
Output root: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.
Do not count historical emulated AKV model tests as native resident evidence.

## Trusted Platform Policy

`stage5_resident_platform_host_20261110_02/result.json` reports
`HOST_GNU_POLICY_PASS_NO_NATIVE`, SHA256
`4bba42d184802fefcdc9dae28e5e8d50188297dbc633f79a162c4bc57d1e1fc4`.
Six host tests pass; normal and UBSan executions each check88 policy assertions.
Parent and independent review confirm108 pins and110 artifacts match.
Source-pin SHA256:
`6e1626b7eaba164ffa7e946270815b0695e94ffe884874439620818b9611dd94`.

The six runtime files are frozen. The weak provider defaults to NULL; runtime
intent cannot grant availability. The versioned provider distinguishes a sealed
test deployment from an external deployment, requires safe scalar state access
before copies/discovery, and retains whole-call ownership and no-retry state.
There is no new hardware advertising or board acceptance. A real QEMU provider
must remain unaccepted until the instruction model and launch contract pass.
The native CSR reader has GNU inspection, not a claim of target execution.

Preserve attempt01 and its original diagnostics. Further semantic changes to
these sealed inputs require a successor and review, not mutation of a consumer's
frozen source. Source reconstruction and model inputs are still in preparation;
no Stage5 performance ratio is established.

## AKV Architecture State And Callback Model

`stage5_akv_model_host_20261110_02/result.json` reports
`HOST_MODEL_CALLBACK_PASS_NOT_QEMU`, SHA256
`e8242012b8fff3dc2faa63935e5dd73bc5985f61233684560d9570ff3971554a`.
Two host tests/configurations cover11 logical cases. Independent static review
and parent verification confirm all10 declared pins match. Source-pin SHA256:
`feb963022dd17335229b6c123b1418a02ef8b1f39c041e2fbbe12d345849fbf6`.

The four model/test files are frozen for adapter consumption. This checkpoint
checks lifecycle/layout, callback ordering and validation, using mock arithmetic.
It does not establish numerical acceptance, complete toolchain closure or native
QEMU execution. The successor adapter/build must bind these model bytes and
host02 evidence, then execute real SoftFloat/native gates and unchanged Stage4
ELFs. Preserve host01 and its diagnostics; no old model is overwritten.

## QEMU Adapter And Source Preparation

Adapter/decode/SoftFloat glue and fresh-build recipe are committed at
`cdbf7c90d`. The reviewed source03 identity is
`1b190a2502865f4f91c8a06c23ab93a498474a43c917474707ce3414430efabe`;
11 source-only checks pass. This establishes neither compilation nor execution.

`stage5_qemu_prepare_20261110_01` failed during safe extraction of the official
hash-matched archive: `roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack` is an
absolute symbolic link rejected by Python's data filter. Configure/compiler
execution never began. The failed preparation and diagnostics are preserved.
Before a successor preparation, enumerate unsafe links and review explicit safe
handling; do not disable the archive security filter or overwrite this attempt.
The accepted QBS source/build and all previous RTL/model evidence are untouched.

## Frozen Model Inputs And Held Harness

`stage5_models_prepare_20261110_04/result.json` is `PREPARED_HELD`, SHA256
`ae27251276ba052d232cf2bb3388f628069717fade303ec91e8bfa345ad662b2`.
Parent verified all2162 input pins with no drift. Eleven host checks and five
GNU syntax-only checks pass; missing-selector compilation is rejected.
Source-pin SHA256:
`9cb49d8f979d9dc99dba3dc8e2707dfd1928b787f3f0c225337b0c7f9440ebfe`.

Four pinned real models supply five OFF/ON pairs: Smol F16 boundary contexts,
Qwen3 F16 multi-tile contexts, two Qwen2.5 quantized-KV cases and Gemma D256
fallback. Model weights, disk contents, tokenizer assets and exact tokens are
bound. The matched host tokenizer only prepares vocabulary inputs; guest
re-tokenization remains mandatory. Neither its reported revision nor the held
commands establish a composed guest library or inference result.

Attempts01/02 retain tokenizer failures and ABI-mismatch evidence;03 remains
held with the earlier source-reference limitation. Models04 archives da56 and
an unapplied native-auto reference separately. Runtime reconciliation, selector,
instruction model, executable and execution-counter bindings remain required.
No inference or QEMU launch occurred. The future reviewed launcher must allow
emulator overhead above4GiB guest RAM (a6-8GiB host ceiling), rather than blindly
using the draft4GiB host limit. This is a successor binding change, not mutation
of the frozen preparation or a model-input change.

## Archive-Policy Successor And Reconstruction Preflight

The archive-policy v2 successor passes22 host checks, including hostile-link
tests and the complete official archive. Inventory is84624 members/73 links;
only the exact `X11IncludeHack -> /opt/X11/include` entry is excluded, with the
data filter retained for everything else. Source04 review identity:
`10f4fc05d16af2285fd7bec1e4c0455c3a6dc23617eb0a770dd6af6144d87824`.

Fresh `stage5_qemu_prepare_20261110_02` passes that extraction but then rejects
`roms/u-boot/include/ctype.h` during inherited-source overlay: a safe internal
symlink is represented by file content in the old source manifest, while the
overlay only allowed regular files. It remains FAIL, not a successful build.
No compiler/configure or guest ran. Before another preparation, preflight all
inherited entries, link destinations/content identities and integration anchors
against this already extracted tree. Any successor must avoid writing through
symlinks, preserve safe matching links, and reject escaping/conflicting content.

## GGML Overlay Control And Build Handoff

`stage5_ggml_overlay_host_20261110_09/result.json` is
`HOST_GNU_CONTROL_PASS_NO_NATIVE`, SHA256
`0a682a093837859d5cc43a2dd04e9859239827a839f4fedc4f9a76a838618f9c`.
Seven tests pass. Parent verifies3567 pins and3663 artifacts with no drift;
the independent review clears this control/build handoff, not native execution.
Source-pin SHA256:
`e1303ccc956a7ae3de2cd09f3a2915d3992c8207e0acb64db73ffc1fc449dc17`.

The frozen nine-file overlay reconstructs da56 plus reviewed auto-pair behavior
without copying the dirty runtime. Default/OFF object identity is preserved.
The ON build compiles seven real CMake objects and the native SDK leaves, while
the host control fixture stubs arithmetic/conversion execution. No complete
linked GGML library, native provider or numerical/model result is accepted.

Admission is explicit and default-deny before INFO. Legacy native, Prefill and
quantized-KV permissions are separately registered, not inferred from resident
profiles. All groups are preflighted before execution; whole-call ownership,
CSR handling, fallback and no-retry semantics are checked. Model counters are
control-path evidence only and must later match real instruction-model traces.
Stage4's preflight producer and feature-bearing resident variant are not promoted.
Attempts01..08 remain retained diagnostics; only host09 is this frozen checkpoint.

## Successful QEMU Source Reconstruction

V3/source05 passes34 host checks. The successor leaves all15 older adapter/
archive files and failed preparations unchanged. Source review identity:
`0b091570f4af0f07f45791ec25b97a554dcb1ec4fe29d3aa99de60291037ee23`.
Full preflight checks34940 inherited entries, all retained links, alias groups,
transforms and new destinations before any inherited-source copy.

`stage5_qemu_prepare_20261110_03/prepare.json` is `PREPARED_NOT_BUILT`, SHA256
`a947e2ebcaab10fbcb0480275746665e4ddcf2381a8282ebd66b7d239f3e6ea5`.
Source-pin SHA256:
`66fa102e49a37d134e8c92836d1f30ed826ba778dad9665dd599d34e089a9db9`.
It preserves72 safe links and the exact accepted QBS bytes. On the fresh archive
the plan keeps34799 regular files and10 symlinks, replaces8 regular files and
creates123. Different CREATE/KEEP counts from the earlier partially overlaid
failed tree are expected; the actual complete plan is validated before copying.
The sole unsafe archive member remains explicitly excluded, not followed.
Independent prepared-inventory review and direct-service compilation are next;
this receipt is not a binary or guest-execution acceptance.
