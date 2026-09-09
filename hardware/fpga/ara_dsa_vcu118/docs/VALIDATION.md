# 检查范围

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
