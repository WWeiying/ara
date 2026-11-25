# clk_i 违例复核和寄存器切点候选

参考：`verification/out/cast-fused-soc-dc-20261123-01`。候选：
`verification/out/clk-i-register-cuts-20261124-01`。均采用 1 GHz、TT
0.9 V/25 C、setup uncertainty 0.200 ns、hold uncertainty 0.075 ns。
候选沿用参考输入的文件和 DC 选项，只覆盖两份 Lane RTL，并在 VCS/DC
同时启用两个宏。不纳入其他工作树或当前未提交的无关修改。

## 路径归因

参考 `qor.rpt` 的 `clk_i` setup WNS/TNS 为 -0.136/-963.594 ns，
违例数 20,485。以下是 `clk_i_max.tim` 最差 1,000 条输出的归因，不是
全组违例计数。按每条路径的第一个匹配分类，不重复计算。

| 来源 | 路径数 | 最差 slack (ns) |
|---|---:|---:|
| CVA6 分支撤销经 Ara 应答回传 | 433 | -0.136 |
| 原生乘法 EW8 旁路至 VMFPU 结果队列 | 113 | -0.128 |
| QBS 共享乘法输入至 VMFPU 结果队列 | 109 | -0.128 |
| 标量 FMA 相关 | 127 | -0.126 |
| 标量 CONV 发出的路径 | 8 | -0.132 |
| VLSU 地址生成发出的路径 | 17 | -0.127 |
| 其他 | 193 | -0.131 |

最差寄存器路径：`fu_data_q.operation[7]` 经 branch unit 得到
`resolved_branch`（0.287 ns），经 controller 和 accelerator 请求
直通到 Ara（0.324 ns），Ara 应答回来（0.711 ns），最后走 CVA6
writeback/forwarding 与 issue 认可逻辑到 scoreboard 写端（0.942 ns）。
切点应放在已有授权请求的边界；只缩短 branch compare、关闭正常转发或
屏蔽撤销信号均不解决问题。路径要求 0.806 ns，差额是 0.136 ns。

## 候选内容

- `ARA_REGISTER_ACCELERATOR_REQUEST=1`：使用已有两槽寄存式输出缓冲。
  未授权的入队仍受原撤销信号门控；缓冲内只保留已授权请求。切断本次
  报告所见的 `flush_unissued -> 普通 acc_req -> Ara` 直通路径。不对
  preview、MMU 或其他旁路做时序豁免。
- `ARA_TIMING_SHARED_MUL_REGISTER_EW8=1`：停用 Lane 共享乘法器的 EW8
  零内部延迟旁路，使用现有乘法流水寄存器。QBS borrow 在注册乘法返回后
  直接执行下一拍的 pair reduction，删除候选配置中重复的本地乘积寄存器。
  QBS 仍经输入、乘积、规约三拍，原生 EW8 多一拍首结果。两宏均未切换主线
  默认值。DC 以实际生成时序报告为准，不按 RTL 推断宣称收敛。

## 验证和待确认

- 部件 VCS：实际共享乘法和 borrow 模块，7,773 次传输；逐拍 ownership、
  ready、result valid 和四组 pair 结果匹配，覆盖连续发射、空拍和所有权排空。
- SoC VCS：12 个短 ELF 全过，包括原生乘法、QBS、AKV 和交接。固定分支站点
  另检查正确路径确实写入、跳过的向量 store 不得写坏哨兵区。QBS 投影 checksum
  一致。短回归验收记录：`dc-short-gate.json`。
- AXPY `1543 -> 1665` 周期（+7.91%）；真实数据 QBS N32 投影
  `15634 -> 15889` 周期（+1.63%）。这是独立时序候选的代价，不能记为零。
- Resident QK/PV 的初始短超时记录原样保留；独立的 `resident-long/` 使用
  长超时和原数值/CSR oracle。除非该 worker 通过，不把两项计入 PASS。
- 首要验收是新 `clk_i_max.tim` 中上述跨模块/旁路端到端长路径不再出现，
  同口径比较 setup WNS、TNS、违例数和面积。如果标量 CONV 仍在顶端，实测
  该路径在 cast 出口为 0.736 ns、标量 FPU 出口为 0.823 ns、最终 0.934 ns；
  优先考虑只给标量 CONV 配置一个输出寄存级，避免全 FPU 无差别加拍。
  标量 FMA 内部路径和 VLSU/MMU/反压路径要单独归因。
- `clk_i` hold WNS -0.150 ns 独立于本轮 setup 优化。其最差样本是 I-cache
  refill 移位寄存器到 SRAM；不靠改功能 RTL、放松 uncertainty 或 false path
  处理。最终按真实时钟树和布线在 PNR 做 min-delay 复查、修复。
