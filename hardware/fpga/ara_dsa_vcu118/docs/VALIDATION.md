# 检查范围

## 2026-09-17 布线报告复核与约束修正

已复核 `d3aef3dd` 上传的 `impl_6abc9f1816a4`。这是完整 Windows Vivado 2020.1
综合和布线结果：MDRV-1、LUTLP-1 无违例；WNS +0.022 ns、WHS +0.010 ns、
WPWS +0.039 ns。但 Gray 指针首级、总线偏斜、UART/JTAG 输入及 VIO 状态的部分
预期例外未保留，不能仅凭正裕量认定 CDC 已通过。详情见 `FPGA_ISSUES.md`。

本次只改 FPGA 约束及验收脚本，不修改功能 RTL、主 RTL、ASIC/DC 或 IP 配置：

- 首级端点改为 `filter`/`get_pins` 对象查询，不再手工拼装用于约束的列表。
  这是针对报告中缺失模式的修正，仍需 Windows 验证保存和重载后生效。
- FIFO 数据例外只指向实际接收跨域数据的 A 级，不覆盖本域 B 级和 full 标志。
  指针/数据/偏斜仍为 3 ns，没有全时钟域屏蔽或放宽数字预算。
- 复位检查核对最终同步 FF、BUFG/BUFGCE 连接及常量使能，允许工具对主 SoC/UI
  高扇出复位插入的合法缓冲；仍拒绝 POR 缓冲、时钟选择器和错误/门控/反相连接。
- 新 `constraint_checks.rpt` 直接检查真实报告里的例外；普通 setup 即使数字恰好
  等于预算也不能代替 datapath-only。缺失的 CDC/端口例外在综合验收时即阻断后续。
  布线后还检查十组 Gray skew 和厂商 IP 的 skew，不能用 WNS/WHS 替代。

已通过 38 项实际报告/反例检查、29 项 CDC 查询场景、18 项边界场景，包含
厂商 skew 负裕量、缺首级、普通 setup 冒充例外、错误复位驱动和资源清理。
离线检查正确拒绝上传报告中的 75 个缺失约束检查项，未修改上传的原始报告。
这些测试包含工具查询替身和人工修改的内存样例，不是新的 Vivado 物理结果。
功能 RTL 未变，保留此前九组 FIFO 和 JTAG/复位的 VCS 证据，不重复仿真扫点。

全局流程另通过 10 项 PowerShell 连续流程、11 项单阶段流程、33 项 Tcl 运行流程
和 5 项多驱动检查测试。导出 27 项、同步 26 项、FIFO 补丁 6 项、包检查 12 项通过，
757 个包文件 SHA256 一致。全板静态展开无非厂商错误；Xilinx 原语、XPM 及三个 IP
仍需 Vivado 展开，未用假 IP 替代，也未把脚本替身测试当作原生综合。

运行方式不变：`scripts/run.ps1 -Stage all`，自动全板 synth 到 impl，无局部 probe。
本机无 Vivado；此次约束修正是否生效、恢复约束后的时序是否收敛，以新 Windows
报告为准。两条 CDC-11、CDC-15 数据通路及 TIMING-51 仍需结合新结果复核，未作豁免。

## 2026-09-16 单命令全局流程

`scripts/run.ps1 -Stage all` 直接运行全板新综合到布局布线和报告。
不运行局部 FIFO probe，不复用旧顶层综合网表，不重建或升级已有三个 IP。
这次仅修改流程、检查和文档；FIFO 独立 `word_q` 存储修复保持 `f529244d` 的版本，
不更新主 RTL、ASIC/DC、QBS/AKV 或时序约束。

已执行的本地检查：

- PowerShell 7.4.13：10 项全局流程及 11 项原单阶段流程通过。
  覆盖 synth/impl 失败、缺失/错误完成标记、阶段内/阶段间源码变化、锁冲突和残留进程。
  使用真正的 PowerShell 执行器，但 Vivado 和 Windows CIM 查询使用替身。
- Tcl：33 项运行流程通过；另外 5 项真实多驱动检查函数/综合 hook 测试通过。
  禁用 `try`，覆盖原 Windows 嵌入 Tcl 不支持该命令的情况。
  检查缺少 hook、综合/实现父网表/布线后多驱动及查询失败时拒绝接受结果。
- CDC 29 项、边界检查 12 项、时钟/IO 报告、组合环提取/资源清理及工程 Tcl 检查通过。
  均为脚本测试，不代表真实网表和布局布线通过。
- VCS 九组 FIFO 等价回归通过，包括实际 579/525 位 AXI 类型和常量字段。
  JTAG 74 次扫描、每个实现 45 次 DMI 接收、板级复位 50 项检查通过。
- 全板静态展开无非厂商模块错误，确认 CVA6、四 Lane Ara、QBS/AKV 和实际 FIFO 位宽。
  Xilinx 原语、XPM、DDR4、Clock Wizard 和 VIO 仍需 Vivado 展开，未使用假 IP 替代。
- 导出/同步/补丁回归、Windows 包文件与模板一致性、SHA256 完整性检查通过。

每个阶段启动前后检查同一输入指纹，两阶段之间继续持有排他锁。
综合失败不会进入实现；实现使用本次新通过检查的综合。
`completed_flow.json` 仅在两阶段通过脚本检查后写入，明确标记没有生成 bitstream。
多驱动诊断升级在实际综合 worker 的前置 hook 内设置，网表另有 MDRV-1 检查。

本机没有 Vivado，以上不证明 Windows Vivado 2020.1 综合崩溃已消失或物理时序已经收敛。
仍须执行一次 Windows 全局流程，复核 setup/hold/pulse、bus skew、DRC/CDC 和未约束路径；
脚本成功也不是完整的 CDC/上板验收，不自动生成或下载 bitstream。

## 2026-09-14 Windows Tcl 兼容修复

Windows `inspect_9f18a71a5829` 在调用 `open_run` 之前报
`invalid command name "try"`，未启动综合，也未重建三个 IP。
这是新增 Tcl 脚本的兼容性回归，不是 RTL 或此前的日志文件权限问题。
原离线测试的宿主 Tcl 支持 `try`，没有覆盖工具嵌入解释器缺少该命令的情况。

- 已将运行入口和两个报告函数共三处 `try/finally` 替换为
  `catch`、显式清理及 `return -options`，不修改 PowerShell 的异常处理。
  所用接口见 [Tcl 8.5 catch 文档](https://www.tcl-lang.org/man/tcl8.5/TclCmd/catch.htm)。
- 回归测试在加载脚本前禁用 `try`：旧代码复现失败，修复后 24 项运行流程通过。
  包括旧网表正常检查、源码更新后的检查、打开失败后清除兼容标志，并保留原错误信息。
- 环路报告测试在同样禁用 `try` 的环境通过。对两个函数分别注入提取失败、
  关闭失败及两者同时失败，6 种情况均验证文件关闭和原始错误传播。
- 本次仅改脚本、测试和文档，不改变 RTL、约束或 IP 配置；无需重建工程和 IP。

测试仍不是实际 Vivado 运行；修复后应在 Windows 更新代码并重新执行 `-Stage inspect`。
失败运行目录可保留，新执行会使用另一独立目录，不必删除旧综合或重置 run。

## 2026-09-14 回传报告复核与 VIO 修复

已读取提交 `98bbc6ea` 的 `inspect_a1c3e095ccee` 报告。这是旧综合网表加新约束：
双向 FIFO 路径的 max-delay 已生效，新增约束没有出现在 ignored exceptions 中。
QBS 八 LUT 组合环和 setup WNS -0.743 ns 仍在，不能进入实现或据此认定时序收敛。

DDR `fabric_ready` 直接进入 50 MHz VIO 的未同步路径已由实际时序报告和板级 RTL
共同确认。板级现为四个独立状态位增加两级同步，复位期间仍能采样；不改 QBS、
功能复位路径、VIO IP 配置或三个 IP 的产物。后续须重新综合验证这项 RTL 修改。

- VCS 使用板级源码中实际状态连线和导出包的 `sync.sv`，40 组变化通过，
  覆盖全 16 种状态、复位期间更新、异步边沿不直通和连续流水采样。
  只验证数字采样行为，不模拟亚稳态，也不证明 FPGA 放置/CDC 已通过。
- CDC Tcl 测试 12 种情况通过，含旧网表检查模式、缺少状态同步器及缺少第二级。
  正常模式检查 15 条 FIFO max-delay、两条复位例外、仅四个状态第一级 D 的例外。
- Tcl 运行流程 24 种情况通过；检查模式对旧网表的兼容只在 `open_run` 期间启用，
  即使打开失败也会清除，不泄漏到综合或实现。
- PowerShell 11 种流程情况通过；无 IP 重建、旧结果覆盖或源码指纹伪更新。
- 新增环路 fanin 测试覆盖侧输入 LUT、顺序单元边界、顶层端口、循环去重、
  2048 单元上限机制、显式截断和无环结果；继续保留实现前后组合环拦截。

Linux 当前没有 Vivado，未实际验证新状态同步器综合网表的命名和新 fanin 提取命令。
再次 `-Stage inspect` 可补充旧网表的环路连接；不需要重建 IP，也不会验证新 RTL。

## 2026-09-14 约束与诊断更新

Windows `synth_67f8334f3965` 已完成综合，但报告含组合环、CDC 约束错误和时序违例。
本次修改约束和运行脚本，不改变 RTL、IP 参数或三个 IP 的综合结果。
问题证据、资源分解和未完成项见 [FPGA_ISSUES.md](FPGA_ISSUES.md)。

- CDC 端点/时钟测试：正常配置，以及缺少同步级、数据端点、复位、时钟，
  多时钟、同域和过快时钟等 9 种情况通过；检查 15 条定向 max-delay，
  保留同步器第一级到第二级的普通时序。
- Tcl 运行流程：23 种情况通过，含检查旧综合时不启动 run、不重建 IP、
  不接受旧综合作为更新后 RTL 的结果，以及实现前和布线后组合环拦截。
- PowerShell：11 种情况通过，含新目录、排他锁、原指纹保留、输入更新识别、
  子进程失败及检查报告携带新旧指纹。
- 报告提取测试覆盖 LUT INIT、跨层次 net segments、驱动引脚、无环情况，
  以及诊断模式保留有环报告、实现模式拒绝有环结果。

以上均使用离线 Tcl/PowerShell 测试替身。当前 Linux 没有 Vivado，
未能打开 Windows DCP；实际网表端点匹配、约束生效、组合环根因及修复后时序
仍需在 Windows 执行 `scripts/run.ps1 -Stage inspect` 验证。
下面的 RTL/VCS 和旧导出检查是历史记录，不代表本次重新进行了 FPGA 综合。

## 已执行的检查

| 检查 | 内容 | 结论的边界 |
|---|---|---|
| 文件自包含 | HDL/头文件清单、路径存在性、重复定义选择、Linux 绝对路径检查 | 不依赖原目录和软链接 |
| Windows 路径 | 无软链接、无大小写冲突、无 Windows 保留文件名；Tcl 使用 package-relative 路径 | 建议解压到短英文路径 |
| RTL 静态展开 | pyslang 11.0.0，选择真实顶层、FPGA defines，检查 CVA6、4 Lane、QBS、AKV 层次 | 除下列 Xilinx IP 外，没有非厂商模块展开错误 |
| Tcl 检查 | Tcl 完整语法、创建工程流程的命令 mock、文件/IP 清单、约束命令解释 | mock 只检查 Tcl，不代表 Vivado 识别每个 IP 属性或物理引脚 |
| Boot smoke 编译 | 当前 RV64 GCC 编译链接，保存 ELF/map/反汇编；检查 load segment 和入口 | 未在 FPGA 上执行，不宣称硬件测试通过 |
| UART host 检查 | mock WRITE/READ/EXEC 协议、读回校验、错误 ACK 拒绝 | 检查 PC 端逻辑，不代替实际串口和 Boot ROM 联调 |
| 完整性 | SHA256 清单及校验脚本 | 可在 Windows 运行 `py scripts/verify_package.py` 检查迁移完整性 |

不提供假的厂商 RAM/DDR 模型。以下模块必须由 Vivado 提供，静态展开明确将它们列为外部边界：

- `xpm_memory_spram`：Vivado XPM memory。
- `BUFGMUX`、`IBUFDS`、`STARTUPE3`：Vivado UNISIM primitives。
- `clkwiz`、`ddr4`、`vio`：由 `scripts/create_ip.tcl` 生成。

静态检查使用与现有 EDA 工具接近的枚举转换及声明顺序兼容选项，并遵循 `translate_off`。
CVA6 中 `DATA_USER_EN=0` 的未启用分支仍含 user-byte 范围告警；静态检查对该范围告警单独降噪，不通过扩大 user 总线改变硬件。
剩余上游告警主要为未使用输出及小位宽/拼接。运行日志留在本机，不进入 Git 快照。

## 当前源码同步检查记录

主 RTL 内容仍与 Ara 提交 `2ac7103163ac5c99c350cddc7c339466b5a35d8d` 一致；
本次只修改 FPGA 集成及工具，实际导出来源提交以 `manifest.json` 为准。
`manifest.json` 记录各依赖的实际提交和本地修改；CVA6 原有的本地修改仍随包保留，
不是将依赖强制重置为干净提交。当前包包含 616 个编译输入、14 个 include 目录。

| 检查 | 本次实际结果 |
|---|---|
| 与工作区源码一致性 | 669 个来源文件的 SHA256 全部与工作区一致；仅执行已记录的 FPGA 集成补丁 |
| 新增 QBS SRAM 文件 | `qbs_payload_buffer.sv`、`qbs_payload_sram.sv` 均进入编译清单，顺序检查通过 |
| 新版 RTL 静态展开 | `cva6=1`、`ara=1`、`lane=4`、`qbs_engine=1`、`akv_engine=1`；无非厂商模块展开错误 |
| QBS payload 存储层次 | 2 个 `qbs_payload_buffer`、24 个 `qbs_payload_sram`；全部选择 FPGA `tc_sram`，未选择 TSMC 宏 |
| 导出补丁回归 | 13 项测试通过，覆盖 AKV 写法及字节统计兼容、计数更新/断言保留、Dispatcher 三行等价替换和异常源码拒绝 |
| Dispatcher 表达式等价性 | VCS 11 组 VLEN、238,175 组输入通过；同时比较新旧表达式及已知输入下的完整 unsigned 参考计算 |
| AKV 字节统计等价性 | VCS 337,681 组输入通过；穷举 16-bit read strobe、逐 lane 的 8-bit 四态 byte enable，并检查最大值 16/32 字节 |
| 增量同步回归 | 26 项测试通过，包括新默认路径、Git 元数据、冲突检测、旧文件备份、本地修改保留和失败回滚 |
| 文件/ELF/UART host 回归 | 9 项测试通过；串口仅使用 mock，不是板上执行 |
| Tcl 创建入口检查 | 源码清单及创建流程 mock 通过，不代表已经运行 Vivado |
| 包完整性 | 完整快照清单通过 SHA256 校验；清单含 Git 元数据，不含历史日志或 Vivado 产物 |

与旧包相比，编译清单增加了两个 QBS SRAM 相关文件。若已创建旧 Vivado 工程，
必须刷新源码清单，或保留旧 `build/` 后重新创建工程；不能直接沿用旧综合或 bitstream。
当前 RTL 已自行修正 AKV 归约表达式，导出工具会识别这一状态，不再要求重复替换。

这里的 `tc_sram` 使用 `tc_sram_xilinx.sv`，最终存储资源由 Vivado XPM 实现。
上述检查确认选择及连通层次，不证明 XPM/IP 原生展开、资源映射、综合时序或板上数值已经通过。
首次导出的原始日志和旧 ZIP 已归档到 Linux 导出工具的忽略缓存，不随 Git 传输。

### Vivado 创建入口修正

Windows 实际创建工程时，旧脚本的 `create_ip_run [get_ips {clkwiz vio ddr4}]`
触发 `Vivado 12-3445`。这不是 RTL 错误，而是 Tcl 命令的参数数量不符合限制。
[AMD UG835](https://docs.amd.com/r/2021.2-English/ug835-vivado-tcl-commands/create_ip_run)
明确要求每次只指定一个 IP；已改为对三个 IP 分别调用 `create_ip_run`，不修改 IP 配置。

原 mock 将该命令当作无条件成功，未捕获这个限制。现已增加对象集合展开、
单 IP 限制、输出生成顺序及三个综合任务完整性的检查；旧脚本会被该检查拒绝。
这项回归仍不是 Vivado，不能替代 Windows 上再次实际创建工程。
创建中断后，约束尚未添加完整；请按 `README_WINDOWS.md` 备份半成品并重新创建。

### Vivado 2020.1 Dispatcher 类型转换兼容

用户提供的 Windows 日志显示：DDR4 IP OOC 综合已完成，顶层综合在
`ara_dispatcher.sv` 原第 1610、1961、2210 行报 `Synth 8-2105 illegal cast operation`。
综合许可证已取得；不能将这次失败归因于 DDR4 或许可证。前面的
`Synth 8-1921` 是 elaboration system task 语法 warning，不是本次终止点，
但不能因此认定所有后续综合阶段都没有问题。

修正只作用于 FPGA 导出副本的三行：

- 正常 `vsetvl/vsetvli` 的 `vlen_t'(acc_req_i.rs1)` 改为
  `acc_req_i.rs1[$bits(csr_vl_d)-1:0]`。
- `vslideup.vx`、`vslideup.vi` 的 `vlen_t'(ara_req.stride)` 改为
  `ara_req.stride[$bits(csr_vl_q)-1:0]`。
- 原来的高位非零检查、比较符号 `>` / `>=` 及默认值全部保留。
  这里的 `vlen_t` 是 unsigned packed logic；窄化 cast 和相同宽度的低位切片
  都保留相同的 4-state 位。VLEN=1024 时为低 11 位，不是改为低 10 位。
- 没有统一删除其他 cast，没有改变流水级、控制状态、RVV 功能或 IP 参数。

`tests/check_dispatcher_casts.py` 从实际 Dispatcher 提取上述三个语句，
通过同一导出补丁生成新表达式，在 VCS 中直接并列计算并检查一致性。
测试使用 VLEN=64 至 65536 的 11 个 2 的幂配置，覆盖 SEW/LMUL 形成的 VLMAX，
零 VL、临界值、所有高位单比特溢出、32 个立即数、随机 64 位值以及 X/Z 输入。
总计 238,175 组输入通过。已知输入另与完整 64 位 unsigned 比较及饱和结果核对。
测试启动命令如下，输出目录必须是尚不存在的独立目录：

```bash
python3 -B hardware/fpga/vcu118/tests/check_dispatcher_casts.py /tmp/vcu118_dispatcher_cast_check
```

VCS 检查证明的是这些表达式的功能等价性，不是 Vivado 2020.1 原生综合验收。
本机仍无 Vivado。Windows 更新后应 reset 顶层 `synth_1` 再综合，
无需重建已成功的 DDR4 等 IP；下一阶段可能出现的兼容性或资源问题仍需实际日志确认。

### Vivado 2020.1 动态位计数兼容

下一轮用户日志显示 Dispatcher 的 cast 不再是终止点，但 AKV 原第 673 行的
`$countones(ldu_result_be_o[lane])` 触发 `Synth 8-280`，要求参数为常量。
同模块原第 1050/1053 行还有两处动态 `$countones(read_data_strb)`，也一并改写。

- Replay 每 lane 统计 8 个 byte enable，再累加到原有 7-bit `replay_word_bytes`。
- Read strobe 用固定循环上限 `AxiDataWidth/8` 计数。当前 128-bit AXI 下为
  16 个 strobe，结果使用 5 位，可表示 0 至 16，不会把全有效情况溢出为零。
- 循环内部用 `if (bit)` 增加计数，X/Z 不计入，与 `$countones` 的四态行为一致。
  没有直接把 X/Z 位加到计数器上而改变模拟语义。
- `q_external_bytes_o`、`kv_external_bytes_o` 和 `replay_bytes_o` 的更新条件不变；
  不修改 handshake、FSM、重放地址或返回数据，也没有新增流水寄存器。
- `ifndef SYNTHESIS` 内的断言保持原样。其他来源中检出的 `$countones`
  位于断言宏中，不属于这三处可综合字节计数。

`tests/check_akv_byte_counts.py` 从实际源码及导出副本提取组合计数表达式，
在 VCS 中检查 337,681 组输入，结果一致。运行命令：

```bash
python3 -B hardware/fpga/vcu118/tests/check_akv_byte_counts.py /tmp/vcu118_akv_count_check
```

这轮 Windows 报告还包含两个必须区分的问题：

1. Cheshire 第 623 行是 `genvar i < NumIntHarts`；`NumIntHarts=Cfg.NumCores`，
   板级常量配置明确设为 1。静态展开可得到一个 CVA6，故当前判断更像下层失败的
   连带诊断，但不能在没有 Vivado 重测的情况下保证它必然消失。本次不把参数强行写死。
2. DDR4 IP 出现 `Memdata 28-203/28-83`，涉及校准 MicroBlaze 的 BRAM 初始化映射。
   IP OOC 任务完成不能单独证明初始化正确；仍需完整 DDR4 日志确认，
   不能降级/屏蔽消息或手改生成的 IP 文件来当作修复完成。

用户报告本轮 RTL elaboration 耗时约 74 分钟、峰值内存约 30,290 MB；
它尚未进入成功的完整综合/实现验收。上述 VCS 等价性检查不替代 Vivado 原生综合。

## Git 管理与迁移检查

完整工程位于 `hardware/fpga/ara_dsa_vcu118/`，导出与同步工具位于
`hardware/fpga/vcu118/`。默认同步目标改为仓库内目录，不再生成 ZIP。

- `.gitattributes` 使用 `* -text` 保留快照原始字节，包括上游文件的原始换行。
  不能让 Windows 的 `core.autocrlf` 改写它们，否则会破坏校验及三方同步基线。
- `.gitignore` 排除 build/reports/output/缓存/备份；同时解除上层对
  `cheshire/`、`debug/` 等名字的全局忽略，防止遗漏需要分发的 RTL。
- 提交前按 `SHA256SUMS` 检查 Git 暂存清单完整性；检查从 Git index 检出的
  快照仍能完成校验，且无 symlink、超大文件或未跟踪的必需依赖。

旧的独立 Windows 工程仍可用 `scripts/sync.py --from-package` 接收 Git 目录中的新快照。
这些迁移检查不提供 Vivado 综合、时序或硬件数值验证结论。串口测试中的
`SMOKE PASS: mocked protocol only` 不是板上 PASS，Tcl mock 的 `Created:` 也不是真实 XPR。

## 本机尚未执行及上板待验项目

- Vivado 原生 RTL elaboration、IP 输出生成、synthesis。
- Vivado implementation、实际 clock/CDC/DRC 与 timing closure。
- 下载 FPGA、DDR calibration、UART 或 CPU JTAG 的实板联调。
- 普通 RVV、QBS/AKV arithmetic 的板上数值回归。
- OpenSBI/Linux/llama.cpp 端到端模型启动。

本机没有 Vivado，也没有连接 VCU118，不能将上表静态检查描述为上述步骤已经通过。
用户已在 Windows 完成工程创建和 DDR4 IP OOC 综合；顶层综合尚未通过，
当前报错和修正见上节，DDR4 初始化映射消息仍待核查。后续按 `README_WINDOWS.md` 顺序验收。
