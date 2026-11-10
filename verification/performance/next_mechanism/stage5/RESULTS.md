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
