# Compiler Program Successor

New owned files: plugin_v2.py, test_plugin_v2.py, PLUGIN_V2.md. Original three
library helpers, runtime six, overlay nine and FAIL01 remain unchanged.

GCC 14.3.0 is configured with --enable-plugins --enable-lto. Its target-library
search `-print-file-name=liblto_plugin.so` returns a bare basename; the correct
host/compiler search is `-print-prog-name=liblto_plugin.so`. The static link
driver still passes `collect2 -plugin <host DSO>` without -flto. Thus LTO OFF does
not justify deleting the plugin pin. V2 moves it into the existing compiler
program query/pin/ldd path; the 13 mandatory target runtime names are unchanged.
Target runtime directories are hashed once per unique directory, without
removing any sibling-library pins. No toolchain, flags or global setting changes.

`audit` performs bounded metadata queries and the corrected complete tool audit,
not CMake or compilation. It preserves the -### command, host ELF classification,
program path/hash and ldd evidence. `prepare` consumes that audited inventory,
so it does not repeat compiler header/library discovery. No target ELF is run.

FAIL01 is not relabeled. Its complete inputs are authenticated against host09,
the f500 Git-object SDK archive, the original helper hashes and link-probe text.
V2 reuses those exact paths; it does not copy/extract a new large source tree or
write into old inputs. New runner and pin/inventory receipts are in prepare02.
The generated worker.patch records the two query-class edits, directory hash
deduplication, and explicit historical data-root/runner identity adaptations.
Every source/sdk/inventory/link/compile-policy path uses `input_prepared`.
Runner membership is checked separately, before and after build.

Prepare schema is `stage5-libraries-prepare-v2`. The inherited build report
remains `stage5-libraries-build-v1` and binds the v2 prepare SHA; downstream must
verify that chain, not infer the preparation schema from the build schema.
ABI, include files, compiler flags and static library link order are unchanged.
There is still no provider grant, inference or QEMU acceptance.

```sh
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/test_plugin_v2.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_plugin_host_UNIQUE
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/plugin_v2.py identity
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/plugin_v2.py audit --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_tool_audit_UNIQUE
python3 -B verification/performance/next_mechanism/stage5/runtime/library_build/plugin_v2.py prepare --audit AUDIT --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_libraries_prepare_UNIQUE --reviewed-source-sha256 SOURCE_SHA --reviewed-audit-sha256 AUDIT_SHA
```

The parent launches the corrected frozen `PREP/runner/recipe.py build`, not the
old `PREP/inputs/recipe.py`. See the original README for direct systemd settings:
four jobs, total worker deadline1800s, service guard2100s, MemoryMax8G, MainPID and
CGroup identity, no shell launcher. The worker uses only authenticated FAIL01
sources and its new immutable runner. Default providers remain NULL. A later
provider object is permitted only after the independent S3 execution gates.
