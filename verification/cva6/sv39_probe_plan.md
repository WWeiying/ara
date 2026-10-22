# Sv39 实际 SoC 诊断捕获计划

## 本次问题与边界

此前 `linux_state_prereq` 验证 M-mode 中的 CSR 状态及浮点运算，
`vle32` 验证普通向量 load。两者都没有证明 S-mode 经非恒等页表访问数据，
也没有证明真实缺页后的向量指令重启。这里不预设 DUT 有错误，先建立可证伪的
期望：有效映射返回正确数据；跨页遇无效 PTE 时，异常和恢复必须符合程序约定。

实际配置为 `cv64a6_imafdcv_sv39_config_pkg`，`MmuPresent=1`、`RVS=1`、
WT data cache；`ara_soc` 设置 `OSSupport=1` 并将 `NrPMPEntries` 覆盖为 0。
`ara_system` 将 `irq_i/ipi_i/time_irq_i` 接零，没有完整 Linux 时钟中断平台。
测试仍是一个 baremetal ELF，不等价于 Linux boot、用户进程切换或 FPGA 签核。

测试、独立字面量预期及异常恢复协议见 [sv39_state_prereq.md](sv39_state_prereq.md)。
规范依据是 [Sv39 与 SFENCE.VMA](https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html)
和 [RVV 1.0 的 vstart 与精确异常](https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html)。
配置专用的预期与一般 ISA 要求分开，不能把本 DUT 的实现选择当成规范要求。

## 先静态重建的路径

1. `csr_regfile` 提供权限、SATP PPN/ASID、translation enable 与 SFENCE 控制。
2. `load_store_unit` 在标量 LSU 与 accelerator 之间切换共享 MMU。请求电平不是
   AXI 握手，translation-valid 也不是原指令退休。
3. `cva6_mmu` 查 TLB，必要时经 data-cache PTW 端口读取页表；返回 PA 或异常。
4. `addrgen` 将请求拆到页边界，保持剩余字节数，在缺页时计算元素级 `vstart`，
   通知 load/store unit 终止当前事务，再沿 dispatcher/ACC 返回异常。
5. `vlsu` 的 AXI 接口与 load-result 端口显示真实存储事务和 VRF 写回。
   异常响应、在途读写排空、重新接受原指令是不同事件，必须分别核对。

## 假设与判别矩阵

| 若出现的现象 / 候选解释 | 同一次捕获必须观察的证据 | 排除或支持条件 |
|---|---|---|
| VA 被当成 PA；未真正打开翻译 | CSR privilege/SATP，MMU `en_i/en_d/root/asid`，route 的输入 VA，addrgen PA 与 AXI 地址 | S-mode、非零 Sv39 root，非恒等 VA 对应独立的正确 PA；仅数据恰好相等不够 |
| 页表数据未可见或 PTW 解析不正确 | MMU PTW request/response、`data_req/gnt/rvalid/rdata`、TLB update payload、PTE 内容 | 从实际 ELF 的页表物理地址及 PTE 字面量追踪；区分页表构造错误、cache 可见性与硬件解析错误 |
| 标量/向量 MMU 路由丢请求或回错响应 | `mmu_route` 中 scalar/acc 输入、selected 请求、acc response；MMU 同周期请求/有效响应 | 对比 VA、store 位和时间序列，不能只用相同地址或电平猜测 owner；scalar_valid/ready 不等于翻译完成 |
| 页面拆分或剩余长度错误 | addrgen 当前/下一 burst VA、bytes、SEW、状态；AR/AW 地址、长度、size；队列 push/pop | 页末之前的数据请求合法且不越页，无效页不得生成成功内存事务 |
| 异常丢失、原因/地址/vstart 错误 | MMU ex、addrgen ack/ex/vstart_d/vstart、CSR trap-PC/cause/tval、软件保存快照 | 沿每个接口逐级对齐；vstart 是元素号，bytes 是字节数，不混用；当前态和下一态不混采 |
| 补页后仍复用旧 TLB 状态 | 修复 PTE 的 scalar 指令、SFENCE、PTW/TLB 更新、重新请求与 PA | 同一原指令 PC 重新执行，后续数据来自新有效映射；不允许异常 handler 直接跳过指令 |
| 重启丢失旧元素、重复写或地址偏移错误 | 重启 pe.vstart/VL、burst 地址、AXI R/W/BE、VRF req/gnt/data/BE 及 guard | 检查全部结果和边界哨兵，不只看最后一个元素或 tohost |
| 控制/退休路径未完成导致挂住 | ACC boundary/lifecycle、CSR commit/flush、MMU 和 addrgen 最后状态、协议 monitor | 给出最后一次确切进展、仍在途的事务和未满足的条件，不靠增加 watchdog 下结论 |

## 捕获契约

- 新增 [sv39_prereq_probe.sv](../uvm/sv39_prereq_probe.sv)，仅作为
  `verify_extra_sources` 编入独立诊断镜像，不进入正常 RTL 文件表，不 force 信号。
- 同镜像包含 ACC boundary、ACC lifecycle 和 CSR/FPU prerequisite probes。
  七个新增文件后缀是 `.mmu.log`、`.mmu_route.log`、`.addrgen.log`、`.vlsu.log`、
  `.ptw.log`、`.seq.log`、`.dispatcher.log`。共享 sink 合计九路，各自有完整性门禁。
- MMU 同时保存当拍输入和寄存后的 `req_q/va_q/pte_q`，返回值要按 RTL 的
  流水关系配对。PTW 保存当前/下一状态、页表层级、物理指针、cache 原始返回与
  寄存返回，避免把 cache 握手、PTE 解析和 TLB 更新当成同一拍事件。
- dispatcher/seq 保存异常、`vstart`、flush 状态、lane/mask 接受状态和在飞位图。
  sequencer 的 token 接受、PE 广播、各 PE 接受、异常返回和退休必须分开解释。
  未直接观察的 MMU 仲裁 owner 不由“地址相等”猜测，route 仅作为路由证据。
- 共享 sink 使用 posedge 前 `#1step`，同一 `cycle/epoch/edge_time_ns`；
  `q/d` 同相位表示当前态/下一态意图，不把 d 当成已经生效。
- 每路默认最多 8192 行，活动、活动后一拍和 reset 变化均占此预算。MMU 过滤 M-mode
  无翻译普通访存，保留 PTW、异常、SFENCE 和有效翻译；其余过滤条件见源码。
  Idle gap 计数保留。采集不是全信号波形，也不声称完整记录全部 scalar LSU 动作。
- ACC lifecycle 独立使用首次 ACC 起的 65536 连续周期窗口。它是额外的有界诊断，
  不能把该窗口当成全程序轨迹；必须核对目标故障/重启是否落在窗口内。整段运行的
  ACC 握手和提交证据分别由 boundary monitor 和 commit trace 保留，九路状态日志
  覆盖各自筛选的活动。若末尾输出越过 lifecycle 窗口，不因此重复运行已覆盖的故障。
- 所有 AXI 通道保存 valid/ready 与 payload。valid 本身不能计为 fire。
  PTW/IF/update 的 packed payload 须用冻结的 SV type 定义解析。
- 每路必须有唯一 END 且 `truncated=0,dropped=0`。无 END、达到截断或运行被终止，
  只能使用已观测的局部证据，不能宣称捕获完整；END 也不等于 DUT PASS。
- runner 的可重复 `--probe-kind` 参数强制所列日志通过完整性检查，记录
  `probe_capture.json` 及原始日志哈希；audit 重新读日志验证，不信任旧 JSON PASS。
  检查 header/END 唯一性、采样相位、row/cycle/epoch/gap、实际记录数、截断、
  活动计数及跨模块时钟边界。此门禁不替代目标事件覆盖或 ISA 数值 oracle。
- 固定 ELF、反汇编、RTL/依赖补丁与探针哈希。检查预期异常 PC、trap 保存恢复、
  页表布局、编译器没有插入额外向量指令后才运行。

## 追加仿真的条件

本次独立静态审查预先标出一个待测差异：CVA6 `decoder.sv` 默认将指令字放入
`ex.tval`，ECALL 分支改变 cause/valid 却未清 tval；当前 `TvalEn=1`、
`ZERO_TVAL=0`。若该值一路保留到 trap，测试 #68 将观测 `0x73` 而非零。
[Machine mtval 规则](https://docs.riscv.org/reference/isa/v20260120/priv/machine.html)
不为 ECALL 指定指令编码值；保持期望零，不用双值接受隐藏差异。
以上是首次仿真前冻结的假设，不能仅凭静态推导宣称复现；同一捕获的 CSR ex_tval
和软件 trap 快照是判定证据，无需另开一次“试试看”的仿真。现已完成该流程：
首次捕获实测只有 #68 失败，修复后原 ELF 及三点相邻回归通过，详见
[验证报告第 105 节](../RVV1_DIFFERENTIAL_VALIDATION.md#105-一次跨模块捕获定位-ecall-tval-错误)。

先离线回答上述矩阵的各项。只有缺少关键证据，或者已经形成可验证的修复，才启动
另一轮；清楚记录新一轮回答什么问题。必要时再用已知 PC/周期触发小 FSDB 窗口。
修复后复用原 ELF，并运行相邻普通 RVV/CSR 回归，不能用缩小输入替代修复。
