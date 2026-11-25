# Full-model Direct-U candidate packaging

Build preparation only. No board acceptance, timing result, zero-cost claim,
RTL execution, QEMU execution, or new FPGA acceptance follows from this recipe.
The validated 20261029 delivery remains a separate hardware/software contract.
This candidate needs a manually installed Direct-U v4 kernel and matching new
gate bitstream; the old bitstream is not supported.

## Ownership and source freeze

Only this new directory is owned by the packaging task. No core, RTL, existing
helpers, or old output inputs are edited. Before changing a recipe already
consumed by a worker, inspect that worker's source-pins.json and use a successor
recipe if sealed. Do not run the command below until the parent reports helper
and integration tests passing and explicitly approves a stable source freeze.

`build.py` requires both `--sources-stable` and `--stability-note`. It checks Ara
HEAD `4a7361f51ba5447a616217dad1c8e72e3ee2b45b` and llama.cpp HEAD
`a2b7f30da9aadf88b0a068c447383ed2e26ee867`. Its archives are ordinary build inputs,
not worktrees. It archives all llama.cpp HEAD and Ara HEAD's software/qbs,
software/akv, and software/llama, then applies only:

- The eleven SDK overlays listed in `SDK_OVERLAYS`, matching
  `../direct_cost/build_compact.py` exactly.
- The three current Direct-U client files in `DIRECT_OVERLAYS`.
- llama.cpp `ggml/src/ggml-cpu/CMakeLists.txt`, RISC-V `akv.cpp`, `resident.inc`,
  `linux-direct.cpp`, `linux-direct.h`, and `examples/simple/simple.cpp`.

No other working-tree delta is imported. In particular, dirty
`software/akv/src/akv_v2_attention_rvv.S` is forbidden as an overlay; the archived
version is hashed before and after overlay application. Additional overlay paths
require agreement and a recipe/test change, not a command-line escape hatch.

## Controlled-Test Contract

Before CMake, `pins/candidate-contract.json` binds frozen source/overlay and
launcher hashes to the selected package
`resident_direct_delivery_compact_20261113_02`. That package supplies:

- `kernel/Image`, SHA256
  `d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1`.
- The v4 kernel build result and package manifest.
- Four-file gate baseline/candidate hashes, prerequisite and gate patches, and
  focused validation evidence. This is not a whole-core or board result.

The contract SHA256 is passed as `GGML_RISCV_AKV_DIRECT_CONTRACT_SHA256` and checked
in linux-direct.cpp's compile command. The contract requires root, one CPU/worker,
exclusive ownership, static RV64 Linux, RVV/Zfh/Zvfh, normal RAM rather than MMIO,
and immutable file mappings. These are deployment prerequisites, not observations
of the running board. Its flags explicitly say test-only, board-pending, no
hardware acceptance, and no automatic board attestation. The ELF hash is recorded
after linking, separately from its source contract to avoid a circular digest.

## Future Build

After parent approval, use a new output basename on every attempt:

```sh
python3 -B verification/performance/resident_deployment/direct_model/build.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_direct_model_NAME \
  --sources-stable --stability-note 'parent approval; passing helper/integration evidence paths' \
  --jobs 4
```

For a background build, let a transient systemd service own this Python worker
directly; do not launch a background child from a short-lived service. No retries,
existing-output reuse, or automatic source modifications are performed.

The GNU-only toolchain uses the specified platforms/cva6-qemu gcc/g++ and assembler,
`rv64gcv_zfh_zvfh`, and lp64d. No ZCC or custom assembler is used. CMake builds only
static `llama-simple`, with Direct-U, Resident, compact coefficients, QBS, AKV,
AUTO and existing beneficial paths enabled, portal/shared/native/OpenMP/dynamic
backends disabled. Runtime workers remain one regardless of `--jobs`.

Outputs include archives, overlay receipts, source pins, candidate contract,
tool/static-library hashes, sanitized environment, commands, configure/build logs,
compile database/cache, link map, ELF headers, nm, disassembly, required-symbol
audit, artifact hashes, and checksummed `board.tar`. Archives normalize ordering,
timestamps and ownership; compiler paths are prefix-mapped and SOURCE_DATE_EPOCH
is fixed. This prepares reproducible inputs; bit-for-bit rebuild equivalence has
not been measured. Failure retains original logs and a FAIL result.

## Board Runner

Install the kernel v4/new gate manually and perform independent board safety and
memory preflight first. This package never programs a board or installs a kernel.
On the board, set operator assertions explicitly:

```sh
export ARA_DIRECT_PREFLIGHT_ACK=kernel-v4-new-gate-single-worker
export ARA_DIRECT_SINGLE_WORKER=yes
export ARA_DIRECT_MEMORY_ACK=normal-ram-no-mmio-immutable-model
export ARA_DIRECT_POLICY_ACK=helper-owned-locks-no-external-policy
export ARA_DIRECT_CONTRACT_SHA256=<candidate-contract.sha256 value>
export BOARD_ID=<board identifier>
export BOARD_CLOCK_HZ=<measured or configuration-verified clock frequency>
export BOARD_HART=0
export BITSTREAM_SHA256=<manually verified installed new-gate bitstream hash>
export KERNEL_SHA256=d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1
export ARA_DIRECT_DIAGNOSTIC=1
sh run_board.sh resident /models/model.gguf /results/fresh-diagnostic 'A fixed prompt' 4
```

Modes are `rvv`, `native`, and `resident`. Native explicitly disables Resident
despite AUTO; RVV disables QBS/AKV/AUTO/Resident. Emulation is always disabled in a
clean environment. A `-h` usage check accepts examples/simple's expected exit 1
and verifies actual options before running `-fa on --kv-type f16 -t 1 -ngl 0`.
The prompt is one positional argument, not an unsupported `-p` flag. No hidden
flash-attention default is assumed. Model and ELF hashes, exact argv/environment,
stdout/stderr and return code are retained. `GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY`
stays zero: this launcher never grants that authority. Runtime admission and RVV
fallback remain in the backend; selecting a mode does not prove an accelerated
path executed. Successful exit is `EXECUTED_UNVERIFIED`, not correctness or speedup
acceptance. Compare outputs and independently inspect path admission afterwards.

The runner sets `ulimit -l unlimited` before either help or model execution and
records the before/after limits. Failure stops execution rather than allowing a
small default memlock limit to silently turn Direct-U into fallback. It records
operator-supplied clock/hart metadata without programming or guessing clocks;
use `BOARD_CLOCK_HZ=50000000` only for a verified 50 MHz configuration.

First collect four-token diagnostics for RVV, native and resident with the same
model/prompt after independent new-gate/v4 qualification. `ARA_DIRECT_DIAGNOSTIC=1`
enables AKV/QBS traces and `LLAMA_SIMPLE_LOGITS_FILE` at `out/logits.bin`. Raw
coverage counters go to `counters.txt`; both native and resident diagnostics need
inspection of `legacy_calls`/`legacy_completed`, and actual `resident_groups>0`
is required to demonstrate a resident path. Zero/missing groups, shape fallback,
or a successful exit alone is not evidence of resident acceleration. Compare
logits independently. This recipe preserves counts without manufacturing PASS.

Only after those checks collect separate fresh performance runs with
`ARA_DIRECT_DIAGNOSTIC=0` (the default), which disables traces and omits the logits
file environment variable. Diagnostic runs are not performance samples. Copies,
hashing, limit setup, and metadata collection remain outside model timers; the
runner does not infer cycle counts from the operator clock declaration.

The fixed llama-simple candidate retains the default `use_mlock=false`: the
Direct-U helper owns locking, and the launcher only raises RLIMIT_MEMLOCK.
Its maps inventory caches the smaps audit, not independent proof of lock state.
External munlock/mlock-policy, madvise, userfault and foreign mapping changes are
forbidden without `ggml_akv_direct::invalidate()` before an allowed out-of-lease
change. No such changes are permitted during a lease. A stable maps inventory
must not be used to assume these policies remained unchanged.

Trace-only `GGML_AKV_DIRECT_PREP` summaries preserve prepares, maps, smaps,
cache_hits, mlock, acquire_attempts, releases and last_error. The helper checks
maps for each preparation, reuses smaps evidence only while its inventory is
unchanged, and locks once for the admitted process. These operations and lease
acquisition/release still cost time; neither caching nor lack of per-node logging
proves zero overhead. Diagnostics retain the raw summary rather than estimating
or subtracting those costs.

## Host Tests

```sh
python3 -B -m unittest discover -s verification/performance/resident_deployment/direct_model -p 'test_*.py' -v
sh -n verification/performance/resident_deployment/direct_model/run_board.sh
```

Tests use synthetic temporary Git repositories and shell executables, not live
SDK/model freezes, a cross-compiler, a simulator, or a board. Mock runner copies
replace only physical-board probes. Production has no test bypass. ShellCheck is
optional when installed; `sh -n` and executed mock-shell tests are always used.
