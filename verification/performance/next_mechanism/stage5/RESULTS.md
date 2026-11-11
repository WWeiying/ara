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

## QEMU Build06 Completes; Real Linux CSR Behavior Is Measured

BUILD06 completes all1,694 Ninja steps and links successfully. Both configure
and build commands return0; the directly owned service exits0. The receipt
records unchanged post-build pins. Parent and independent review verify the
executable SHA256:
`1deb41c75cc507030994765971d5a3d91f17e958c195bf60b4fb5563eb880a6f`.
Build receipt SHA256:
`93506639dda6fc22dc66733ca2160c5ba7b799787e8fb8f5e4d067ed37d3c3d6`.
This closes the native-emulator compile/link prerequisite. Directed instruction,
ROM-negative, unchanged-ELF, QBS and model execution gates remain independent.

A separate standard-RVV probe boots the actual pinned Linux Image once under
the old accepted QBS-only emulator; it does not execute AKV or a model. Six
raw samples show that getpid clears nonzero VSTART and resets VL/VTYPE, whereas
FCSR/VCSR remain unchanged. No-syscall controls preserve all sampled state.
The child exits0. Parent independently rehashes all138 probe input pins with
zero differences; result receipt SHA256:
`4951e7f36a1ee7b2df074721ddda9ddf6954fa3b6a08a91f41acb6b24a57a1ad`.

Consequently the initial model provider must not issue a syscall before its
VSTART-first check. The execution_v2 successor performs OS preauthorization
outside the seeded ROI, makes state/release syscall-free, and retains actual
OS/task/affinity/mapping admission with incoming-state checks and scalar CSR
restoration around acquire. Static/link/host review is not model acceptance;
the actual model launch still requires the same four successful native gates.

## First Native Runs Identify Checker And Transport Issues

The BUILD06 QBS guest actually executes and exits0. Its original aggregate
remains FAIL because the new checker incorrectly requires opcode-valued mtval
for every illegal-instruction trap. Independent raw/source review finds190
native instruction attempts and69 traps with matching order, PCs and causes:
46 helper illegal traps report0,3 decoder illegal traps report the opcode,
and20 access traps report their precise addresses. QEMU's state restoration
overwrites the helper's earlier bins assignment. The original firmware already
accepts the ISA-permitted illegal mtval alternatives. A separate source-stage
checker correction verifies exact values per case, not an unrestricted union;
the original failed worker is never relabeled PASS. This audit is BUILD06-only.

The first BUILD06 directed AKV run times out after case44 output. The next
case is the unaligned FULL negative test: the model returns an opcode-valued
front-admission fault, but the adapter loses that value during CPU restoration.
The fatal handler then uses a32-bit EOC store, while the new transport accepts
only64-bit accesses, producing repeated nested faults instead of exiting.
This is not evidence of a new RTL arithmetic failure or a passing full suite.

The V10 copied successor restores precise CPU state before applying the model's
illegal tval, then raises without a second restore. Its transport accepts the
additional32-bit EOC write only at offset0, preserving other access policies
and full64-bit nonzero failure values. The QBS helper and every original ELF
and numerical oracle remain unchanged. Finite compiler checks and10 host tests
pass; final source identity is
`256fe96bb36cf229734d5b0427e77b360ea812a63128f38e3eef43b382389231`.
The next image must execute all required gates itself; BUILD06 QBS evidence
cannot be mixed into a different-image acceptance aggregate.

## BUILD07 Directed Native Acceptance

BUILD07 completes configure, compilation and linking, with executable SHA256
`1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a`.
The new directed worker executes all three original ELFs and the independent
ROM-negative ELF on that same image. Its result is DIRECTED_NATIVE_AKV_CHECKED,
receipt SHA256
`4968224d1a0cd7023e21f61aa17699d6dfc1688b81240892aaf5f60bf52aea16`.
The enabled mode checks100 cases/10,392 output records/30 traps, including31
successful resident operations. Resident-disabled4 cases and AKV-disabled2
cases pass with zero successful resident operations. The ROM negative reports
cause5/tval0x1000, unchanged CSRs, no descriptor read and no helper completion.
These are QEMU architectural/function checks, not fresh RTL performance results.

The unchanged performance ELF also exits0 on BUILD07. Independent use of the
original numerical checker verifies4 calls/1,024 bit-exact outputs, FCSR
`[3,11,3,11]` and VCSR/VSTART guards. Its worker remains FAIL because the added
activity checker undercounts capability queries. Frozen caller/native-selection
sources imply one outer query plus one query per eligible paired group, not
one query total. The successor must retain exact source-derived, shape-sensitive
counts, including multi-group and early-rejection shapes, without modifying
the firmware or numerical oracle. Fresh same-image three-ELF execution remains
required before the combined S3 gate can pass.

## Same-Image Three-ELF Regression Passes

Fresh worker `stage5_qemu_execution_20261110_03` runs all three original ELFs
on BUILD07 and finishes NATIVE_QEMU_THREE_GATES_CHECKED. Receipt SHA256:
`09792bce390c67d3136dc95dd561d0ba96e1f1ce24a30a28fbc55a96f922b15c`.
QBS checks190 instruction attempts and69 exact source-stage traps. The original
performance oracle checks4 calls/1,024 bit-exact outputs/FCSR `[3,11,3,11]`.
The original functional oracle checks18 calls/2,816 bit-exact outputs, including
the non-RNE pair, floating flags and VCSR/VSTART. Exact group-sensitive INFO
counts, SDK entries, native/resident instruction order, snapshot reads, local
flags and context lifecycles also pass. The failed earlier workers remain FAIL.

Before model execution, static review finds that llama's frozen mmap loader
uses MAP_SHARED/PROT_READ. The private-only provider would wrongly deny that
normal read-only model mapping. A separate provider_shared_v3 source changes
only that permission check: the exact pinned model path may be `r--s`, never
writable or executable; other shared/unknown mappings remain denied. Actual
OS smoke confirms the model's shared read-only mapping and16 callback/CSR
checks. Its original worker remains FAIL because its checker additionally
expected an unknown-file shared negative that the firmware only ran privately.
The independent scoped audit explicitly retains that limitation; unknown-shared
denial has host evidence only. No model result follows from this smoke.

The combined native gate now completes as NATIVE_QEMU_FOUR_GATES_CHECKED in
`stage5_qemu_four_gates_20261110_03`. Receipt SHA256:
`d1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0`.
All four gates bind BUILD07 executable
`1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a`;
the combination includes actual ROM rejection and does not credit historical
BUILD06 runs. Full-model graph/path/numerical acceptance remains pending.

## First Complete Model Pair And Scoped Checker Correction

The real SmolLM2 pair executes to Linux child exit0 with the same ELF/model,
63-token prompt and teacher-forced Decode contexts64/65. All147,456 logits,
greedy tokens and architectural CSR values match bitwise. OFF executes60 native
Decode calls/180 groups; ON executes60 resident calls/180 groups. Architectural
traces verify540 QK and540 PV resident commands across the two Decode steps,
and180 FULL/90 REFILL/180 RELEASE operations. Each arm executes90,378 native
QBS command entries with matching complete per-format work summaries.

The original worker remains FAIL: it incorrectly expects accelerated Prefill
completion for every non-D256 model. The compiled source sets GGML_FA_TILE_Q=64
and explicitly declines the numerically distinct short-Prefill path. The actual
63-token Smol Prefill correctly falls back in both arms, with30 size-decline
records each and no AKV computation. A source-bound successor checks this exact
case rather than accepting arbitrary fallback. It also subtracts explicitly
cancelled pre-execution TB trace records, using the fixed QEMU trace semantics;
entry attempts are not described as instruction retirements.

Independent complete-log replay succeeds; the separate final audit rechecks
all406,566 original pins and preserves the failed original worker. Result:
`stage5_models_smol_prefill_audit_20261110_02/result.json`, SHA256
`0887a6da31d749c4f7cb4d400f3b2b7777d9a7f57c6c25a5f491543baaa61a26`.
This is scoped full-model functional/path evidence, not a relabeling of the
original worker, a QEMU speedup or completion of the five-pair matrix.

The two Qwen2.5 quantized-KV cases are launched in independent direct-owned
services using the unchanged prepared model ELFs and an explicitly bound
successor checker. Qwen3 F16 and Gemma D256 preparations are also available;
their execution results remain pending. No failed model case counts as verified
coverage merely because it exercised the new path.

## Bounded Observation Policy And Planned Verbose-Run Stops

At approximately51 minutes the two verbose Qwen2.5 guests are still executing
OFF Prefill. Their remaining command work predicts that completing both arms
will exceed the original5,400-second limit. Parent stops those two services
before spending the remaining budget on predictably incomplete runs, preserving
all inputs, logs, attempts and explicit stop-reason.json files. No result.json
or PASS is fabricated. This is a planned resource stop, not a numerical bug.

The low-overhead observation policy retains identical model inputs, computation,
libraries and whole-output checks. It disables only QBS TRACE_CALLS,
TRACE_LIFETIME and TRACE_M4_PREPARE diagnostics, while retaining main TRACE
summaries/counters. Source review confirms these controls affect printing and
diagnostic snapshots, not context-reuse decisions or numerical execution.
The QBS/PV_PREP trace filter retains their entry PCs rather than entire function
ranges; AKV architectural events and all logits remain enabled.

A same-image/same-ELF control in ordinary TCG TB mode (not one-insn-per-tb)
checks unchanged entry/required-PC counts and successful exits under both
filters. Its trace sizes are344,510 versus26,396 bytes. These are observation
cost/semantics data, not RTL or model speedups. Raw evidence is
`stage5_models_observability_normal_tb_smoke_20261110_01/result.json`.

Qwen3 and Gemma use fresh, separately pinned diagnostic-only frontend relinks:
models, tokens, provider and SDK/libraries are unchanged, and both arms still
share one ELF. Parent launches both directly owned services with single vCPU,
8GiB host cap and10,000-second guest/12,600-second whole-service limits. The
extra service time includes pre/post identity checks; it is not an instruction
or model-performance claim. The original Qwen2.5 outputs remain sealed, and
their quiet successors require fresh preparations and execution evidence.

## Gemma D256 Fallback Pair Passes

`stage5_models_execution_final_gemma_20261110_01` completes MODEL_PAIR_CHECKED
with post-input pins matching. Receipt SHA256:
`ecdb0e109049cbbe12993607bc4715333e2f53aed150519108e0ce17cbff2d49`.
All786,432 logits, greedy tokens and CSR observations match across the pair.
Every phase takes the explicitly expected D256 legacy fallback; both arms have
zero resident calls/groups and zero AKV computation events. Native QBS work
remains independently checked. This is unsupported-shape correctness evidence,
not positive Resident acceleration coverage.

Qwen3 remains on its original bounded quiet run. Parent uses the freed slot to
launch fresh `stage5_models_execution_final_qwen25q4_20261110_02`, using its
reviewed quiet assets and the same model/tokens/libraries. The Qwen2.5 Q8/Q8
successor is prepared but waits for a slot; model concurrency remains two.

## Quantized-KV Command Accounting Correction In Progress

The quiet Qwen2.5 Q4/Q8 KV pair completes both guest children and reports
GUEST_TEST_EXIT=0. The unchanged full-content checker confirms455,808 logits,
greedy tokens and CSR observations match. Its original worker remains FAIL:
`QBS native-entry hits differ from complete command summaries`, receipt SHA256
`512631cde200190d26ebf3d1499b49fe7e636d0f19c04afd657ffc7c64f8cd37`.

Compiled qbs.cpp has two command routes. Projection execute_command updates
the per-format summary, whereas quantized Attention's execute_direct_command
calls the same native function without updating those projection counters.
Each arm has486,132 projection commands plus5,600 direct Attention commands:
28 layers times184 Prefill commands, followed by28 times8 commands in each
of two Decode calls. This equals491,732 observed native entries exactly.
Both arms have identical phase counts401,148 /45,292 /45,292, after excluding
the explicitly cancelled pre-execution TB records. Entry counts are not
instruction retirement or performance measurements.

A separate source-bound checker/audit is being reviewed; it must verify the
exact per-layer quantized Prefill/Decode records and independently derived
shape work, not merely allow arbitrary excess entries. The original failure,
log and preparations are preserved. The Q8/Q8 successor is held until that
correction passes review; no model or computational code is changed.

The successor now passes24 checker/launcher tests, including a complete raw-log
replay, mutation rejection, exact field/layer/phase accounting and both fixed
Q4/Q8 and Q8/Q8 shapes. Independent source review clears its mapped inputs and
pin-preserving launcher. A directly owned background audit is rehashing the
original Q4/Q8 evidence; its terminal acceptance remains pending. The final
Q8/Q8 model service is launched with the same frozen quiet assets and this
explicitly pinned checker extension. Qwen3 has completed both guest arms and
is in final checking; no result is presumed until its receipt exists.

## Qwen3 Positive Resident Pair And Quantized-KV Audit Pass

Qwen3 F16 completes MODEL_PAIR_CHECKED with post-input pins matching. Receipt:
`stage5_models_execution_final_qwen3_20261110_01/result.json`, SHA256
`d2f48995def4627f844b3969146dfbf4af0918b252bb968f937ac8d483da188c`.
All455,808 logits, greedy tokens and CSR observations match. Each of the two
ON Decode calls has28 resident calls/224 groups and672 actual QK plus672 PV
architectural events; the corresponding OFF calls have28 native calls and no
resident execution. Prefill retains its existing native path. Each arm has
644,580 independently checked QBS native entries. This proves real D128 model
selection and numerical agreement, not QEMU or end-to-end performance.

The separate Qwen2.5 Q4/Q8 KV audit passes with all406,594 original/binding/
audit pins verified before and after replay and102 source dependencies checked.
Receipt: `stage5_models_quant_audit_q4_20261110_01/result.json`, SHA256
`330965770cdfea0425b38151341e133a7259261fd8d205095ee6f0abd01df6d5`;
checked proof SHA256
`cdfcb30606e11b8ac717eb524d5dc2645a925d9edaace585c7dd8676111061b9`.
All455,808 logits/tokens/CSRs match. Both arms retain the original quantized-KV
route, with28 successful legacy calls per phase and no resident computation.
Its original projection-only checker FAIL remains unchanged. The final Q8/Q8
pair is still in progress; four of the five finite model pairs are accepted.

## All Five Model Pairs Accepted; Full Source Replay Finding

Qwen2.5 Q8/Q8 KV completes MODEL_PAIR_CHECKED with post-input pins matching.
Receipt: `stage5_models_execution_final_qwen25q8_20261110_02/result.json`, SHA256
`5485406147300124a25d4972ae6e48fdee525bb9969bc8793c46456819b45908`.
All455,808 logits, greedy tokens and CSR observations agree. Per arm486,132
projection commands plus5,600 quantized Attention commands equal491,732 native
entries. The six phases each have28 successful legacy calls, no resident
execution and no denied/failed admissions. Q4 and Q8 K-cache encodings are
checked separately against their exact source-derived row-byte/layout fields.

The five accepted pairs compare2,301,312 FP32 logits in total. Positive resident
coverage comes from Smol D64 and Qwen3 D128; quantized KV and Gemma D256 establish
preserved alternative/fallback routes, not resident speedups. There is no
remaining model guest, synthesized design or FPGA run required by this phase.

The additional real full-source reconstruction into
`stage5_source_reconstruct_20261110_01` fails its final inventory check. Preserve
that destination and stderr/stdout logs. The small bundle tests and in-memory
delta replay did not prove actual extraction identity. S5 remains open until
the exact difference is diagnosed, a reviewed successor fixes reconstruction,
and a fresh actual full-source replay passes without weakening the inventory.

## Final Source Reconstruction And Stage5 Delivery

The complete inventory comparison finds exactly two differences: safe symlink
targets under `subprojects/libvduse/{linux-headers,standard-headers}/linux`
lost their trailing slash in tarfile.data_filter. There are no missing/extra
entries, file-content, type or executable-bit differences. The successor
`delivery/qemu_source_v2.py` first performs the same safety filter, then retains
the already authenticated original symlink spelling; all inventory and unsafe
link rejection checks remain unchanged. The original helper, payload, manifest,
failed root and logs are preserved. Seventeen successor tests pass.

Actual fresh reconstruction into `stage5_source_reconstruct_20261110_02`
exits successfully with SOURCE_RECONSTRUCTED_NOT_BUILT and empty stderr. All
84,955 entries match:78,571 files,6,312 directories,72 symlinks,695,458,426
regular-file bytes. Final inventory SHA256:
`164d0a470c70b2d524956608c7aeb0533ab503b797f749978931838647c1bc56`.
This is a complete source reconstruction, not a new compiled binary or model run.

`delivery/manifest.json` binds the five accepted model pairs, original failures,
scoped audits, executed ELFs/commands, fixed model/disk/token identities, native
gates, libraries, source bundle, reconstruction and reviewed entrypoints.
The final reader entry is `hardware/docs/INFERENCE_STAGE5_DELIVERY_20261110.md`.
The earlier DELIVERY_DRAFT remains explicitly historical. Independent review
corrects prototype-versus-SDK performance attribution, provider mapping scope
and the interpretation of Resident-OFF; no test expectation is weakened.

S1-S5 are closed within their finite experimental contract. All five models
share BUILD07, the checked full-library build and the same reviewed provider
source. Main RTL and committed SDK paths remain identical to Stage4 c492;
unrelated dirty files and the user's uncommitted AKV assembly are excluded.
The annotated local release tag is `stage5-ggml-resident-20261110`. It does not
authorize default Resident promotion, FPGA eligibility, new PPA or model-level
performance claims. No further model/synthesis/board campaign is required by
the completed Stage5 contract.
