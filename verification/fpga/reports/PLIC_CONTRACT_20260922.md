# PLIC 与 AXI 寄存器桥：单次诊断报告

## 结论

2026-09-22 的一次有界 VCS 子系统测试，在正确生成的58源槽/2上下文候选 PLIC
上确认三类独立功能问题。**初次功能验收为FAIL；后续隔离补丁已在相同TB下7组PASS。**
本次没有覆盖原 FPGA 导出、外部依赖或其它 worktree，也没有启动板卡构建。
下表保留初次诊断结果；修复与复验见文末，不用PASS覆盖原失败证据。

| 检查组 | 结果 | 说明 |
|---|---|---|
| physical_decode | PASS | 从0x04000000物理基址访问，未由 TB 预先减基址 |
| word_lanes | PASS | 高低32-bit word、64-bit访问、字节使能、响应背压 |
| reserved_holes | FAIL | 两个 context 的 IE[0] 均能写成1 |
| source_context_matrix | PASS | ID1/31/32/51/52/57分别通过 M/S 两个 context 的生命周期检查 |
| priority_threshold | PASS | 阈值通知、阈值不限制 claim、同优先级排序等所选场景 |
| competition_completion | FAIL | 未使能源57的 S context 仍能完成它 |
| read_side_effect | FAIL | 窄读 threshold 同时触发相邻 claim，消耗 pending |

总计370笔 AXI 事务、3223次检查、5282个采样周期，5条失败检查对应上述3类问题。
VCS编译28.58秒、运行10.84秒，共约39.42秒。编译仅有8条未实例化 interface 警告。
仿真进程退出码虽为0，日志中存在功能失败和 `$fatal`，运行器正确将最终结果判为
FAIL；不能仅凭进程退出码或 `simulation.status` 字段签收。

## 可复现证据

所有路径相对验证 worktree 根目录：

- 候选生成：`verification/out/plic-candidate-20260922/`。
- 配套检查：上述目录的 `static-check.json` 为 STATIC_PASS；旧配置的
  `legacy-static-check.json` 为 FAIL，该旧配置本轮没有另跑 RTL 仿真。
- 仿真归档：`verification/out/plic-contract-candidate-vcs-20260922/`。
- 完整事务和失败记录：`run/console.log`。
- 逐周期证据：`run/plic_signals.log`，5282行，采样相位为上升沿前 `#1step`。
- 输入与工具证据：`sources.json`、`compile_command.json`、`probe_plan.json`、
  `inputs/`、`build/command.json`、`run/command.json`、`summary.json`。
- 仿真后检查原输入与冻结副本，无文件漂移；探针连续性、握手次数、事务归属和
  日志尾部完整性均未报告错误。
- 独立复核直接重算逐周期握手：AW/W/B各208次、AR/R各162次，合计370笔。
  没有立即终止的 `PLIC_FAIL`，末尾 `completed=1`；最终 fatal 汇总的是已记录的
  五条功能失败。三个根因的周期链路均由独立审查者复核，而非只读取汇总状态。

TB使用实际导出的 `axi_to_reg_v2`、译码/解复用、错误从设备及候选 PLIC。
AXI为64-bit数据、48-bit地址、2-bit user，`CutMemReqs=1`；4-bit ID为TB局部配置。
没有 CPU、SoC crossbar/原子处理、UART、DDR 或实际板卡，不能称为 Linux 启动通过。

复现时必须换一个新输出目录，不覆盖这份失败证据：

```sh
env PYTHONPATH=verification python3 -B verification/run_plic_contract.py \
  --plic-dir verification/out/plic-candidate-20260922/rv_plic \
  --output verification/out/plic-contract-new
```

## 缺陷 PLIC-01：保留使能位不是硬零

[PLIC 1.0.0 的 Interrupt Enables 规定](https://github.com/riscv/riscv-plic-spec/blob/master/riscv-plic.adoc#interrupt-enables)，
不存在的中断源0对应使能位必须为0。测试对使能字写全1，再从真实 AXI 路径读回。

| Context | 事务 | 检查时刻 | 预期低32位 | 实际低32位 |
|---|---:|---:|---|---|
| M/context0 | 14 | 171 | 0xfffffffe | 0xffffffff |
| S/context1 | 22 | 256 | 0xfffffffe | 0xffffffff |

上述检查时刻在响应背压结束之后。对应写接受发生于周期143/228，读响应握手发生
于164/249；不能把检查器报告周期误当作寄存器状态被改变的周期。

生成 HJSON 为全部58个 IE 元素分配 RW 属性，reggen 因此为 bit0 生成了普通存储，
核心又逐位连接 `reg2hw.ie*.q`。将外部源0绑零只能避免 IRQ0，不能修复软件可见读回。
修复应从生成契约处理保留位，并保持所有非零源编号和0x80字节 context 间距不变；
不能只在仲裁器前屏蔽 IE[0] 而留下错误的寄存器读回。

## 缺陷 PLIC-02：completion 未检查该 context 的 enable

测试让 M/context0 使能源57并完成 claim，源输入保持高；S/context1 不使能源57，
但向其自己的 completion 寄存器写57。规范要求忽略这种 completion，并不要求
跟踪“上次由哪个 context claim”的所有权，因此不能误修成另一种所有权协议。
见 [Interrupt Completion](https://github.com/riscv/riscv-plic-spec/blob/master/riscv-plic.adoc#interrupt-completion)。

事务358的周期证据如下，数值只列源57对应的位：

| 周期 | 事件 | S IE57 | complete57 | IA57 | IP57 | M IRQ |
|---:|---|---:|---:|---:|---:|---:|
| 5087 | reg握手：0x04201004写57，complete_we=2 | 0 | 1 | 1 | 0 | 0 |
| 5088 | 错误completion释放gateway | 0 | 0 | 0 | 0 | 0 |
| 5089 | 持续高电平重新产生pending | 0 | 0 | 1 | 1 | 0 |
| 5090 | target通知再次置位 | 0 | 0 | 1 | 1 | 1 |

核心代码只检查 `complete_we[i]`，直接置 `complete[complete_id[i]]`，
没有对应 `ie[i][complete_id[i]]` 条件。修复应在消费 completion 时检查源编号合法且
该 context 使能该源，保留两个已使能 context 间合法 completion 的现有行为。

## 缺陷 PLIC-03：AXI 窄读访问了非目标寄存器

这是寄存器桥的读副作用错误，不是 PLIC 的 claim 语义错误。测试先令源1 pending，
只读取 context0 threshold，不读取 claim。事务369的实际链路：

| 周期 | 总线/内部事件 | IP1 | IA1 | IRQ |
|---:|---|---:|---:|---:|
| 5243 | AR握手，addr=0x04200000，size=2（4字节） | 1 | 1 | 1 |
| 5244 | reg握手读取0x04200000，claim_re=0 | 1 | 1 | 1 |
| 5245 | **额外**reg握手读取0x04200004，claim_re=1、claim_id=1 | 1 | 1 | 1 |
| 5246 | claim消费pending | 0 | 1 | 1 |
| 5247 | IRQ撤销，gateway仍等待completion | 0 | 1 | 0 |

`axi_to_detailed_mem` 将64-bit读请求发往两个32-bit bank；size相关掩码只约束
汇总的读错误响应，并未阻止非目标 bank 访问。`axi_to_reg_v2` 仅过滤零strobe写，
不抑制这种额外读。因而软件读回的threshold仍为正确的0，总线响应也是OKAY，
但一个未请求的claim已发生。只看最终读回数值会漏报此问题。

修复应让有效读范围与每笔请求一起跨越请求缓冲，阻止非目标 bank 到达 MMIO。
不能只屏蔽返回数据或错误码，也不能在存在缓冲时直接使用当前 ARADDR/ARSIZE
过滤较早事务。被抑制 bank 的握手/返回合并必须继续闭合，否则会引入等待不结束。
应保留合法64-bit访问、独立AW/W、写byte enable和背压行为，并检查其它有读副作用
的外设是否走同一个桥。本次仅实测PLIC，不声称已证明UART/FIFO故障。

## 隔离修复及原测试复验

修复位于两份可重现补丁，不在共享依赖或正式导出上手改生成文件：

- `verification/fpga/patches/plic-contract.patch`：仅改核心模板。对IE第一个word
  写入时清除bit0，存储和读回均保持0；completion检查合法非零源及该context的IE。
  不新增“必须由claim的context完成”的所有权限制。
- `verification/fpga/patches/mmio-read-range.patch`：`axi_to_detailed_mem`新增默认
  关闭的`EnableReadByteMask`，在寄存器桥实例开启。掩码从选中的请求metadata计算，
  随已有strb穿过bank FIFO和request cut；零掩码bank在桥内返回，不访问外设。
  MMIO模式的响应错误掩码来自相同访问范围。写路径及其它默认实例保持原行为。
- 没有新增流水级或队列。子字读取只保证不访问无关register bank，当前被访问的
  32-bit寄存器内部是否有逐字节副作用，仍由具体外设语义决定。

固定PLIC候选为 `verification/out/plic-fixed-candidate-20260922`，73份原始生成
输入不变；9份输出中仅`rv_plic.sv`变化。MMIO候选为
`verification/out/mmio-fixed-candidate-20260922-03/rtl`，原始导出文件不变。

复验归档 `verification/out/plic-contract-fixed-vcs-20260922`：

| 项目 | 初次诊断 | 隔离修复复验 |
|---|---:|---:|
| AXI事务 | 370 | 370 |
| 检查数 | 3223 | 3223 |
| 检查组通过数 | 4/7 | 7/7 |
| 失败检查 | 5 | 0 |
| 有界采样周期 | 5282 | 5121 |
| 编译/运行墙钟秒数 | 28.58/10.84 | 28.23/10.84 |

两次`plic_contract_tb.sv`字节相同。编译RTL仅三处改变：PLIC核心与两个桥接模块。
host运行器仅增加显式`--mmio-dir`覆盖件选择，未放宽测试预期。
固定编译镜像SHA-256为`d5a0c63c17107223c87854b0248a6e56f67147af754c1628f78b77585f6fcfce`，
周期日志SHA-256为`ef1c2005b81066ad015e5fc3f854356cff610c96b0336dace81a6c74154df4a0`。

修复后的关键周期：事务358在4928周期仍接受S context的completion寄存器写入，
但`complete[57]=0`，源57的IA保持1、IP保持0。事务369在5084周期只握手读取
threshold，未出现CC读，claim为0，源1的IP与IRQ保持1。两个context的IE[0]
均正确读回0。周期减少来自测试中多余register访问消失，不是模型性能加速数据。

独立复核已从原始探针重算5121个连续周期、AW/W/B各208次及AR/R各162次，
并核对冻结输入、日志与镜像哈希。事务358之后IA57一直保持到周期4944的显式
复位；事务369之后IP1与M IRQ一直保持到复位前周期5099。两轮370笔刺激和TB
相同，没有用缩短观察窗口或更改期望值使原失败检查通过。

后续桥接回归已完成：相同冻结TB分别运行原桥/修复桥，65个AR、74个R beat及
6笔写，覆盖全部偏移/size组合、连续请求、独立AW/W、反压与错误归属。原桥FAIL，
修复桥5组PASS，详见 [MMIO回归报告](MMIO_CONTRACT_20260922.md)。
下一步是完整SoC输入交接与VCU118/Linux；当前没有验证完整CPU外部中断送达或板卡启动。
