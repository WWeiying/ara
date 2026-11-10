# Frozen Native Libraries, No Execution

This successor owns only `recipe.py`, `test_recipe.py` and this README. It does
not modify the sealed six runtime files, nine overlay files, SDK, llama or QEMU.
Source review and preparation review precede a parent-launched library build.
There is no provider registration, inference, target execution or positive ISA
claim. The libraries can build while the separate QEMU package is being fixed.

## Closure

- Copy the fully rehashed host09 materialized llama tree: da56 + adapted06 +
  reviewed overlay09. Compare exact source file membership with the authoritative
  artifact subset, rejecting unlisted additions as well as missing/changed files.
  Never archive llama HEAD039 or copy the dirty repository.
- Archive `software/akv` and `software/qbs` from f50092f2d. Require AKV equality
  with host09 and Git-object byte equality with models04 c49289ff8 for both SDKs.
- Enable the preserved QBS and quantKV/quantized-Prefill/register-PV sources.
  Resident plain integration is ON, features-v2 remains OFF. OpenMP, native ISA
  inference, backend DL, ccache, LTO, tools/examples/server/common are OFF.
- Exact ISA/ABI: rv64gcv_zfh_zvfh/lp64d, no fast math, contraction OFF except
  the accepted quantKV source properties. No pthread/Linux replacements/stubs.
- Build four static archives: libllama.a, libggml.a, libggml-cpu.a, libggml-base.a.
  One ON library set serves runtime request OFF/ON; no second candidate build.
- Record compiler/wrapper/backend tools, include roots, target CRT/static
  libraries and host tool libraries before build. Check generated compile
  commands before build, then actual compiler dependencies and linker map.
  No live SDK/dependency path is allowed. Source membership and bytes must match
  before/after. CMake version text is not source identity; the pinned archive,
  overlay and source inventories are. Embedded commit label is da56+overlay09.

The three successor copies and live review identity are checked again before
PREPARED. The final build receipt binds commands.json by SHA256 as well as logs.

The link-only probe retains llama_decode and the experimental backend, verifies
static RISC-V linkage and both weak default-provider definitions. It is NEVER
run. Missing provider is deliberate: no accepted model/board availability follows
from compilation. A later accepted provider is an explicit object before the
archives, not an archive silently hidden behind already-resolved weak defaults.

## Review And Prepare

```sh
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/test_recipe.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_recipe_host_UNIQUE
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/recipe.py identity
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/recipe.py prepare --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_prepare_UNIQUE --reviewed-source-sha256 REVIEWED_SOURCE_SHA
```

`prepare` only freezes sources and queries tool metadata; it does not configure,
compile or link. Parent reviews prepare.json, source-pins.json, toolchain.json,
tree-inventory.json and metadata command logs before launching. Failed outputs
remain immutable. No retries, rebuild or source repairs occur automatically.

## Parent Launch

Use a new build output. PREP is the accepted preparation, SHA its prepare.json
SHA256. Replace UNIT with a unique `stage5-libraries-*.service` name. Service
stdout/stderr are intentionally outside source pins and outside frozen inputs.

```sh
systemd-run --user --unit=UNIT --property=Type=exec --property=RuntimeMaxSec=2100 --property=KillMode=control-group --property=TimeoutStopSec=30 --property=MemoryMax=8G --property=CPUQuota=400% --property=StandardOutput=append:PREP/service.stdout --property=StandardError=append:PREP/service.stderr --setenv=PYTHONNOUSERSITE=1 --setenv=PYTHONDONTWRITEBYTECODE=1 --setenv=PYTHONPATH= /usr/bin/python3 -B PREP/inputs/recipe.py build --prepared PREP --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_build_UNIQUE --reviewed-prepare-sha256 SHA --service UNIT
```

The Python worker must be the service MainPID in its exact CGroup. Four compiler
jobs only; a total 1800-second alarm covers configure/build/link/audit, with a
2100-second service guard for cleanup. Long work is not polled. build.json is
BUILT_NOT_EXECUTED only after archive/symbol/static-link/dependency/post-pin
checks. Failure preserves configure/build/link logs and the original report.

## Parfit Frontend Interface

Use prepare.json/build.json include dirs and the same CXX/flags. Public headers:
llama/include, llama/ggml/include, overlaid riscv directory (entry.h/platform.h),
SDK include and SDK experimental. Link frontend.o then a separately accepted
provider.o, `--start-group libllama.a libggml.a libggml-cpu.a libggml-base.a
--end-group -lm -pthread -ldl -latomic`, with `-static -no-pie`.

Do not run the default-NULL probe as a positive test. Do not link/bind a provider
until S3 image/model gates pass. Actual model ELF/launcher/provider identities,
resident/legacy retirement, numerical equality and CSR proof remain independent
future gates. No all-fallback result counts as resident integration acceptance.
