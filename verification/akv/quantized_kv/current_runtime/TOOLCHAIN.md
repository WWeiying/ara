# GNU toolchain inventory

Independent, bounded before/after identity check for the current RISC-V Linux
SDK. It does not modify or import the sealed graph/model workers. No frontend,
assembler, linker, model, QEMU or EDA tool is executed: only compiler-driver
queries and GNU `-###` (print commands, do not execute them) are used.

## What is recorded

- Invoked GCC/G++ aliases, all traversed directory/file symlinks, wrapper, its
  reported `.br_real` driver and SDK wrapper alias; GCC target/version/specs.
- Queried cc1/cc1plus, as, ld, collect2 and lto-wrapper, cross-checked against
  the dry-run plan where applicable; linker plugin paths from that plan.
- Actual GNU-selected sysroot and static startup files; `-l` archives selected
  for the fixed `rv64gcv_zfh_zvfh`, `lp64d`, static, pthread, math/dl link probe.
  This includes libc, libm, libdl, libpthread, libgcc/libgcc_eh and C++ libstdc++.
- SHA256, bytes and permission bits for each regular file, and raw query
  argv/stdout/stderr. Temporary GCC filenames alone are normalized in the
  semantic plan, preserving their reference relationships and extensions.

Each GNU query is bounded to 30 seconds. Environment is deliberately fixed:
PATH `/usr/bin:/bin`, C locale, `/tmp`, Buildroot wrapper debug ON and ccache OFF.
Do not pass extra compiler options through environment variables. Unsupported
tool spellings, unresolved bare filenames, non-archive/thin-archive `.a` files,
unexpected startup selection or split C/C++ SDK identities fail closed. No
generic linker-script or toolchain discovery framework is intended.

## Usage

From the signoff worktree, choose fresh independent output directories:

```
python3 -B verification/akv/quantized_kv/current_runtime/toolchain_inventory.py capture --output verification/out/quantkv-tools-before-UNIQUE
python3 -B verification/akv/quantized_kv/current_runtime/toolchain_inventory.py verify --inventory verification/out/quantkv-tools-before-UNIQUE/inventory.json --output verification/out/quantkv-tools-after-UNIQUE
python3 -B -m unittest discover -s verification/akv/quantized_kv/current_runtime -p test_toolchain_inventory.py
```

`capture` supports `--gcc` and `--gxx` absolute aliases. Defaults are the
existing cva6-qemu platform aliases, resolving to the SDK used by CMake.
`verify` first checks all saved file and symlink identities, then re-runs the
same queries and requires the entire semantic inventory to match. It never
overwrites the before receipt. Discovery/selection failures after directory
creation emit FAIL; malformed/drifted prior inputs can reject before creating
an output. A parent must separately pin inventory.json/result.json hashes.

## Scope limits

This is not a QEMU ABI update or compatibility proof. The existing native-QBS
QEMU may still expose legacy context capabilities. Nor is this a model-build
manifest: the old worker must continue checking actual compile flags, headers,
objects, ELF, model/disk and raw functional evidence. This fixed probe does not
inventory arbitrary extra project libraries, host shared-library dependencies
or all sysroot headers. Compare its selections with the actual model link
command. A capture made during a running build cannot retroactively prove the
compiler identity at that build's start; report that timing honestly.
