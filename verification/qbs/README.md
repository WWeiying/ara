# QBS reference and contract-verification environment

This directory contains the executable specification and focused RTL contract
checks for QBS architecture version 3 and descriptor version 2.

For formats not yet in the real-DUT paired campaign, capture a real decode
operator with `capture_real_format.py`. The capture uses host llama.cpp and
forces `-nr`: the current host capture callback can dereference an unavailable
tensor getter on the CPU repack path. It records model and executable hashes,
the exact command, and weight/F32-activation/F32-output tensor hashes. Recheck
the frozen result without rerunning the model:

```sh
python3 verification/qbs/capture_real_format.py --audit-existing \
  --output verification/out/qbs-format-closure-q2k-20260923-03
```

The same audit passes for the `q4-0`, `q5-0`, and `iq4-nl` capture directories
with that run suffix. These are input/golden captures, not RVV or QBS RTL
functional results. The host capture's `operator.json` always says
`activation_quantization=Q8_K`; this field is not the saved activation type.
The saved activation is F32 and QBS software must select Q8_K versus Q8_0
using the weight-format ABI.

- `qbs_ref.c`: descriptor validation, all nine implemented weight profiles,
  Q8_K/Q8_0 activation execution, layout conversion, numerical-contract
  ordering, trace events, and atomic result commit. R4 output-row groups are
  padded to four rows; the descriptor retains logical N and commit ignores
  padding.
- `qbs_ref_test.c`: constructed-vector tests for instruction/descriptor ABI,
  fixed-RNE behavior under a conflicting host rounding mode, profile decoding,
  quantization, layout equivalence, M/N tails, and failure behavior.
- `qbs_real_test.c`: tiled execution over the six captured Qwen2.5 workloads.
  It requires bit-identical outputs across supported layouts and compares the
  numerical-contract output with the captured llama.cpp golden result.
- `run_real_cases.sh`: fixed real-data regression manifest.
- `qbs_command_vectors.c` and `qbs_engine_tb.sv`: end-to-end command tests for
  every implemented profile and M1--M8 narrow/wide command geometry, including
  R4 `N=7/9` multi-block tails and four validation/MMU/AXI/PMA fault classes.
- `compare_adaptive_model_logs.py`: matched-log checker for the production
  GGML M4/M8 paths. It reconstructs ABI-derived weight-plus-activation payload
  bytes and rejects mismatched graph-node counts, M counters, command counts,
  or dot work. It does not treat those logical bytes as measured AXI traffic or
  cycle speedup.
- `qbs_activation_context_tb.sv`: focused DIRECT-independent context storage,
  metadata lookup, stale-generation rejection, incomplete-FILL protection,
  abort, replay backpressure, and RELEASE test. It deliberately writes Q8_K
  blocks with 12-, 8-, and 4-byte first chunks to exercise non-row-aligned
  compact storage.
- `qbs_context_sram_macro_model.sv`: behavioral model for the exact
  `64x256` TSMC macro interface used by the synthesis branch.
- `check_activation_context_evidence.py`: strict two-tile top-level log
  validator. It checks checksum equality, access modes, fault flags, AXI range
  roles and payload bytes, context counters, and cycle deltas together.

Run the fast constructed tests with:

```sh
make -C verification/qbs check
```

The profile-level VCS suite contains the original 432 cases plus 16 Q8_0
signed-extreme cases (physical M1--M4, row counts 1--4). Both operands are
`-128`: eight products total `+131072`, which requires a signed 19-bit dot
result. Alternating `-128/127` inputs alone do not exercise this overflow.
The suite checks decoded operands, integer groups/results, first and repeated
FP updates, fflags, and dot activity counters. Its PASS lines also report
first/repeated block latency for before/after comparisons.

The focused profile matrix can be audited from the original VCS log with
`python3 verification/qbs/audit_profile_matrix.py --log <run.log> --output
<audit.json>`. The 2026-09-22 run has 448/448 expected tuples, covering all
nine profiles across M=1..4, rows=1..4 and three input patterns, plus the
16 signed-extreme Q8_0 cases. Its auditable result is
`verification/out/qbs-profile-matrix-audit-20260923-01.json`. This is
profile-engine subsystem coverage, not real-model or full-DUT signoff.

From the repository root, use a separate build directory:

```sh
build_dir=$(mktemp -d)
make -C verification/qbs rtl-profile-check RTL_BUILD="$build_dir" RTL_RUN_TIMEOUT=180

# Optional: trace the first extreme case, without changing the DUT.
"$build_dir/simv" -no_save -l "$build_dir/trace.log" \
  +QBS_VECTOR_FILE="$PWD/verification/qbs/qbs_rtl_vectors.txt" \
  +QBS_DOT_TRACE_CASE=432
```

`QBS_DOT_TRACE` samples stream-zero operands at a rising edge and reports the
registered dot result after that edge, together with a signed 32-bit testbench
sum. The trace is disabled unless a case ID is supplied. Test success requires
the final PASS marker and no `Error:`/`Fatal:` lines, not just process exit zero.
The measured failure, fix, and unchanged command-cycle comparisons are recorded
in [the signed-extreme regression report](results/int8_extreme_20260908.md).

Run the ten real-data cases with:

```sh
make -C verification/qbs real-check
```

该目标检查六个原始切片、一个 M8 扩展切片及三个 Q3_K/Q5_K/Q8_0
decode 切片，共十点；运行前须由对应
`apps/llama_qwen25_*/script/gen_data.py` 从捕获张量生成 `generated/`。
若要固定输入目录，可设置 `QBS_REAL_DATA_ROOT`，其下应包含各
`llama_qwen25_<case>/generated/`。2026-09-22 的当前验证工作树以
`verification/out/qbs-real-20260922-01/inputs/apps/` 快照重跑七点，
`run-snapshot.log` 与直接读取生成目录的 `run.log` 一致，并记录了输入及
参考程序的 SHA-256。这是 QBS C 参考与捕获 golden 的数值检查，不是 RTL
或 AKV 签收。

新增的 Q3_K、Q5_K 切片取自 Qwen2.5-1.5B 的真实捕获数据，维度均为
`M=1,N=256,K=1536`；Q8_0 切片取自 Qwen2.5-0.5B，维度为
`M=1,N=256,K=896`。三点的 C 参考与 llama.cpp golden 均为 `0/256`
输出不匹配；最大绝对差依次为 `7.75e-7`、`9.83e-7`、`4.77e-7`。
每点还比较 row-major 与 R4 weight layout 的逐位一致性。Q8_0 使用
Q8_0 activation 和 32 元素块，不复用 Q8_K/256 元素量化路径。
上述 C 参考数值结果本身仍不是整机 RTL 证据。

Q3_K、Q5_K、Q8_0 的真实 DUT 单点分别封存在
`verification/out/qbs-q3-real-dut-20260923-01/`、
`verification/out/qbs-q5-real-dut-20260923-01/`、
`verification/out/qbs-q8-real-dut-20260923-01/`。三点的程序数值自检和
UVM 审计均通过；独立向量 trace 各记录 8 次 QBS 指令分配、写回与完成。
`verification/qbs/check_real_dut_evidence.py` 可读取原始运行目录及对应
`case.json`，重算数值 marker、命令次数、UVM 状态和文件哈希，并输出
`qbs_evidence.json`。该证据只适用于所测的三个 M1 decode 切片。

对应的标准 RVV 程序使用同一组捕获权重、激活及 golden 数据，在同一
QBS-enabled VCS 镜像上运行，但不发出 QBS 指令。首次 Q8_0 运行的
256 个输出数值自检无不匹配，独立 contract trace 却在 100000 行
上限被截断，故首次 UVM 审计保持 FAIL；Q3_K/Q5_K 首次运行均在原
900 秒 watchdog 下中断，尚无完整结果。三点另在独立的
`verification/out/qbs-rvv-q{3,5,8}-pair-20260923-02/` 目录重跑，
只提高该轮的 trace 上限和 watchdog。完成的运行须逐一检查 UVM、
数值、向量 trace 及输入哈希，再用 `compare_real_dut_pair.py` 生成
成对证据；不能把首次运行或进行中的日志解释为已通过的性能对比。
其中 Q8_0 的标准 RVV 对照已在
`verification/out/qbs-rvv-q8-pair-20260923-02/` 完成，程序数值自检与
真实 DUT UVM 均为 PASS，contract 与独立 UVM monitor 各核对 23414
个事件。`paired_evidence.json` 核对同一模型捕获输入、两侧结果哈希、
67 个 VCS 镜像组件及 RVV 路径无 QBS 指令分配，结果为 PASS：RVV
`173026` 周期，QBS `38782` 周期，该单点为 `4.46x`。RVV 计时窗口
内的阶段间控制开销为 44 周期，已单独列出。另在新编译的同一
真实 DUT UVM 镜像上，Q3_K/Q5_K 的标准 RVV 与 QBS 对照均完成
程序自检、UVM 审计和 `paired_evidence.json` 检查，记录于
`verification/out/qbs-rvv-q{3,5}-fire-pair-20260923-01/`。
Q3_K 的 RVV/QBS 为 `955389/33281` 周期（`28.71x`），Q5_K 为
`1493614/37143` 周期（`40.21x`）；两条标准 RVV 路径均无
custom-2 指令分配。这三个单点都不能代表端到端模型加速。

旧 QBS 输入清单记录的是运行时脚本的 SHA-256 `3c5d6e39...`；该脚本
的逐字节归档在 `verification/uvm/run_real_dut_case_legacy_20260923.sh`。
审计器仅当清单哈希与当前脚本或归档副本**精确匹配**时接受它，其他
输入及结果文件仍须按原清单逐一核验。新 RVV 运行对应可配置版脚本，
两版来源不应互相冒充。

AKV-v2 的独立标准 RVV 对照使用现有
`apps/llama_qwen25_small_attention` 算子，不借用联合 QBS+AKV 用例
中可能受先行 QBS 影响的 Attention 周期。两份 ELF 与生成的
`data.S` 已封存在
`verification/out/akv-attention-pair-inputs-20260923-01/`；同一
Qwen2.5 捕获点的 5 份张量路径和配置维度相同，配置只在实现标志
`RVV=1` 与 `AKV-v2=8` 上不同，5 份张量字节均在两个 ELF 中核实。
真实 DUT 运行分别位于 `verification/out/akv-attention-rvv-pair-20260923-01/`
和 `verification/out/akv-attention-akv_v2-pair-20260923-01/` 两个
独立目录。AKV-v2 单项现已结束，golden 自检与真实 DUT UVM 均为 PASS，
独立 Attention 计算窗口为 `41534` 周期。向量 trace 核实 v2 fill
2 次、K 列读取 256 次、复用旧式 AKV V 行读取 32 次、release 2 次，
没有其他 custom2 指令。该混合指令构成与
`software/akv/src/akv_v2_attention_rvv.S` 相符。标准 RVV 单项随后
完成，golden 自检和真实 DUT UVM 同样为 PASS，计算窗口为 `156845`
周期，且没有 custom2 指令分配。
`verification/out/akv-attention-pair-inputs-20260923-01/paired_evidence.json`
由 `compare_akv_real_dut_pair.py` 复核两侧 ELF 内嵌张量、UVM、
67 个 VCS 镜像组件、golden 自检和上述指令活动，结果为 PASS；
该真实单切片计算窗口的 RVV/AKV-v2 周期比为 `3.78x`。设备初始化
不在计时窗口内，不能将该点外推为完整模型加速比。
两侧冻结 ELF 还在同一较新 VCS 镜像上分别通过真实 DUT UVM，目录为
`verification/out/akv-attention-rvv-fire-pair-20260923-01/` 和
`verification/out/akv-attention-akv_v2-fire-pair-20260923-01/`；
`paired_evidence_fire_20260923.json` 再次审计为 PASS，周期仍为
`156845/41534`，标准 RVV 无 custom2 分配。
代表性配对结果可用 `audit_paired_campaign.py --manifest
verification/qbs/paired_campaign_20260923.json --output <report.json>`
重审。该检查现要求九种 QBS 格式和 AKV-v2 各自配对通过，且十对
来自同一完整 VCS 镜像。最新报告
`verification/out/paired-campaign-nine-formats-20260923-01.json` 为 PASS：
九格式加 AKV-v2 均通过、无缺失格式或证据错误，完整镜像组件身份一致。
原五格式报告仍存于 `verification/out/paired-campaign-20260923-04.json`。
这仅闭合
代表性捕获切片的配对门禁，不是所有 profile 或端到端模型签收。
新增的形状审计报告
`verification/out/paired-campaign-nine-formats-shapes-20260923-01.json`
重新核对同一批原始证据，九种格式均有一个有效真实数据配对点，但本清单的
多输入 `inputs>1` 为 0/9，非四行倍数的输出尾块也是 0/9。这里的“缺失”
只针对这份配对清单，不表示其他定向测试没有覆盖；因此九格式代表性 PASS
不能被解释为 Prefill 或 R4 行尾的完整 DUT 配对签收。
作为下一条真实数据多输入配对点，Qwen2.5 `Q4_K` Prefill
`K=1536,N=32,inputs=4` 的 RVV/QBS ELF 已构建，两侧源权重、F32 激活和
golden 哈希一致；
`verification/out/q4k-prefill-n32-pair-preflight-20260923-01.json`
记录了运行前的 `READY_NOT_RUN`。预检对未显式写在 `case.json` 中的捕获目录，从各自的
`provenance.json` 读取并逐侧比较，再核验真实 `model.json` 哈希。随后两侧
VCS/UVM 均通过，独立配对报告为
`verification/out/q4k-prefill-n32-pair-audit-20260923-01.json`，
计算窗口 RVV/QBS 为 `134077/114061` 周期（`1.175x`）。QBS 指令证据按
`inputs=4` 核对 `06b5045b` 的 alloc/write/done，而非单输入编码。
上面的 0/9 是旧九格式清单的覆盖率，不包含这个新增点。保留原清单不变后，
新清单 `paired_campaign_20260923_with_prefill.json` 的独立审计结果位于
`verification/out/paired-campaign-nine-formats-prefill-20260923-01.json`：
10 条 QBS/RVV 配对加 AKV/RVV 配对均 PASS，VCS 镜像身份一致；多输入
格式覆盖为 1/9（仅 `q4_K`），输出行尾覆盖仍为 0/9。该结果不代表全部
格式的 Prefill 或行尾已经闭合。
配对汇总脚本现在允许同一格式再提供带唯一 `variant` 的形状记录，保留
原格式键对应的 Decode 点，并分别核对每条记录的 VCS 镜像与数值证据；
只有已通过的 Prefill 运行才能加入新清单；报告中的
`campaign_shape_coverage` 按清单里的真实配对证据计算。

Q6_K 的独立整机配对已由
`verification/out/q6-paired-evidence-20260923-01.json` 重审为 PASS：
两侧 256 个输出均零 mismatch，QBS 侧 8 条命令分配与完成均被观察到，
标准 RVV 侧无 custom-2 分配；计算窗口 RVV/QBS 为
`1478066/40561` 周期（`36.44x`），不是模型端到端加速比。
两份测试 ELF 均从
同一 Qwen2.5-1.5B 捕获点生成，形状为 `M=1,N=256,K=1536`。
`preflight_real_pair.py` 在启动 VCS 前逐文件核对相同的原始权重、
激活、golden 和模型元数据，验证 QBS R4 排列、ELF 内嵌数据及
4 MiB/QBS-enabled 镜像配置。运行前预检文件
`verification/out/q6-pair-preflight-20260923-02.json` 为
`READY_NOT_RUN`，明确不代表 RTL 运行通过。可重放命令为：

```sh
verification/tools/soc-venv/bin/python verification/qbs/preflight_real_pair.py \
  --rvv-app apps/llama_qwen25_q6k_decode_attn_q_rvv \
  --qbs-app apps/llama_qwen25_q6k_decode_attn_q_qbs \
  --rvv-elf apps/bin/llama_qwen25_q6k_decode_attn_q_rvv \
  --qbs-elf apps/bin/llama_qwen25_q6k_decode_attn_q_qbs \
  --simv verification/out/real-ara-uvm-contract-fire-4m-20260923-01/sim/simv \
  --output verification/out/new-q6-preflight.json
```

预检不代替真实 DUT UVM、QBS 指令活动审计或同镜像 RVV/QBS 周期对照；
运行完成后仍需分别调用 `check_real_dut_evidence.py` 和
`compare_real_dut_pair.py`，且两侧程序必须使用同一冻结 `simv`。
本次标准 RVV 与 QBS 输出分别保存在
`verification/out/q6-rvv-real-pair-20260923-01/` 和
`verification/out/q6-qbs-real-pair-20260923-01/`；两路复用相同的
`simv`，各有 7200 秒独立墙钟上限。QBS 侧独立证据为
`verification/out/q6-qbs-real-pair-20260923-01/qbs_evidence.json`；
两侧均完成后仅运行下列离线检查，不重启 VCS：

```sh
python3 verification/qbs/compare_real_dut_pair.py \
  --qbs-run verification/out/q6-qbs-real-pair-20260923-01 \
  --rvv-run verification/out/q6-rvv-real-pair-20260923-01 \
  --qbs-app apps/llama_qwen25_q6k_decode_attn_q_qbs \
  --rvv-app apps/llama_qwen25_q6k_decode_attn_q_rvv \
  --output verification/out/q6-paired-evidence-20260923-01.json
```

同一验证工作树的真实数据 RTL 子系统回归位于
`verification/out/qbs-real-rtl-20260922-01-results/`。它从封存的
Qwen2.5 捕获张量构造 Q4_K 和 Q6_K 命令，各测试 M4/N32、M8/N16、
M7/N16，共六点；每点的 `qbs_engine_tb` 均报告完整功能 PASS，且
`SHA256SUMS` 对输入、生成器、仿真器和脚本复核通过。对应周期与传输量
在 `summary.csv`。这比 C 参考更接近 RTL，但仍只覆盖所测的 QBS
子系统命令，不证明 CVA6/Ara 整机、AKV 或 Linux 下的计算正确。
现行 `run_adaptive_real_rtl.sh` 在运行结束后另生成 `RUN_SHA256SUMS`，
封存六个命令向量、六份 VCS 日志、汇总 CSV 和原始输入/镜像清单。
`verification/out/qbs-real-rtl-sealed-20260923-01/` 的两份 SHA-256 清单
均复核通过；六点周期汇总与此前结果逐字节相同。真实数据只覆盖 Q4_K、
Q6_K 两种权重格式，不能把 profile-engine 的九格式构造测试解释成
九格式真实模型数据覆盖。

Before a long VCS run for the remaining formats, run the host-only quick
gate with a fresh output directory:

```sh
make -C verification host-quick-check \
  CAPTURED_QBS_OUT=out/qbs-captured-quick-check-new
```

It unit-tests capture/result parsing, reruns the existing ten real-data C
cases, re-audits four frozen llama.cpp captures (Q2_K, Q4_0, Q5_0, IQ4_NL),
and compares the C reference against their captured GGML outputs. All four
passed with zero mismatches in the 2026-09-23 run. This is a fast software
and input-integrity gate, not a standard-RVV/QBS real-DUT paired result.

The same four captures can be checked against the QBS engine RTL with full K
and an N=16 output slice, keeping each VCS case short:

```sh
python3 verification/qbs/run_real_format_rtl.py \
  --simv verification/out/qbs-real-rtl-20260922-01-engine/simv \
  --output verification/out/qbs-format-rtl-new
python3 verification/qbs/run_real_format_rtl.py \
  --audit-existing --output verification/out/qbs-format-rtl-new
```

The 2026-09-23 sealed run passed Q2_K, Q4_0, Q5_0, and IQ4_NL and its
independent audit. The runner records input and VCS-image hashes, regenerates
the command vectors during audit, and checks exact profile, K, and PASS lines.
This is an engine-level result, not a CVA6/Ara full-DUT or RVV/QBS pair.

Q4_0 has a separate real-DUT RVV/QBS pair on a captured Qwen2.5 decode
`attn_q` slice (K=1536, M=1, N=32). The shared-input preflight is
`verification/out/q4_0-pair-preflight-20260923-01.json`; both UVM audits
pass, both programs compare all 32 outputs with GGML, and
`verification/out/q4_0-paired-evidence-20260923-01.json` independently
accepts the same-image pair. Its measured compute cycles are 298871 (RVV)
and 17402 (QBS). Q5_0 now also has a same-image full-DUT pair on a captured
Qwen2.5 decode `attn_q` slice (K=896, M=1, N=32). Both UVM audits and all
32 output checks pass with checksum `0x969367732e152945`; the independent
`verification/out/q5_0-paired-evidence-20260923-01.json` audit passes with
152247 RVV and 10384 QBS compute cycles. IQ4_NL also has a captured Qwen2.5
decode `attn_q` pair (K=896, M=1, N=32), with 32/32 output checks and UVM
passing on both sides, identical checksum `0xa932dc518da44e1f`, and an
independent PASS audit at
`verification/out/iq4_nl-paired-evidence-20260923-01.json`. Its RVV/QBS
compute cycles are 349714/10314. Q2_K now has a full-K (4864), four-output
decode `ffn_down` pair at
`verification/out/q2k-4r-paired-evidence-20260923-01.json`: both UVM and
golden-tolerance checks pass, with 263516 RVV and 43010 QBS compute cycles.
Their output checksums differ, so this is numerical-tolerance agreement rather
than bitwise equality. An eight-output RVV diagnostic timed out at 600 seconds
and is not counted as passing. These single-slice results do not close all
shapes, exception paths, or model-level performance for any format.

After building the patched QEMU model, run the short ISA-contract regression
with `QBS_QEMU=/path/to/qemu-system-riscv64 make -C verification/qbs
qemu-contract-check`. It drives `frm=RUP` through an RNE/RUP-discriminating
input and checks that QBS still returns the fixed-RNE result. It also requires
load-access faults, before device reads, when the descriptor, activation, or
weight range points at the QEMU `virt` UART MMIO region. Legal payloads that
cross a 4-KiB page must succeed; payloads whose tail crosses from RAM into an
unmapped region must fault without changing the destination vector group.

Run the generic and SRAM-mapped activation-context checks with:

```sh
make -C verification/qbs rtl-context-check
make -C verification/qbs rtl-context-macro-check
make -C verification/qbs rtl-engine-check
```

The engine test executes FILL/REUSE/RELEASE through the normal range builder,
read engine, compute engines, and atomic commit path. Mismatched context ID,
generation, profile, layout, M, or K must fault before any payload access.

After the real Qwen2.5 two-tile top-level runs have populated
`hardware/qbs_activation_context_evidence`, validate the evidence with:

```sh
make -C verification/qbs activation-context-evidence-check
```

The expected pair is `decode_attn_q` DIRECT/DIRECT versus FILL/REUSE. A
passing result proves that the second command has no activation AXI range and
that both executions produce the same bit-level checksum; it does not infer
absence of reads from a single aggregate counter.

The real-DUT UVM pair in
`verification/out/qbs-context-real-dut-enabled-20260923-01/` uses the same
captured Qwen2.5-1.5B input and a VCS image compiled with `qbs=1, akv_v2=1`.
Both ELF checks pass with checksum `0x71b5ea8a1468eb92` and zero mismatches.
FILL/REUSE reduces two-command activation AXI reads from 3504 to 1752 bytes
and second-command cycles from 2371 to 2255. Both UVM audits are PASS and the
input/output SHA-256 manifests verify. Reproduce the pair with
`bash verification/qbs/run_real_context_pair.sh <qbs-enabled-simv> <new-dir>`;
the script rejects a QBS-disabled image before starting VCS. This is one
real-data QBS context case, not nine-profile or AKV model-level signoff.
