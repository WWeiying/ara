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

## First Build Configuration And Tool Preflight

Prepared03 independently passes78470 pins and84776 exact tree entries. The
parent launched `stage5-qemu-build-20261110-01.service` with the frozen v3 worker.
`stage5_qemu_build_20261110_01/build.json` is FAIL: configure chose system
Python3.9.21, which has no usable `tomli` in the minimal environment. Configure
exited after1.6s; no C compilation or guest execution began. The direct-service
failure/logs remain preserved, and prepared03 is not modified or re-extracted.

Parent prerequisite checks find Python3.11.13 with built-in tomllib, venv and
ensurepip; the pinned source contains Meson1.9.0 and pycotap1.3.1 wheels.
System pkg-config reports GLib2.68.4, pixman0.40.0 and zlib1.2.11. A reviewed
build-only successor must bind its interpreter/offline dependencies explicitly
while preserving environment isolation and the already accepted source tree.
Do not count service launch or a configure failure as an executing compiler.

## Directed Guest Firmware And Checker

`stage5_akv_directed_build_20261110_03/build.json` is
`DIRECTED_GUESTS_BUILT_NOT_EXECUTED`, SHA256
`ae70017f636067c87c490175a92c8bbb22227298debc08072893e83fa4f707fe`.
Three GNU ELFs and eight host checks pass. Parent verifies34 pins and61
artifacts; independent static review clears the frozen firmware/checker.
The main mode contains100 instruction steps; resident-OFF and AKV-OFF images
contain4 and2 steps. These are instruction steps, not independent test counts.

The INFO-check successor is separately frozen at
`stage5_akv_directed_info_host_20261110_01`: four host checks pass, no firmware
rebuild or guest execution. Original checker and failed build01 are retained;
build02/03 have identical ELF bytes, with03 carrying complete dependency and
disassembly evidence. The tests contain a real trap handler and independently
specified numerical constants, not a call into the model under test.

Native lifecycle/fault/flags acceptance still requires running all three modes
on the exact new QEMU executable, checking raw output/architectural events,
service completion, source/image identities and normal RVV coexistence.
The old native-QBS smoke is separately required. No such execution has yet
occurred, and built ELF or host markers cannot substitute for it.

## Explicit Build-Only Tool Environment

V4 changes only the build worker/tool preflight, reusing prepared03. Host02
passes9 checks; toolenv02 binds Python3.11, offline Meson1.9.0/pycotap1.3.1,
26 package checks,612 tool pins and516 artifacts. Independent review clears
build launch. Toolenv receipt SHA256:
`ffc26812e9e4de51bea4b9ef8c47411f88a5f8a5407580855c0f927d8aaf378d`.

Toolenv01 remains FAIL because its library audit attempted ldd on the Red Hat
pkg-config shell wrapper. The successor pins the wrapper, interpreter/rpm and
actual platform pkgconf, and applies ldd only to ELF inputs. Existing offline
bootstrap evidence is retained; no dependency is globally installed.

Parent launched `stage5-qemu-build-20261110-02.service` with the reviewed v4
worker and explicit Python/Ninja, bounds900/1800 seconds and four compiler jobs.
Launch is not compilation or binary acceptance; confirm actual process/log
progress and wait for terminal evidence before native guest execution. All
source03/V4 inputs remain sealed while this service consumes them.

## Internal FDT Selection And Third Build

BUILD02 remains FAIL at Meson configuration, after successful Python/offline
bootstrap. Both the old accepted and new build lack system `-lfdt`; the old
build used the internal dtc subproject. New `--disable-download` selects
`wrap_mode=nodownload`; meson.build2072-2097 then maps auto FDT to disabled even
when the internal sources exist. The missing-metadata hypothesis was checked
and rejected: the matching dtc Meson files are already present in prepared03.

The v5 build-only variant adds exactly `--enable-fdt=internal`, keeping download
disabled, prepared03, toolenv02, source code and all other options unchanged.
Eight host checks and independent final review pass. Source review identity:
`c715107e529d0ee04ce5aabdda0d3c03f479e627701d0489085067447a2aff97`.
Parent launched `stage5-qemu-build-20261110-03.service`, output
`stage5_qemu_build_20261110_03`, using the direct-owned v5 worker. This is a
launch milestone only; binary and guest acceptance require terminal evidence.

## Build03 Metadata Closure And Parallel Library Preparation

BUILD03 correctly enters the internal dtc project but stops before C compilation:
`subprojects/dtc/version_gen.h.in` is absent. This proves the previous declared
source-file integrity gate was not a complete build-asset closure. Parent reads
all accepted Meson introspection JSON, finding2941 existing source references
and exactly one absent reference in prepared03: that template. Old dtc Git
revision is `b6910bec11614980a21e46fbccc35934b671bd81`. A successor must bind
all required build assets and preserve prepared03, not add one unchecked live
file then retry. Ninja1.10.2 does not support `-t inputs`; that failed read-only
query is not counted as graph evidence.

In parallel, the complete static-library recipe passes12 host checks and source
review, but `stage5_libraries_prepare_20261110_01` fails a tool query before
configure/compilation. GCC's `-print-file-name=liblto_plugin.so` returns a basename;
`-print-prog-name` correctly locates the installed host compiler plugin. Its
configured GCC14.3.0 supports plugins/LTO; this is a query-category error, not a
missing target runtime. Preserve the failure and pin the correctly identified
compiler component rather than dropping the check or installing another toolchain.

## Static Libraries Enter Compilation; Generated Source Lock Is Identified

The compiler-program successor passes7 host checks and its complete metadata
audit. Preparation02 reuses authenticated preparation01 inputs without changing
the historical FAIL receipt. Parent independently verifies all7,585 source/tool
pins and reviews the worker patch. Preparation receipt SHA256:
`d702e1f46de9eddf1e516cd3f711f77c6c4faad43f526df73c94f6eb38ab8a22`.

Parent launches `stage5-libraries-build-20261110-01.service`, output
`stage5_libraries_build_20261110_01`, using the frozen preparation02 runner.
Configuration completes; the service CGroup contains CMake/Make and actual
RISC-V GCC compilation processes. This is compilation progress, not archive,
link, instruction-model or model-regression acceptance. The GGML configuration
prints commit label45e28f45c; source identity remains the separately authenticated
da56+overlay09 tree, not that automatically discovered label.

V6 host checks pass11 tests, but asset audit01 stops on source membership.
Independent review proves all78,470 original pins still match, with no original
file/link changes or missing entries. The sole addition is the empty generated
`subprojects/.wraplock`, created during BUILD03 configuration. Meson opens the
lock with `w+` and closes/unlocks it without deleting it. The original preparation
and failed audits remain preserved. A successor must distinguish this exact
empty generated file from source changes, including after the next configure.
V7 host checks pass10 tests; its asset audit02 remains FAIL at the structured
reference-count check. No QEMU C compilation or native guest execution has yet
been accepted; the count discrepancy must be explained before retrying.

## Complete Static Libraries And Fourth QEMU Build

Library build01 completes in326.23 seconds with222 translation units, four
static archives,776 recorded compiler dependencies, a successful static RISC-V
link-only probe and unchanged source/tool pins. Receipt SHA256:
`f47864d88068b2aec18b7f63c9578d2bfeabd9e59f3fde5c5b0b386ece3b21fd`.
The probe was not executed; both platform providers remain weak/default-NULL.
This closes the library compile/link prerequisite, not native model acceptance.

The QEMU reference-count failure is a census error, not another missing asset.
Normalizing relative paths across all eleven introspection files yields3,119
references:3,111 unchanged,7 reviewed overlay changes and the one known missing
template. The former2,941 assumption was not reproducible. The revised V7 host
checks pass12 tests; asset audit03 passes and compares all3,119 references.
The pre-correction V7 source snapshot and failed audits remain separate evidence.

Copied variant01 is PREPARED_NOT_BUILT, preserving all original source/input
bytes and link targets without hardlinks; only the Git-pinned dtc template is
added, and the generated empty lock is excluded from the copied source inputs.
Preparation receipt SHA256:
`34f60faabc1b8d3cdd9e261ac1dceb87bfedbce95cfa385f47cdd839d9986bcc`.
Parent launches `stage5-qemu-build-20261110-04.service` using final helper
identity `0b1ea7542c5e201525ac6605f7eaa9d66551aada5405cee17facd7aee675cd09`.
The worker retains four build jobs, offline/internal-FDT configuration and
before/after pin checks; only the exact empty Meson lock is admitted as generated
metadata. Actual QEMU compilation and subsequent native gates remain pending.

BUILD04 is terminal FAIL during configuration: dtc also requires
`libfdt/version.lds`. No QEMU C compilation occurred. The3,119-reference audit
was not a complete conditional build-input closure and must not be described
as one. The next preparation must compare the complete fixed-revision dtc
archive and restore all missing tracked inputs in one explicit manifest,
instead of repeating single-file additions. Variant01, BUILD04 and their
receipts remain preserved. The completed static libraries remain independent
of this source-packaging failure.

## Complete Dtc Restoration And Fifth Build

The fixed dtc archive contains310 tracked files. Variant01 retains116 identical
files and lacks194; no existing file differs in content. The successor restores
all194, including11 executable files, and records Git blob IDs, archive modes,
canonical modes and existing-file modes separately. The archive's group-write
bit is not confused with a content or execute-bit difference. The failed first
host check and its source snapshot are preserved; host02 passes12 tests.

A finite QEMU API review also finds one definite compile error before build:
the transport declares the obsolete `CharBackend` type. The new copy changes
that one declaration to `CharFrontend`, matching the fixed QEMU chardev API.
This is a separately recorded adapter patch, not a dtc change or an arithmetic
change. Original helpers and previous variants remain unchanged.

Variant02 preparation passes, SHA256:
`79d8477622dd33b24d9dd25a0cfc56ca55b01e6ef7c72ba13a80bd0d095bc210`.
Final helper identity:
`59d2e885689b0ba061bce9f7237633bdba288d16d70f0c59185965b1fc4654a3`.
The authorized direct worker launches exactly once as
`stage5-qemu-build-20261110-05.service`, with8GiB host memory, four build jobs
and a3,000-second service bound. This is a launch record, not successful
compilation, native instruction acceptance or model-regression evidence.

## Decoder Generation, RAM Admission And Sixth Build

BUILD05 reaches step1,603/1,694, then fails in the real decodetree generator:
the five AKV execution patterns leave the high seven bits unspecified. The
successor marks those bits ignored by decoding, retaining raw instruction bits
for the helper's reserved-field validation. They are not forced to zero, which
would reject resident operations. Real generator checks cover65,548 routing
inputs, including resident and reserved encodings. Four actual translation
units also pass independent compiler syntax probes using the generated headers.

Static review separately proves the RAM-only callback contract incomplete:
QEMU permits direct host-pointer reads of ROMD without setting TLB_MMIO. The
new copy classifies the backing MemoryRegion under an explicit RCU read lock,
requires non-ROM RAM and an in-range chunk, and unlocks before raising an
access exception. Guest read-only mappings backed by ordinary DRAM remain
eligible. A separate ROM-negative guest is prepared; its native result remains
pending. Host callback checks are not substituted for that execution.

The first successor preflight also identifies one new empty generated directory,
`tests/qemu-iotests/scratch`, created during BUILD05 configuration. All prior
file bytes and types match. The successor records that exact empty real
directory in the copied inventory; it does not broadly ignore directories or
delete original evidence. Earlier checks and source snapshots remain historical.

Final host04 passes12 tests with helper identity
`9b30fc522f1e258c8d85e7ed8ad51f4bbf522969fd2034541f973c4537466fd7`.
Variant03 passes preparation, receipt SHA256:
`655b1c715559885fa99e9bd353553299330b6e46e27ee744a63a7c62a5a28855`.
The authorized direct worker launches once as
`stage5-qemu-build-20261110-06.service`, retaining8GiB/four jobs/3,000 seconds.
No successful executable or guest/model acceptance is claimed from launch.
