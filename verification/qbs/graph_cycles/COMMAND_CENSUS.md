# Native command shape census

`command_census.c` is an isolated experiment harness, not a production runtime
change. Link with `-Wl,--wrap=qbs_native_execute_command` to intercept external
calls to the shared native executor from projection and quantized Attention.
The original executor remains responsible for validation and execution.

The caller supplies bounded storage and brackets one inference with begin and
finish. Each record retains descriptor header (including context access mode),
M, N, output stride, segmented flag, descriptor presence and returned status.
Records remain in call order; compare full records, not only totals or hashes.
No allocation, printing, timing, floating-point or vector operation belongs in
the wrapper. Build this object for RV64GC, with vectorization disabled, even
when the model is built for RV64GCV.

Overflow and nested begin invalidate the capture. They do not skip, retry or
replace the actual command. A failed finish must reject the evidence, not count
its retained prefix as a complete workload. Only a single caller is supported;
this is not a thread-safe counter. Storage must remain valid until finish.

This observes **software native-executor calls**, not hardware retirement or
all custom instructions. Descriptor/activation/output addresses and data are
not recorded, and helpers bypassing this executor are outside its scope.
Ordinary RVV, graph fusion and prepared-cache hits require separate evidence.
In particular, identical command shape sequences alone do not establish
identical input data or cache decisions. Full model output comparison remains
mandatory. The wrapper adds overhead and must not be used to report unperturbed
latency.

Host linkage/forwarding test:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror -Isoftware/qbs/include \
  verification/qbs/graph_cycles/command_census.c \
  verification/qbs/graph_cycles/command_census_mock.c \
  verification/qbs/graph_cycles/test_command_census.c \
  -Wl,--wrap=qbs_native_execute_command -o /tmp/command-census-test
/tmp/command-census-test
```

The 20261029 host run passes all seven forwarded calls, including disabled,
null-descriptor, overflow, nested capture, guard preservation and restart cases.
The separate mock translation unit checks all original arguments. GNU RV64GC
cross-compilation also passes; disassembly contains integer instructions only.
Artifacts: `verification/out/graph-command-census-host-20261029-01`.

Remaining integration: link a successor isolated model binary, confirm symbol
wrapping in its map/disassembly, capture and compare both modes' complete
records, and retain exact logits/CSR checks. This preparation is not yet a
model command-equivalence result and does not alter the already accepted
graph-probe binary.

`run_census.py --output <fresh-verification/out-directory>` prepares that
successor from the accepted graph-probe binary's exact source and libraries.
It retains the six complete-logit comparisons and adds full binary command
record comparisons after every inference. A fixed 1048576-record capacity
bounds memory; overflow fails evidence collection without suppressing commands.
The same collector is enabled in both modes. The final ELF disassembly must
show at least two wrapped callsites and no direct native-executor calls outside
the wrapper before QEMU may start. No production source or archived library is
rewritten. `test_census_check.py` exercises missing/mismatched/overflow records
and numerical-check failures before the model run.
