# Linux bring-up

This is the Linux handoff for the existing passive UART boot path. It uses the
current VCU118 bitstream and places OpenSBI, the kernel, the device tree, and
an interactive BusyBox initramfs in DDR before executing OpenSBI. The DTB is
also embedded in OpenSBI so its platform initialization does not depend on the
initial register contents supplied by the passive UART `EXEC` call.

Changing the separately loaded DTB is insufficient: OpenSBI's embedded copy
is authoritative during this boot path. Rebuild `fw_jump.elf` whenever the
DTB changes (including ISA, UART interrupts, and initramfs length), and load
the matching pair. Confirm the effective ISA and UART IRQ in the kernel log.

## Build

The build host needs the RISC-V Buildroot SDK used for the kernel, OpenSBI,
and BusyBox, plus `dtc` and `cpio`:

```bash
cd hardware/fpga/ara_dsa_vcu118
bash linux/build_linux_bringup.sh
```

Override `SDK`, `KERNEL_IMAGE`, `OPENSBI_SRC`, or `OUT` when the SDK is stored
elsewhere. The script emits:

| File | DDR address |
| --- | ---: |
| `fw_jump.elf` | `0x80000000` |
| `ara_vcu118.dtb` | `0x80100000` |
| `Image` | `0x80200000` |
| `initramfs.cpio` | `0x88000000` |

The repository also includes the resulting first-boot payloads in
`linux/artifacts/`. This is the directory to use on a Windows board PC that
does not have the RISC-V toolchain.

## JTAG bring-up status (2026-09-25)

The `host_load.py linux` path wrote and read back all five OpenSBI/DTB/kernel/
initramfs ranges: 30,029,946 payload bytes in 172.28 seconds, including
readback. Evidence is in `D:/fpga_host_runs/linux_jtag_20260925_01`. OpenSBI
and Linux 6.19.6 reached the early console, but the initramfs success marker
never appeared. This is **not** a successful Linux boot.

Read-only JTAG snapshots in `D:/fpga_host_runs/linux_jtag_20260925_snapshot02`
show repeated illegal-instruction traps (cause 2) at
`0xffffffff80b93822`, with zero reported DDR response errors. The board bytes
at physical `0x80d93822` match the loaded `Image`. The `Image` matches the
SDK's `install64_qemu/Image`. The SDK build-directory `vmlinux` does not
match that installed Image, so the earlier `_etext`/non-code-padding
interpretation is invalid and must not be used as root-cause evidence.
The last console line comes from `unaligned_access_init()`; the next initcall
path probes misaligned access. A **software-only diagnostic hypothesis** is
to skip that probe with kernel boot arguments
`unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported` and
check whether boot advances. This has not been run and is not a proven cause:
the bad branch/return could still originate elsewhere, including hardware.
Do not change RTL based on the current evidence.

## Integrated J10 Ethernet attempt (2026-09-28)

The combined `host_ethernet` bitstream loaded an isolated Linux package over
J10 using `ethernet/ara_load.py --linux --port COM6`. Its DTB, embedded in
OpenSBI and also loaded at `0x80100000`, limits Linux RAM to
`0x80000000..0xFEFF0000` and uses the documented diagnostic boot arguments
`unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported`.
The kernel `Image` is byte-identical to the earlier JTAG attempt.

`D:/fpga_runs/ara_linux_run_20260928_01/report.json` records 30,030,014
payload bytes transferred and read back in 3.065 s (9.80 MB/s), 21,764
packets, zero retries, and a locked/isolated loader with balanced DDR
transactions and zero loader errors. OpenSBI and Linux 6.19.6 ran. The UART
log reached `Run /init as init process`, past the prior unaligned-access
failure, but did not emit the initramfs success marker within 150 s.
**This is not a successful Linux boot.** The output and two non-freezing JTAG
snapshots are in `D:/fpga_runs/ara_linux_run_20260928_01` and
`D:/fpga_runs/ara_linux_snapshot_20260928_{01,02}`. Across the two snapshots,
cycles advanced but retired instructions, last/head PC and trap count did not;
the debug `COMMAND/FLAGS` readback was `[0, 0]`, confirming counters were not
frozen. DDR response errors and outstanding transactions remained zero. The last trap
cause was 8 (user-mode ecall), not evidence by itself of a fatal trap.

The next investigation should distinguish a user-space instruction-fetch or
data-access stall from a console-only issue at the fixed head PC, using focused
signals or a minimal user-mode test. Do not attribute the result to the
unaligned probe or change RTL without cycle-level evidence. The board remains
in the locked post-launch state; a new load requires fresh bitstream
programming and firmware initialization.

### Follow-up diagnostics

With the UART interrupt properties removed from the test DTB, a minimal
assembly `/init` printed its complete markers. Its `nanosleep(1s)` test also
resumed after about one second, so basic user execution and timer wakeup work.
This DTB change is a UART polling workaround, not an IRQ fix. The standard
dynamic BusyBox, a static BusyBox, and a small static glibc C `/init` still
did not reach their first marker; no interactive shell was obtained.

`D:/fpga_runs/ara_linux_monitor_fast_run_20260928_01/uart.txt` shows a
no-libc monitor reaching `clone`, then immediately reading the test child's
`/proc/<pid>/syscall` as `running` and `wchan` as `0`. No later sample
appeared, even though the monitor's next loop contains only 1000 iterations.
Two subsequent non-freezing JTAG snapshots at
`D:/fpga_runs/ara_linux_monitor_fast_snapshot_20260928_{01,02}` show cycles
advancing from 6,665,594,785 to 8,277,744,360 while retired instructions
remain exactly 1,455,719,423. Both report last retired PC
`0xffffffff80b880d4`, head PC `0xffffffff80b880d8`, and last user ecall PC
`0x17dc2`. This is not an idle-loop PC. The child in this package is the
small static libc test installed as `/bin/busybox`, not actual BusyBox.
The last trap PC is historical, not proof that the syscall body is executing.

### QEMU comparison and minimal reproducer (2026-09-28)

The loaded Image SHA256 is
`716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285`.
Inspecting its actual bytes, rather than the mismatched SDK vmlinux, identifies
the head instruction as `vsetvli a5,zero,e8,m8,ta,ma` (word `0x0c3077d7`).
The surrounding sequence matches Linux `riscv_v_vstate_discard()` on user
ecall entry: enable VS, configure m8, overwrite v0/v8/v16/v24, set invalid
vtype, then disable VS.

QEMU uses this same Image and initramfs, but its own virt DTB and OpenSBI.
The original initramfs fails dynamic linking because `/lib64 -> lib` is
missing. The builder now supplies that symlink. The fixed package reaches
the shell and executes `uname -r` and `QEMU_SHELL_OK`, then powers off with
exit status zero. Evidence: `/tmp/ara_linux_qemu_lib64_fixed_20260928`.
This is a QEMU pass, not a board Linux pass.

`diagnostics/qemu_vstate.gdb` steps the discard sequence and records scalar
registers and vector CSRs. QEMU completes the m8 configuration with vl=1024,
vtype=0xc3, and completes the subsequent invalid-vtype configuration with
vl=0 and VILL set. Trace: `/tmp/ara_linux_qemu_vstate_gdb_20260928.log`.

`diagnostics/vector_ecall_init.S` removes libc: enable vector state, invoke
brk, then write two progress markers. QEMU observes all three markers
(its intentional final loop makes the diagnostic runner time out).
Board evidence in `D:/fpga_runs/ara_linux_vector_ecall_run_20260928_01`
shows only `ARA_VEC_ECALL_BEFORE`. The following snapshot in
`D:/fpga_runs/ara_linux_vector_ecall_snapshot_20260928_01` reports last
trap PC `0x10138`, the second ecall, and the same last/head kernel PCs above.
Thus the first ecall returned, but the second discard sequence did not
progress through its configuration instruction.

The falsifiable hardware hypothesis is that the prior discard leaves vector
completion/idle handling blocked; an alternative is a lost configuration
request across the scalar CSR flush/commit path. Distinguishing them requires
accelerator request/response handshakes, CVA6 flush and commit, Ara dispatcher
WAIT_IDLE/ara_idle, and sequencer running-operation bits. The existing board
snapshot does not expose those signals. No RTL fix or full instruction-by-
instruction FPGA/QEMU equivalence is claimed by these tests.

## Windows load

After programming the existing `.bit` and `.ltx` in Vivado, run from the
repository root on the board PC:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py `
  --port COM6 `
  --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf `
  --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image `
  --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb `
  --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio `
  --no-readback --chunk-size 4096 --seconds 120
```

For the regenerated fast-boot bitstream, use the CP2105 Enhanced COM port for
the payload and switch the host back to the Linux console rate after `EXEC`:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py `
  --port COM7 --baud 1562500 --console-baud 115200 `
  --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf `
  --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image `
  --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb `
  --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio `
  --no-readback --chunk-size 65536 --seconds 120
```

At 115200 baud, transferring the kernel takes a long time even with readback
disabled. Expected output includes an OpenSBI banner, Linux early console
messages through the SBI debug console, followed by the normal UART console,
and:

```text
Ara DSA VCU118 Linux init reached
Linux console, DDR and RVV handoff are alive
```

The initramfs then starts a BusyBox shell on `/dev/console`. With the fast-boot
bitstream, use `--interactive` so the loader keeps the same CP2105 Enhanced
COM port open and forwards keyboard input after switching to 115200:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py --port COM7 --baud 1562500 --console-baud 115200 --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio --no-readback --chunk-size 65536 --interactive
```

Press `Ctrl-C` on the host to disconnect the loader; the Linux process remains
running. This is an interactive bring-up rootfs, not persistent storage and
does not yet contain llama.cpp or GGUF weights. Those still need to be added to
the initramfs or loaded into DDR by a separate high-bandwidth path.

## Dual-DDR Linux memory configuration

The dual-DDR FPGA profile alone does not make the second bank available to
Linux. The original bring-up DTB describes only DDR1. OpenSBI built with
`FW_FDT_PATH` overrides the incoming FDT, so update both the external DTB and
the firmware's embedded copy.

`diagnostics/build_dual_linux.py` creates a separate bundle from a known-working
directory containing `Image`, `fw_jump.elf`, `ara_vcu118.dtb`, and
`initramfs.cpio`:

```bash
python3 hardware/fpga/ara_dsa_vcu118/linux/diagnostics/build_dual_linux.py --source /path/to/working-bundle --out /path/to/new-dual-bundle
```

It preserves the kernel and DDR1 range `[0x80000000, 0xfeff0000)`, adds DDR2
`[0x100000000, 0x180000000)`, appends `/ddr_pages` to the original initramfs,
updates its end address, and rebuilds matching OpenSBI. Unexpected original
memory layouts are rejected rather than silently replacing reservations.
The existing Ethernet loader still transfers boot payloads into DDR1 only.
Do not run destructive host DDR scratch tests while Linux owns these banks.

The board-specific `diagnostics/boot_dual_memory.ps1` verifies payload hashes,
programs the existing dual-DDR bitstream into SRAM (not Flash), initializes
Ethernet, boots Linux, then runs `verify_dual_linux.py`. Its paths refer to the
2026-10-06 Windows release and require a prepared output directory containing
`payloads`, working `tools`, `program_host_image.tcl`, and the verifier.

Measured on 2026-10-06, evidence directory
`D:\fpga_runs\ara_dual_linux_memory_20261006_01`:

- Linux init and shell reached; `MemTotal=3996732 kB`.
- `/proc/iomem` contains DDR1 System RAM and `100000000-17fffffff : System RAM`.
- 64 MiB pattern write/read verification passed. All 16,384 allocated 4 KiB
  pages were classified through `/proc/self/pagemap` as DDR2; none were outside
  the permitted RAM ranges. This user allocation did not sample DDR1 pages.
- Both DDR hardware observers recorded read/write activity during the test;
  both error counters remained zero.

This establishes dual-bank Linux operation, not full-capacity memory coverage,
throughput benchmarking, or a repeat of the 73-case regression suite. The old
single-bank DTB and firmware remain available for rollback.

### Qwen3 Bring-Up

The bundle builder also accepts `--llama /path/to/static-riscv-llama-simple`
and `--model /path/to/Qwen3.gguf` together. It adds `/llama-simple` and
`/qwen3.gguf` to the initramfs and records their SHA256 digests. The combined
initramfs must fit between `0x88000000` and the DDR1 loader limit. This avoids
serial transfer of the model and does not require a Linux Ethernet driver.

The current bring-up uses Qwen3-1.7B-Q4_K_M from
`hardware/scripts/akv/qwen3-model-manifest.json`, standard RVV (`rv64gcv`),
one CPU thread, and a static llama.cpp build with QBS/AKV disabled. This is a
functional baseline, not an accelerator performance claim. The original
kernel and dual-DDR FPGA bitstream are retained.

Prepare the same Windows directory as above, additionally copy
`diagnostics/run_qwen3.py`, and invoke `boot_dual_memory.ps1 -Out <directory>
-Qwen3`. The larger initramfs has a 900-second boot observation window. The
runner normally verifies the on-board model and binary hashes before invoking:

```sh
/llama-simple -m /qwen3.gguf -ngl 0 -t 1 -n 16 'The capital of France is'
```

`qwen3/uart.bin` retains the generated text, errors, and timing output;
`qwen3/report.json` records the exit code and decoded-token count. A host-side
observation timeout does not kill the guest process: inspect the live process
and console before retrying. Compilation, transfer, or Linux boot alone is not
a Qwen3 inference pass. Do not open another COM6 terminal while this runner is
active.

For software-only reruns on the already validated bitstream, use
`-SkipMemoryTest -SkipBoardHash` with the PowerShell wrapper to omit the extra
64 MiB memory test and the very slow guest SHA256 scan. Host bundle hashes and
the Ethernet loader's readback verification remain enabled. Do not describe
this mode as a guest-file SHA256 pass. The standalone runner also accepts
`--skip-board-hash`; use it only when the current payload transfer was verified.

### Indexed-Load Failure And Software Candidate

The initial Qwen3 run exited with signal 11 at `0x240976`, a `vluxei64.v`
inside `ggml_compute_forward_flash_attn_ext_f16_one_chunk`. It did not generate
a token. The table base was `0x531358`; the reported fault address was
`0x2537e434`, outside the FP16 conversion table.

`diagnostics/indexed_overlap.S` provides a small board test. Build with
`-DEXACT_WIDEN` to include the 16-bit load and widening sequence, and add
`-DFAULT_TABLE` to gather from newly mapped pages. On the current board:

- Resident-page control and overlapping-index cases passed 1,000 iterations.
- The widening sequence passed both cases.
- Newly mapped pages passed the non-overlap case; overlap faulted on its first
  iteration at the indexed load.
- Adding `-DPREFAULT` made both cases pass.

This isolates a fault/restart-sensitive overlap failure, but does not prove
the initiating event or complete RTL cause of the original Qwen3 failure.

The software candidate selects GGML's existing arithmetic FP16 conversion:
`-DGGML_CPU_FP16_TO_FP32=GGML_COMPUTE_FP16_TO_FP32`. Apply this to both C and
C++ compilation. The current cross-toolchain replaces `CMAKE_C_FLAGS` and
`CMAKE_CXX_FLAGS`, so add the define to `CMAKE_C_FLAGS_RELEASE` and
`CMAKE_CXX_FLAGS_RELEASE` alongside `-O3 -DNDEBUG`, and inspect generated flags.
Keep a separate build directory and retain the original executable.

`diagnostics/fp16_compute_check.c` passed all 65,536 FP16 encodings on the board
with that define: non-NaN outputs match an independent integer reference
bit-for-bit; NaNs are checked by classification. Disassembly of the rebuilt
Flash Attention function contains no indexed gathers. This is a software
workaround, not an RTL fix. End-to-end validation is recorded below.

### Qwen3 Board Result (2026-10-07)

The arithmetic-conversion build completed the command above on the dual-DDR
VCU118 Linux system at 50 MHz. Windows evidence is in
`D:\fpga_runs\ara_qwen3_compute_20261007_01\qwen3\{report.json,uart.bin}`.
The UART contains `QWEN3_DONE:0`, 16 decoded tokens, and the returned shell
prompt. Prompt plus generated text:

```text
The capital of France is Paris. The capital of the United States is Washington, D.C. The capital
```

This matches the captured native reference text (the native executable is a
different build; this is not a tensor-by-tensor numerical equivalence claim).
The binary SHA256 is
`7efcd126fdf88b628fe806bb4e539476b650b369eece3abe9ba7c2dd34aa643d`.
The model SHA256 is
`d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`.

Measured main generation loop: 1669.10 seconds for 16 generated tokens,
including prompt evaluation. The context reports 245.616 seconds for the
5-token prompt and 1420.599 seconds for 15 subsequent evaluation runs:
94.707 seconds per subsequent token (about 0.01056 tokens/s). The entire host
runner took 2268.17 seconds, including model setup and console handling but
excluding Ethernet transfer and Linux boot. This is a functional bring-up
pass, not a performance or general RTL correctness signoff. The indexed-load
fault/restart issue remains unresolved in hardware.

### Native QBS/AKV Follow-Up

`run_qwen3.py --qbs-akv` enables both native backends and their trace counters,
explicitly disables emulation and AKV portable mode, and retains ordinary
RVV fallback for unsupported operations. A successful inference alone does
not pass this test: the report also requires nonzero `native_qbexec` and
AKV `executed_ops` counters. The PowerShell wrapper exposes this as `-QbsAkv`.

The follow-up uses the same model, prompt, one thread, and 16 output tokens.
Its independent Windows evidence directory is
`D:\fpga_runs\ara_qwen3_qbs_akv_20261007_01`; completion and speed must be read
from its report, not inferred from the capability probe. Board capability
queries and an exhaustive 65536-code FP16-to-FP32 conversion check passed
before deployment. NaNs are checked by classification, other values bitwise.

This build enables Zfh/Zvfh as required by the AKV backend. Its native half
conversion supersedes the arithmetic-conversion macro used by the baseline,
so any combined speed difference cannot be attributed solely to QBS/AKV.
A controlled attribution needs the same executable with both backends off.

This run completed at 2026-10-07 02:27:17 +08:00 with exit zero, 16 decoded
tokens, and the returned shell prompt. QBS reported 281408 Q4_K and 98752
Q6_K native commands (380160 total), with zero emulated commands. AKV
reported 420 v2 decode operations and 3360 groups; 28 prefill operations
fell back for size. The main generation loop took 180.52 seconds, versus
1669.10 seconds for the earlier build (9.25x combined-build difference).
Decode evaluation took 152.74258 seconds for 15 runs, or 10.18284 seconds
per token. Host runner time including model preparation was 760.34 seconds.

After removing interleaved AKV trace records, prompt plus generated text was:

```text
The capital of France is Paris. The capital of Spain is Madrid. The capital of Italy is Rome.
```

This differs from the earlier baseline continuation. The runner's `passed`
flag certifies completion and native execution counters, NOT numerical
equivalence. A same-binary backend-off comparison and, if needed, focused
logit/operator comparisons remain necessary to attribute the text difference.
No claim that this difference is an RTL bug or harmless rounding is made.

### Same-Binary Backend-Off Control

The control completed on 2026-10-07 with the identical executable and model,
explicitly setting QBS, AKV, emulation, and AKV portable mode to zero. No
reprogramming or payload replacement occurred. Evidence is in
`D:\fpga_runs\ara_qwen3_qbs_akv_20261007_01\qwen3_same_binary_off`.
It returned exit zero, 16 decoded tokens, zero native QBS commands and zero
AKV executed operations. Its complete generated text matches the native
QBS/AKV run above after removing interleaved trace records.

The control main loop took 1560.83 seconds versus 180.52 seconds with both
backends enabled: 8.65x for this single short-prompt workload. Decode-only
evaluation was 1324.38247 versus 152.74258 seconds for 15 runs (8.67x).
This comparison keeps native half support identical. Trace logging was on
in both runs; it is not a repeated, trace-free performance characterization.

Thus the earlier different continuation is not reproduced by toggling
QBS/AKV in this binary. The older/newer build difference remains unisolated;
matching text here does not establish bitwise logits, all-shape numerical
equivalence, or a complete RTL correctness signoff.

### Context-Length Board Campaign (2026-10-07)

The same binary/model and 50 MHz dual-DDR image completed three additional
single-thread native QBS/AKV cases without reprogramming. Prompt counts below
are measured tokens, not characters or the allocated KV capacity.

| Case | Prompt tokens | Generated tokens | Prefill seconds | Decode seconds / runs | Decode tokens/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Arithmetic | 11 | 16 | 42.84062 | 152.73179 / 15 | 0.0982 |
| Repeated passage x4 | 130 | 8 | 457.31039 | 73.77228 / 7 | 0.0949 |
| Repeated passage x16 | 490 | 8 | 1876.08767 | 79.98889 / 7 | 0.0875 |

All returned `QWEN3_DONE:0`. Arithmetic continued `12 + 7 = 19` before
asking another question. Both passage cases correctly named wheat and rice;
generation then continued beyond the answer because the token budget, not
an answer delimiter, stops this raw-completion test. QBS native command
counts were 397632, 740448, and 2312928 respectively. AKV executed 420, 224,
and 224 operations; both passage cases covered native prefill as well as
decode. Their allocated KV capacities were 256 and 512 cells respectively.

Windows evidence under `D:\fpga_runs\ara_qwen3_qbs_akv_20261007_01`:
`arithmetic_recovered`, and
`context_campaign_utf8\{context_medium,context_long}`. The original arithmetic
collector in `context_campaign\arithmetic` failed on Windows GBK stdout
encoding, not guest inference. Observation resumed without sending guest
commands, and captured its completion. The runner now explicitly uses UTF-8.

`run_qwen3_contexts.py --root <existing-run>` runs the cases serially.
It records normal guest failures and continues, but stops on unknown guest
state or observation timeout. `--start-index` and `--output-name` allow an
explicit continuation into a fresh evidence directory. The runner supports
`--prompt`, `--prompt-repeat`, `--suffix`, and `--tokens`; repeated material
is assembled in the guest shell to avoid transmitting a long terminal line.

These are a small functional/length sweep with repeated synthetic passages
and real model inference, not a long-context quality benchmark, long soak,
or backend-off numerical comparison for the new shapes. The short-run
8.65x speedup must not be extrapolated to these longer prefill workloads.

### Answer Quality and Quiet Output

`diagnostics/run_qwen3.py` now defaults to a quiet console: run status,
answer, and a short speed summary. Use `--verbose` for raw UART output.
The complete `uart.bin` and `report.json` remain available in either mode.
`answer.txt` contains extracted generation; `final_answer.txt` excludes a
completed Qwen3 reasoning section. An unfinished reasoning section is not
displayed as a final answer. These files do not certify semantic correctness.

`--prompt-file` preserves trailing newlines, including those required by
the model's chat template. `diagnostics/prepare_qwen3_chat.py` renders the
actual GGUF template and runs a native reference with separate stdout and
stderr. Its `--thinking`, `--tokens`, and `--chat-only` options support a
bounded reference test before spending board time on a new configuration.

The meaningful cold-chain reading case (`reading96`) completed on the board
with 320 prompt tokens and 96 generated tokens, at 0.0904 decode tokens/s.
However, its raw-completion response contained placeholders rather than an
answer: execution passed, answer quality failed. A current-source native
reference using the model's non-thinking chat template produced sentences
but incorrect inventory arithmetic. Chat formatting alone has therefore
not established acceptable answer quality. No RTL fault is established by
these semantic failures, and no answers were inserted into the prompts.

Two further current-source native controls also failed this reading task:
thinking mode with a 1024-token budget, and non-thinking mode with explicit
step-by-step constraints and a 256-token budget. Both completed, but their
final answers contained arithmetic and vehicle-capacity errors. Evidence
directories under `/home/wangwy/fpga_runs/qwen3_20261006` are
`chat_reference_current`, `chat_reference_thinking`, and
`chat_reference_structured`. These controls use the same model and greedy
`llama-simple` sampler; they do not isolate model limitations, quantization,
sampling, or runtime numerical correctness. No new board run was launched
with these known-failing quality configurations.

#### Similar-Size Host Model Controls

The same reading and default system message were also run on x86 CPU with
Qwen2.5-1.5B-Instruct, using its own GGUF chat template and current-source
`llama-simple`, with a 384-token ceiling. Both completed normally:

- Q4_K_M: usable inventory 360 and Harbor demand 80 were correct, but the
  remaining stock was incorrectly reported as 60 and 10:30 was described
  as later than noon. Evidence: `quality_qwen25_15b_q4`.
- Q6_K: usable inventory and per-clinic demands were correct; remaining
  stock was replaced by the minimum reserve of 20. The final explanation
  incorrectly claimed insufficient truck capacity and added an infeasible
  extra Cedar shipment to the van. Evidence: `quality_qwen25_15b_q6`.

A freshly built, statically linked `llama-completion` also ran the original
Qwen3-1.7B Q4_K_M with the same rendered non-thinking prompt. Sampling was
temperature 0.7, top-p 0.8, top-k 20, min-p 0, seed 42, context 4096, and
384 maximum generated tokens. It still answered inventory 40, demand 380,
and remaining stock -340, all incorrect. Evidence: `quality_qwen3_sample42`.
These directories are under `/home/wangwy/fpga_runs/qwen3_20261006`.

This is a single-question quality comparison, not a model benchmark. It
establishes failures without FPGA execution, not a proof that model weights
alone are at fault or that the shared llama.cpp runtime is numerically
correct. The old mixed shared-library build failed its help command and
was excluded from inference; the new isolated build was used instead.

### Continuous Windows Chat Window

`diagnostics/chat_qwen3.py` wraps the verified single-turn runner in a
continuous input loop. Deploy it and `chat_qwen3.cmd` beside the updated
`run_qwen3_chat.py` in the existing Windows payload directory, then run:

```powershell
& 'D:\fpga_runs\ara_qwen3_qbs_akv_20261007_01\chat_qwen3.cmd'
```

Enter a question at `You>`. After completion the answer appears and the
window accepts another question. `/reset` starts a new conversation and
`/exit` quits. Messages are retained in subsequent prompts and logged per
turn; the model and KV cache are NOT resident across turns. Each question
still reloads the model and reevaluates the conversation. This is not a
low-latency chat server, and answer quality remains unvalidated.

The default output budget is 128 tokens; `chat_qwen3.py --tokens 256` changes
it. The wrapper refuses prompts exceeding 8192 UTF-8 bytes rather than
silently dropping history. A generation failure stops the session without
automatic retry or interruption of the guest. Close other COM6 clients
before use. This entry assumes the existing verified board image/model;
it does not reprogram or boot the board. Windows startup/exit and host
mocked history/reset/failure tests passed; a new board multi-turn inference
campaign was not performed as part of deploying this interface.
