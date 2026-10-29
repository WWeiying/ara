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

The successor integration described below does not alter the already accepted
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

## Accepted model command comparison

`verification/out/graph-command-model-20261029-02` completed PASS. This is the
same Qwen3-1.7B Q4_K_M model, 40-token prompt, context 128, single worker,
Q8_0/Q4_0 K-cache pair and Q8_0 V-cache as the graph-probe functional test.
The probe is OFF in the first child and ON in the second. Command capture is
enabled identically in both.

| K-cache | Inference step | OFF native calls | ON native calls | Full shape/status sequence |
| --- | --- | ---: | ---: | --- |
| Q8_0 | Prefill | 189772 | 189772 | Exact |
| Q8_0 | Decode 1 | 23116 | 23116 | Exact |
| Q8_0 | Decode 2 | 23116 | 23116 | Exact |
| Q4_0 | Prefill | 189772 | 189772 | Exact |
| Q4_0 | Decode 1 | 23116 | 23116 | Exact |
| Q4_0 | Decode 2 | 23116 | 23116 | Exact |
| Total | Six calls | 472008 | 472008 | Exact |

The guest compares every 40-byte record, not a digest or histogram, and requires
all recorded returns to be successful. All 911616 paired logits remain bit-exact;
selected tokens and FCSR/VCSR match. All six graph records and 3894 node-group
records pass the original accounting checker. Disassembly confirms two bridge
callsites enter the wrapper; only the wrapper calls the underlying executor.

Independent replay checked the raw serial log, disassembly audit, receipt and
all 1019 sealed input hashes. The first preparation attempt remains FAIL: its
audit omitted GNU objdump's `jr` spelling for an indirect tail call, although
the calls were correctly wrapped. It never launched QEMU. The successor adds
tail-call recognition and a negative test that rejects bypass calls.

| File within the accepted run | SHA256 |
| --- | --- |
| `result.json` | `92f00270d28fce2df9ce63f3e0878f30f92e9c6b00b941af223e711d2afa0265` |
| `qemu.log` | `f83d5993ece75a858e83ded1552ec4a9c4ee9febd871825147f15a28233f9609` |
| `test` | `411a25bd9fc96c8e02e53139a5d07928e5072f4f670456c18a912e755f278cdd` |
| `source-pins.json` | `7d60cb540edf210a0b5299e1cd664258e2ea4d47ac2d90f63a6e7ee3e9818a1e` |

This closes software native-call shape/order equivalence for this paired test.
It does not turn QEMU timestamps into hardware cycles, establish hardware
retirement counts, or prove prepared-cache hit/fusion equality. Those narrower
remaining gates are not implied by the PASS above. No new performance gain or
production change is claimed.
