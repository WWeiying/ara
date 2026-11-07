# 矩阵链路平衡候选：SoC 构建与 M4 交接验收

## 完整处理器构建

隔离候选已完成宿主机 VCS 编译，不是综合或门级仿真。配置保持 4 lane、
VLEN1024、实际 256 位物理存储及 16 MiB 容量，balanced 开关为 1。
以已验证的 physical256 快照为基础，473 个源文件中仅变换 VLSU 的候选实例
接入，另外新增八个候选模块；其余标量、普通 RVV、DPI 和验证源不变。

完整控制器、compute、seed 实际编译源及新 SoC 的七份候选计算模块逐文件一致，
第八份 engine clone 与完整控制器一致。原 131 条编译诊断的内容和数量全部
相同，没有通过忽略新增诊断来接受构建。独立审查核对 1070 个相关文件和全部
66 项可执行镜像文件；这不是对整个继承清单的重复重审。

| 构建证据 | SHA256 |
| --- | --- |
| `result.json` | `87efac7d98760d21bd6442a63ee61fe0737c56e631acf6d3a510d3644837257c` |
| `source-pins.json` | `ecc119ed8ba640ba3c59f652d702eb7b80e01db462760d3f0e2afde90a6e79c2` |
| `sim/simv` | `262b78f0463fef9192857d684142a173d9073d784149637d765a4bc9bc1082d5` |

原始目录位于唯一验证工作树的
`verification/out/e2e_balanced_soc256_20261106_01/`。

## 实际 M4 交接

在上述镜像运行 `LLAMA_BALANCED_SDK_RUN_PLAN_20261106.md` 中的固定 M4 ELF，
结果为 `BALANCED_SOC_M4_HANDOFF_RTL_PROTOCOL_PASS`。四条 QBS 命令都实际执行
M4/N3/K256，每条 useful pairs=3072、dot issue=32；不是用 M1 通过来替代 M4。

| 检查 | 结果 |
| --- | --- |
| QBS 数值 | 两次检查共 256 个字，四个不同激活行及零尾全部正确 |
| AKV 数值 | 四次行读取，共 256 个半字全部正确 |
| 普通 RVV | 三次 load/add/store，共 96 个字全部正确 |
| 联合交接 | QBS、QBS、十条 AKV、QBS、QBS，顺序匹配 |
| 架构状态 | 没有 trap；目标 Core SUCCESS |
| 协议 | 独立 UVM/CVXIF/backend/AXI 检查通过，完整镜像、ELF、日志和 trace 身份匹配 |
| 物理存储 | 实测 256 位；932 次读、932 次返回、550 次写，包含高半区写入与连续返回 |

物理存储计数包含整个测试，不是 QBS ROI 带宽。程序测试的是平坦物理地址，
不是 Linux 页表、PMP 或异常恢复；三次普通 RVV 检查也不是完整 ISA 回归。

原始目录：`verification/out/e2e_balanced_m4_handoff_20261106_01/`。

| 运行证据 | SHA256 |
| --- | --- |
| `result.json` | `083dfafe5fa2dd2f56768cdcb7ff6c5ba0d8a20c806ab7cddd9de5d685a6e877` |
| `source-pins.json` | `89607250d4d6bbb791c055230552b3a3b8d2261419aeec7804ae2eae7345637f` |

SDK 准入函数另行重读该原始日志并复算数值/工作量/顺序检查，核对协议及镜像
绑定，结果一致。它不能只凭一个旧 PASS 字段启动候选性能测试。

## 后续测量

至此只接受构建和交接功能，尚未接受模型加速。真实 QKV 候选、FFN 原版256和
FFN 候选256已安排独立后台测量；只有数值、工作量和独立协议均通过后才报告
配对周期。当前生产 RTL、原镜像和无关未提交文件保持不变，未进行综合、面积、
功耗或 FPGA 验收。
