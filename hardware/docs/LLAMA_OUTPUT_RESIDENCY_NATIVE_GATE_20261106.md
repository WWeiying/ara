# 输出驻留：真实 QK 完整调用准备

## 固定比较范围

本轮不改变 QBS/AKV RTL，也不进行综合。比较双方为：

| 部分 | baseline | candidate |
| --- | --- | --- |
| Query 量化 | 生产 GGML Q8_0 | 同左 |
| Key 类型 | 分别 Q4_0 / Q8_0 | 同左 |
| QK | native QBS 指令 | 同左 |
| V 类型、物理布局 | Q8_0、token-major、8 个物理 KV head | 同左 |
| 输出更新 | 当前 Register-PV，每 token 写回 | Output-tile，tile 内驻留 |
| 准入、key panel、描述符、完成路径 | 原 runtime | 复用原 runtime |

真实捕获来自 Qwen3，query=19、GQA=2、D=128、可见历史 20。
测量包含准备、准入、QK、Softmax、PV、最终归一化及完成等待；打印在计时区间外。
ABBA 四次调用使用同一 ELF，检查 256 个输出的位级一致、相同 fcsr/vcsr、
相同命令和 key panel 工作量，并与模型捕获 golden 比较。

这是一个真实形状的完整 Attention 调用，不是完整模型，也没有跨 tile 或大 GQA
的性能代表性。先用它确定是否值得继续，再扩展可能收益和退化的形状。

## 已完成的构建

新构建工具：`verification/performance/end_to_end_baseline/build_output_native.py`。
它使用归档工具链和 GGML 配方，全部重新编译 18 个对象；当前未提交 llama.cpp
文件不会自动混入。除编译器 `-M` 依赖外，显式检查汇编 `.incbin` 引用的 5 个
实际输入文件，包含 query、key、value、mask 和 golden。

输出目录均在唯一验证工作树 `verification/out/` 下：

| 类型 | 目录 | ELF SHA256 |
| --- | --- | --- |
| Q4_0 K | `e2e_output_native_q4_20261106_04` | `d35e02102e10d7013aba501438837c31c757302d5d1d676de189fe21510c42a8` |
| Q8_0 K | `e2e_output_native_q8_20261106_02` | `4df16a1b7fc539378da5668c8d90c2e1ec213aa92a690cd7fe8ed9bbf33075b5` |

两组状态均为 `BUILT_NOT_EXECUTED`。反汇编确认两个 runtime 与 native executor
符号存在，没有链接 `qbs_ref_execute`。此时不能称为真实 QK 测试已通过。

两侧共同链接暴露了原 runtime 包含实现中的外部辅助符号重名；新候选仅将自身
的 unused grouped helper 改为独立名称，未改变计算或生产入口。
原始编译/链接失败记录保留，没有覆盖。

校验器和执行工具为 `check_output_native.py`、`run_output_native.py`。
校验器复用既有原始输出、golden、ABBA 和 CSR 检查，并额外要求准确的实验身份，
拒绝把旧 shared-V baseline 的日志拿来计为本轮结果。共 11 项工具单元测试通过。

## 为什么尚未运行 VCS 性能测试

旧 `canonical-shared-resources-build-20261025-02` 的预检失败，原因是当前验证
分支的 `hardware/src/vlsu/qbs/qbs_profile_engine_int.sv` 已不同于编译时归档。
其余归档清单文件未发现内容变化。当前该文件的最近提交为 `a38656a06`，涉及
final-dot retirement；不能跳过源码身份检查后把旧镜像称为当前 RTL。

失败预检：`e2e_output_native_q4_preflight_20261106_01/result.json`。
没有因此启动模拟器，没有改写原镜像、原清单或原失败结果。

采用现有严格构建流程生成当前验证分支的新独立镜像：

- 计划预检：`e2e_vcs_build_plan_20261106_01`，已通过。
- 新 VCS 构建目录：`e2e_vcs_build_20261106_01`，已完成，退出码 0。
- systemd 服务：`ara-e2e-output-vcs-build-20261106-01.service`。
- 工作进程直接由服务管理；构建阶段确认过实际 `vcs1` 执行。
- 4 lanes、VLEN1024、16 MiB 仿真内存、真实 CVA6、QBS/AKV-v2，保留 UVM、
  contract monitor 和断言失败保护；不采集 FSDB 或覆盖率。
- 该构建仅创建仿真镜像，不自动开始 benchmark，不进行面积/时序综合。

构建回执 SHA256 为
`32190b89a1dcf5ce0bb43a201a7b26ba23830fc753c9639837837d525a79c77c`。
新镜像严格准入通过，没有放宽旧源码漂移检查。

查看构建记录：

```sh
systemctl --user status ara-e2e-output-vcs-build-20261106-01.service --no-pager
tail -n 30 /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_vcs_build_20261106_01/sim/comp.vcs.log
```

## 下一步验收

已以新构建 `result.json` 的准确 SHA256 传给 runner 的
`--soc-build` / `--soc-sha256`，完成源码、依赖、镜像及配置身份校验。
两组完整调用在独立目录、独立服务中并行运行：

| 类型 | 运行目录 | systemd 服务 |
| --- | --- | --- |
| Q4_0 K | `e2e_output_q4_vcs_20261106_01` | `ara-e2e-output-q4-vcs-20261106-01.service` |
| Q8_0 K | `e2e_output_q8_vcs_20261106_01` | `ara-e2e-output-q8-vcs-20261106-01.service` |

启动检查时两个 worker 均为 RUNNING，`manifest-before` 和内存/ELF 合同检查均为
退出码 0。已核对两个实际 simv 进程及各自 ELF/日志路径，不仅检查服务状态文件。
此处记录的是启动，不代表测试已完成；最终以每组 `result.json` 为准。

运行结束后可使用 `collect_output_native.py --q4 <Q4运行目录> --q8 <Q8运行目录>
--output <新结果JSON>` 重新校验原始输出、golden、CSR、源文件及协议证据，并
按 ABBA 调用配对提取 QBS 活动。只有双方完整 PASS 才生成汇总。

活动分析额外要求每次调用恰有一个 QBS command，检查 M/N、量化输入字节数、
5120 个有效乘积对及命令阶段和。QBS engine 的阶段计数是互斥分类，并有 RTL
总和断言；它们可以描述 QBS 内部阶段。但 QBS busy 与整次软件调用的比例只作
诊断，不能与 RVV busy 等重叠事件相加作为完整 stall breakdown。

工具单元测试现为 15 项通过，新增拒绝重复/缺失 command、错误工作量、阶段和
不一致和未完成调用的检查。运行中的 worker 及其 sealed helper 未改动。

如果出现异常或 contract 错误，提前停止对应任务并保留证据；只有数值、活动、
协议检查全部通过，才报告周期和加速比。尚未获得新的性能数值，不用解析器的
合成日志或 QEMU 的经过时间代替。

整体目标仍是完整推理的性能面积收益。此软件候选用于判断数据流优化空间，
并不排除后续选择计算资源、缓冲与供给等硬件改进。
