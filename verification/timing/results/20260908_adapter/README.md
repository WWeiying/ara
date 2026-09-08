# QBS 接收路径组合优化验证

- 基准：`7b7c3de0`，即上一批 QBS 状态压缩和 RVV ALU 改写之后。
- 本批唯一修改的硬件模块：`hardware/src/vlsu/qbs/qbs_block_adapter.sv`。
- 新旧 adapter 使用相同输入逐周期比较；另编译原 adapter 的 engine 程序，独立核对周期。
- 不增加寄存器状态、流水级或队列；不修改软件 ABI、profile、存储容量和 ready/fault 协议。
- 所有仿真使用宿主机 VCS。没有运行 DC、Innovus、Vivado 或功耗工具。

| 检查 | 结果 |
| --- | --- |
| adapter 布局/形状 | 81 组 PASS，九种 profile、M1..M8、row-major/R4、M4/M8 |
| strobe | 全部 65536 种 PASS，测试实际写入和独立 source-byte 计分板 |
| adapter 逐周期对比 | 157217 个测试周期 PASS，含 payload、byte-valid、完成位、计数 |
| QBS engine | 33 功能点及四类 fault PASS，周期全部不变 |
| activation context | FILL/REUSE/RELEASE PASS |
| 真实 Qwen2.5 数据 | 1 个 Decode 和 6 个 Prefill 切片 PASS，周期、phase、traffic 均不变 |
| SYNTHESIS 条件编译 | VCS 下 33 功能点和四类 fault PASS；不是综合结果 |
| 完整顶层切换 | RVV、4 条 QBS、10 条 AKV PASS，traps=0 |

## 文件含义

- `engine_cycles.csv`：33 点前后周期，profile 数字使用当前 `qbs_pkg.sv` 编码。
- `real_cycles.csv`：七个真实数据切片的周期与流量。周期仅属于 QBS engine 测试环境，
  不能拿来直接替换完整 SoC benchmark 的周期或模型 token/s。
- `adapter_cycles.csv`：首个 Q4_K/M1 定向点的 64 周期窗口，基准与当前逐字节相同。
  每行记录该周期有效输入和时钟沿后的状态。
- `summary.json`：源代码、捕获数据、激励文件、仿真程序和日志的 SHA256，以及各项结果。
  `simultaneous` 等字段是测试覆盖事件数，不是模型性能计数器。

窗口中的具体例子：cycle 3 后计数 W=7、A=5；cycle 4 补齐另一部分，计数变成
W=13、A=11；cycle 5 用全 strobe 重写相同位置，计数不再增加；cycle 6 无 valid，
状态保持。cycle 1 的 clear 和 valid 同拍，计数为 0。M8 两个 context bank 的行为
在完整 81 组测试中检查，不是通过这个 M1 窗口推断。

完整临时日志和程序目录：

```text
/tmp/ara_dsa_adapter_20260908_baseline/adapter/
/tmp/ara_dsa_adapter_20260908_exhaustive/adapter/
/tmp/ara_dsa_adapter_20260908_candidate/engine/
/tmp/ara_dsa_adapter_20260908_candidate/baseline_engine/
/tmp/ara_dsa_adapter_20260908_candidate/real/
/tmp/ara_dsa_adapter_20260908_candidate/baseline_real/
/tmp/ara_dsa_adapter_20260908_synthesis_define/
hardware/timing_adapter_handoff_20260908/
```

顶层于 2026-09-08 16:11:47 UTC 开始，16:13:13 UTC 完成。
临时目录可能被系统清理，以上小型记录纳入版本管理，不提交 VCS 二进制和构建缓存。

## 复现

从仓库根目录执行。使用新的 BUILD 路径，避免覆盖已有记录：

```sh
make -C verification/timing adapter-check adapter-engine-check \
  adapter-baseline-engine-check BUILD=/tmp/qbs_adapter_check RUN_TIMEOUT=300

QBS_ADAPTIVE_RTL_SIMV=/tmp/qbs_adapter_check/engine/simv \
QBS_ADAPTIVE_RTL_RESULT_DIR=/tmp/qbs_adapter_check/real \
  bash verification/qbs/run_adaptive_real_rtl.sh

QBS_ADAPTIVE_RTL_SIMV=/tmp/qbs_adapter_check/baseline_engine/simv \
QBS_ADAPTIVE_RTL_RESULT_DIR=/tmp/qbs_adapter_check/baseline_real \
  bash verification/qbs/run_adaptive_real_rtl.sh

diff -u /tmp/qbs_adapter_check/baseline_real/summary.csv \
  /tmp/qbs_adapter_check/real/summary.csv
```

Decode 使用独立捕获的激活，不是把 Prefill 第一列冒充为 Decode：

```sh
verification/qbs/qbs_command_vectors \
  /tmp/qbs_adapter_check/real/q4_decode_m1n32.vectors --real q4_K \
  "$HOME/llama/captures/qwen2.5-1.5b-q4_k_m/decode/operators/blk_0_attn_q_weight" \
  1536 1536 0 1 0 32

timeout 300 /tmp/qbs_adapter_check/engine/simv \
  -l /tmp/qbs_adapter_check/real/q4_decode_m1n32.log +QBS_FUNCTIONAL_ONLY \
  +QBS_COMMAND_VECTOR_FILE=/tmp/qbs_adapter_check/real/q4_decode_m1n32.vectors

timeout 300 /tmp/qbs_adapter_check/baseline_engine/simv \
  -l /tmp/qbs_adapter_check/baseline_real/q4_decode_m1n32.log +QBS_FUNCTIONAL_ONLY \
  +QBS_COMMAND_VECTOR_FILE=/tmp/qbs_adapter_check/real/q4_decode_m1n32.vectors
```

顶层切换和去除 synthesis-excluded RTL 检查的回归：

```sh
python3 verification/akv/run_current_handoff.py \
  --output "$PWD/hardware/timing_adapter_handoff_new"

make -C verification/qbs rtl-engine-check \
  RTL_ENGINE_BUILD=/tmp/qbs_adapter_check/synthesis_define RTL_RUN_TIMEOUT=300 \
  RTL_INCLUDES="+incdir+$PWD/hardware/deps/common_cells/include +incdir+$PWD/hardware/deps/axi/include +define+SYNTHESIS" \
  RTL_EXTRA_SOURCES="/tmp/qbs_adapter_check/qbs_block_adapter_reference.sv $PWD/verification/timing/qbs_adapter_equivalence.sv"
```

## 结论边界

这是一项组合逻辑重排的功能/周期验证，不是形式等价证明，也不是物理时序测量。
七个真实点保留完整 K，只截取 token 数和输出行，既不是完整模型运行，也不代表所有模型回归。
这些结果证明已测工作负载没有多花执行周期；没有证据宣称主频、面积或功耗改善多少。
timing worktree 旧报告中的 SRAM adapter 不能充当当前寄存器 adapter 的物理比较基准。
