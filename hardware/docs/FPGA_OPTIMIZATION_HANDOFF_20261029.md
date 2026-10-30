# 已验收 QBS/Attention 优化的 FPGA 交接

本文是交接入口。先按固定提交建立干净环境，再做 FPGA 同步和板测。
不要把当前工作区的其他修改、旧位流或未启用的软件当作交付版本。

## 一、两个仓库的版本

| 仓库 | 分支/标记 | 固定版本 |
|---|---|---|
| `WWeiying/ara` | `ara_dsa`；交付标记 `qbs-akv-validated-20261029` | 核心 RTL/SDK 合并提交 `5611f8577`；标记还包含本文 |
| `WWeiying/ara` | `ara_dsa_signoff_integration` | 原验收提交 `6872bb97c` |
| `WWeiying/llama.cpp` | `ara-qbs-akv-validated-20261029`；同名交付标记 `qbs-akv-validated-20261029` | `da56aa750559c180d631b466de983ff2bb5d54d9` |

llama.cpp 交付提交以 `8ed9403e37f1ceb43c6279cdefef01354eac6fd3` 为父提交，
保存模型测试实际消费的源码。814 份源码/配置逐文件核对交付 Git tree，
与验收快照一致；实际增量为 19 个文件。包括此前被忽略/未跟踪的后端头文件。
它是完整已测软件状态的检查点，不表示每个增量均由本轮新写。
本地额外的 `tests/test-ara-q4k-repack.cpp` 修改未纳入此提交。

原 llama.cpp 工作区的分支、索引与未提交差异没有改变。不要继续从原脏工作区
猜测交付状态；应使用新的分支或标记创建独立工作区。不要强制重置已有目录。

## 二、具体修改及不能改变的约束

| 保留优化 | 主要源码 | 行为与约束 |
|---|---|---|
| QBS final-dot retirement | `hardware/src/vlsu/qbs/qbs_profile_engine_int.sv` | 消除最后结果退休后的空等周期；仍保留 correction/result 排空中的上下文，不改变点积顺序 |
| M4 parallel sums | llama.cpp `arch/riscv/q8_K-m4-packed.h`、`q8_K-m4-group-sums.h` | 并行生成 Q8_K 整数组和；量化字节不变；producer tag 区分缓存来源 |
| Register-PV Decode | Ara `software/akv/experimental/quantized_kv/register_pv/` | V 解码和 PV 在寄存器中衔接；受格式、VLEN、舍入及形状条件限制 |
| Grouped quantized Prefill | Ara `software/akv/experimental/quantized_kv/prefill/` | 多 query 共享 K panel/V 解码；保留每行 causal prefix 和在线计算顺序 |
| 运行时接入 | llama.cpp `ggml/src/ggml-cpu/CMakeLists.txt`、`arch/riscv/quant-kv.cpp`、`akv.cpp`、`qbs.cpp`、`ggml-cpu/repack.cpp` | 构建与运行期开关、能力/布局检查、执行前 fallback、执行中错误传播 |

原有普通 RVV 和未满足条件时的路径不能删除。禁止把已开始且可能部分写出的
失败操作静默重跑为普通路径。新迁移同时包含此前验收分支的 QBS/AKV 共享
资源组织；不要只复制上表一个 RTL 文件而遗漏其依赖模块或 filelist。

cache hint、query guard、复制 V 缓存、直接读取 V 缓存均未获生产推广。
它们存在于验证实验目录，不是板上需要启用的优化。

## 三、构建与启用

请复用目标 Linux 的 GNU RISC-V 交叉编译器，不使用 ZCC。原模型功能测试的
工具链文件在本机 `/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake`，
编译器来自本机 cva6-sdk Buildroot。该绝对路径不是仓库内可移植依赖；
另一环境需要提供兼容 sysroot/ABI 的工具链文件。

已测构建启用 RVV、ZFH、ZVFH，并关闭未验证的 ZICBOP、ZIHINTPAUSE、
ZVFBFWMA；检查 FPGA 实际 ISA 配置，不要仅看编译通过。
核心 CMake 选项如下，SDK 路径必须显式指向此次 Ara 交付工作区：

```sh
-DGGML_RISCV_QBS=ON
-DGGML_RISCV_AKV=ON
-DGGML_RISCV_AKV_QUANT_KV=ON
-DGGML_RISCV_AKV_REGISTER_PV=ON
-DGGML_RISCV_AKV_QUANT_PREFILL=ON
-DGGML_RISCV_QBS_RUNTIME_DIR=/实际交付路径/software/qbs
-DGGML_RISCV_AKV_RUNTIME_DIR=/实际交付路径/software/akv
```

这不是完整 CMake 命令。原始完整配置记录位于验收 worktree 的
`verification/out/m4-sums-models-20261029-01/libraries/configure-on.command.json`；
其中构建静态库，未构建 CLI/server。板上应用目标、Linux ABI 和链接方式
需要由 FPGA 会话选择，不能把库测试记录说成新 CLI 已经板测通过。

功能启用至少涉及：

```sh
export GGML_RISCV_QBS=1
export GGML_RISCV_QBS_EMULATE=0
export GGML_RISCV_QBS_M4_PREPARE=1
export GGML_RISCV_QBS_M4_PACKED=1
export GGML_RISCV_QBS_M4_PARALLEL_SUMS=1
export GGML_RISCV_QBS_M4_CACHE=1
export GGML_RISCV_AKV_QUANT_KV=1
export GGML_RISCV_AKV_REGISTER_PV=1
export GGML_RISCV_AKV_QUANT_PREFILL=1
export GGML_RISCV_AKV_GROUPED_PV=0
```

上述开关仍受实际形状、类型、能力和内存条件控制，不代表每次都会命中快路径。
`GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=1` 是调用方对内存条件的承诺，
不能未经检查就在板上设置；需确认内存映射、权限、硬件可达性和缓存一致性。
原浮点 KV 的 AKV 分支与 quantized KV 分支不同，启用方式另见
`runtime_integration_current_20261029.md`。首先使用单 worker 复现已测范围，
不要把当前特定路径的单 worker 验收扩大为多核并发保证。

## 四、已有结果与 FPGA 后续责任

| 实验 | 已有结论 |
|---|---|
| 完整 Q/V/K 切片，已启用 QBS 的原版到本轮组合优化 | 582799.5 → 547856 cycles，1.063782× |
| 当前 RTL 上 Register-PV Decode | 47882.5 → 43072.5 cycles，1.111672× |
| Grouped Prefill Q4_0/Q8_0 K | 1.182042× / 1.207151×，历史验收 RTL 的四-query 配对结果 |
| 模型数值 | Qwen2.5-1.5B 与 Qwen3-1.7B Q4_K_M、两种 K-cache，1,823,232 个配对 logits 逐位一致；QEMU 功能证据 |

上述不是整模型 FPGA 加速比。完整范围和原始证据见
`optimization_round_final_20261029.md`。最后一项当前 RTL VCS 回归在验收
worktree 的 `verification/out/register-retirement-final-20261029-01/`。
大体积仿真结果/快照主要保存在本机，不随源码推送自动迁移。

下一会话应：

1. 从两个交付标记建立独立、干净工作区，核对实际提交号。
2. 核查 FPGA 的实际源清单和 RTL 导出机制，同步完整依赖而不是假定副本已更新。
3. 检查时钟、复位、存储实现、能力寄存器、VLEN 和接口配置，重新构建位流。
4. 先普通 RVV，再 QBS/AKV 定向与同任务规模模型切片，核对数值、异常和快路径调用。
5. 最后接真实 llama.cpp 端到端，记录位流/软件/模型版本及 prompt/decode 时间。

本轮没有重新综合、实现或烧写位流。既有板测不能证明新交付已在板上通过。
迁移前 Ara 本地尚有 9 份未提交修改，尤其 generic 双-head K/V 复用汇编，
不属于交付标记的已验收版本；这些改动已保留，不要混入本次板上基线。
