# 大偏移 slide 的真实场景重放

本项对应旧板测 RVV-08，不把此前三条重启卡死或通用 slide 矩阵的通过
当作本项已经解决。归档指出 e8/m4、e8/m8、e16/m8 在最后一个元素的
掩码使能出现反转，同时存在单例和连续调用两种证据。

## 测试来源与保留内容

源码来自 `ara_hw_campaign_20261007_01/rvv_verified_handoff03/` 下的
`rvv_small_slide04/`、`rvv_slide_sequence01/`，选取 seed0：

| 配置 | VL / offset | 单例 | 连续调用 |
| --- | --- | --- | --- |
| e8/m4 | 512 / 511 | all-on，1 次 | mask mode 0、1、2、3，4 次 |
| e8/m8 | 1024 / 1023 | all-on，1 次 | mask mode 0、1、2、3，4 次 |
| e16/m8 | 512 / 511 | all-on，1 次 | mask mode 0、1、2、3，4 次 |

`prepare_replay.py` 按各场景 `case.json` 逐项验证源码 SHA256，保存原始
`scenario.c`、`operations.S`、`operations.h` 和身份记录。原来的 RNG、
筛选循环、函数表、汇编、寄存器号、掩码、逐元素期望值及两端 guard
均保留。仅复用已核验的适配器替换 Linux entry/write/exit，因而这是
原始算术源码的裸机移植，不是原始 Linux ELF 在板上重跑。

另外核验六组 `original.elf` 与 `scenario.elf`，共 12 个归档 ELF 的
SHA256 均与各自 case 记录一致。移植后的新 ELF 自有哈希，不能与这些
归档 ELF 混为同一二进制。

六个 ELF 共包含 15 次目标调用；本组保留短序列内部的调用顺序，但
不代表已重放原始完整 permutation sweep 的所有前序操作或三个 seed。

## 参考与执行状态

`prepared01/reference02/results.json`：六项 Spike 均 exit 0，走到完整
源码 oracle 之后通过 HTIF 退出。共同运行时的 `SPIKE_REFERENCE` 分支
把日志写进 RAM，不向宿主 stdout 输出，所以不能要求终端出现 PASS。
最初 `reference/` 的 FAIL 是适配器误要求 stdout marker，进程实际 exit0；
已保留记录，没有覆盖、重编译或改动测试 ELF。RTL 仿真仍要求 UART
PASS marker、零失败记录及正常结束，不能仅看 simulator exit code。

当前重放使用 final03 的相同冻结整机镜像，不新增 RTL 构建：

- 服务：`ara-board-large-offset-final03`
- 并行度：3
- 每程序时限：300 秒
- 结果：`/home/wangwy/fpga_runs/current_board_integration_final03/large-offset/`
- 工作日志：同级 `large-offset-worker.log`

启动不等于通过。最终以 `summary.json` 和每条程序的 console、commit trace、
输入哈希为准。出现失败后先检查具体最后元素、mask mode 和掩码消费时刻，
不直接调整掩码指针或延长超时。

## final03 实测：仍有一个当前 RTL 反例

六项批次在首个失败后取消剩余任务，不能把取消项记为失败或通过：

| 程序 | 状态 | 实测内容 |
| --- | --- | --- |
| e8_m4_single | PASS | 512/511、全一掩码 |
| e8_m4_sequence | PASS | 相同尺寸、四种掩码连续调用 |
| e8_m8_single | FAIL | 1024/1023、全一掩码；元素1023应为185，实际91 |
| e8_m8_sequence | CANCELLED | 首错停止时正在执行 |
| e16_m8_single | CANCELLED | 首错停止时正在执行 |
| e16_m8_sequence | CANCELLED | 未启动 |

失败程序正常走到源码 oracle 和 `tohost=3`，不是 watchdog 超时。
`tests/e8_m8_single/console.log` 保留 `RVV_PERMUTE_DETAIL`；同一 ELF
的 Spike 参考通过。scalar commit trace 中目标是 PC `0x800006c6`、
opcode `0x388e4c57`，在103398ns提交；依赖其完成的 vstart 读取在
103701ns得到0。错误为目标末元素仍是初值91，而非无法返回。

这还不能只凭症状判断掩码反转。`capture_current.py` 复用完全相同的
final03镜像和程序，在103200至104000ns抓取显式信号列表，分别核对：
lane MaskM请求原点、MASKU读取的packed mask与输出、SLDU源数据/掩码、
输出位置与字节使能、各lane实际写回地址/数据/握手。没有重编译、插入
额外指令或更改期望值；`capture01/` 保留输入核验与波形证据。
诊断采集完成不等于功能通过，根因及修复需由这些信号另行证明。
