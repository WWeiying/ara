# Two-Thread Parent FCSR Diagnostic

Hypothesis: the frozen graph test compared the calling thread's local fflags
across two executions whose ordinary GGML Attention work was dynamically split
between OS threads. There is no threadpool fflags reduction. Thus parent UF/NX
can differ even with the same program, inputs and complete output bits.

Source proof in the unchanged external llama tree:

- ops.cpp:9158-9207: nr=12 heads; nth=2 gives chunk_size=2, nchunk=6,
  dr=2. Each worker starts at its ith chunk, then atomically claims later chunks.
- ggml-cpu.c:3578-3582 creates secondary OS threads; :3665-3668 runs worker0
  on the calling thread. :3369-3384 and :3674-3680 finish without collecting
  worker FP status into the caller. Barriers are not FP-status reductions.
- quant-kv.cpp:55 rejects nth!=1 before the grouped selection or direct task.
- Frozen ggml/test.cpp:228-234 resets/reads only the calling thread's CSR;
  :305-306 compares complete output bits, then incorrectly assumes identical
  caller FCSR for the separate two-thread executions.

This diagnostic includes only the failed run's fixture-source/test.cpp with its
main renamed. Its own main executes Q4 token-major prefix128, two threads,
16 times. Quant-KV stays disabled and grouped stays unset throughout. There is
no old/new or enabled/disabled alternation. Every call uses the frozen compute
API, preserving its finite-output, input, FRM, sticky-DZ and VCSR checks, and
compares all 1536 output words to call0 bitwise. The checker deliberately does
not equate newly raised fflags. It records all caller FCSR values and requires
no quant-KV dispatch records. Only observing both 9 and 11 supports the stated
specific hypothesis; a constant value is explicitly inconclusive, not PASS.

worker.py pins and verifies the original failed source-pins plus archived
fixture, failure/log/status, compiler, linked static libraries, native QEMU
model/build receipt, image/init/captures, and its own files before and after.
One new object and fresh ELF are linked against the original immutable graph
libraries. No GGML/SDK rebuild, source edits, retries, or model execution.
Compile/link/cpio/QEMU limits are 120/120/60/300 seconds. Preserve full logs.
Use a fresh verification/out directory and a directly owning systemd service.

No diagnostic result changes the original FAIL or weakens native/single-thread
exact CSR acceptance. A successor two-thread fallback contract should retain
full output equality, no dispatch, exact FRM/VCSR and preexisting sticky flags,
while treating newly raised caller fflags as local observations, not aggregate
or cross-scheduling equality. The diagnostic cannot observe secondary-thread
flags and must not claim that it does.
