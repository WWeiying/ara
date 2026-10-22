# Linux 高虚拟地址截断：根因与修复

## 已复现的故障

Linux 在恢复向量上下文时执行 `0x02070007` 向量加载。
基址寄存器为 `0xffffffd680846000`，但送入 MMU 的地址变成
`0x0000ffd680846000`，产生 load page fault，cause 为 13。

原始板测及对照实验记录位于主工作树：
`hardware/fpga/vcu118/results/20261017_linux_virtual_address_rootcause/result.json`。
实际 AddrGen/MMU 的四组实验保存在：
`/home/wangwy/fpga_runs/ara_linux_canonical_rootcause_20261017/recorded_repro/`。
这些是原始故障证据，不被修复后的结果替换。

| MMU | AXI 地址宽度 | 虚拟地址 | 原始结果 |
|---|---:|---|---|
| 当前已修正合法性检查 | 48 | 内核高地址 | 复现 cause=13，无 AXI 读取 |
| 当前已修正合法性检查 | 64 | 同一高地址 | 发出读取 |
| 当前已修正合法性检查 | 48 | 低地址 | 发出读取 |
| 旧的实时输入检查 | 48 | 同一高地址 | 漏检截断形成的非法地址 |

旧 MMU 在响应周期查看实时请求，而不是已保存的翻译请求，因此此前的
错误检查掩盖了截断。恢复旧 MMU 不能修复地址通路。

## 类型边界

`CVA6Cfg.VLEN` 是本配置的架构虚拟地址宽度，不是向量寄存器位数参数
`VLEN=1024`；两者不能混淆。本配置的架构地址为 64 位，而 FPGA AXI
地址为 48 位。

原 AddrGen 用 `axi_addr_t` 保存翻译前的地址，导致先截断、再零扩展。
对已经丢失高位的地址补符号位不可靠：必须将完整原始地址交给 MMU，
才能区分合法内核地址和应被拒绝的非规范地址。

## 当前修复

在 `hardware/src/vlsu/addrgen.sv` 中引入
`vaddr_t = logic [CVA6Cfg.VLEN-1:0]`，用于：

- 内部请求记录的地址字段。
- unit-stride 与 strided 的起始地址和 lookahead 寄存器。
- stride 加法的下一地址暂存。
- indexed 基址加索引的结果，以及对应 spill register。
- burst 起止位置、下一 burst 起点、跨页高位和 split-carry 运算。
- 由这些地址构造的 MMU 输入、异常 `tval` 和下游 `vaddr` 元数据。

保持不变的部分包括：MMU 合法性检查、物理 AXI 通道宽度、请求握手、
队列深度、状态机和流水级数。只有翻译后的物理地址进入 AXI 字段；
关闭翻译时仍使用既有物理访问路径。

`addrgen_axi_req_t` 的 `addr/vaddr` 原本是
`axi_pkg::largest_addr_t`，当前库中为 128 位，并不是 48 位；
store B-response 元数据也使用该宽类型，因此无需修改这些接口。
QBS/AKV 共享读引擎已区分 `vaddr_t` 与 `axi_addr_t`，未发现同类翻译前截断。

## 验证要求与边界

针对性测试必须检查真实 RTL 的 MMU 请求地址、翻译结果、AXI 地址、
异常原因和完整 `tval`，而不只检查仿真结束标志。低地址对照应比较
修复前后的请求周期；测试还需覆盖跨页、负 stride、indexed 暂存和
非零 `vstart`，防止只修复最初的单次加载。

`verification/tests/test_addrgen_virtual_address_width.py` 检查类型边界和
跨页运算中的宽度约定。这是静态回归检查，不能替代真实 RTL 仿真。
原有 `verification/timing/generate_closure_checks.py` 的独立算术测试
保留旧参数名，用本地虚拟地址类型别名兼容新的 `set_end_addr` 函数。

本次修改后的完整 SoC 和 FPGA Linux 启动尚需单独验证；修复前的
798 项 PASS 和覆盖率对应旧镜像，不能作为新 RTL 已完成全回归的证据。
FPGA 导出 RTL 也不会因修改主源码而自动更新，后续必须重新导出并核对构建清单。

## 本次实际验证结果

宿主机 VCS 使用当前源码中的 AddrGen 与 MMU，分别编译修复前的
`5ee02215` AddrGen 和修复后 AddrGen。两侧各完成 10 个场景，约 79 秒。
修复前场景按预期复现错误行为，不表示旧实现符合架构要求。
结果入口为 `verification/out/addrgen-virtual-address-20261017-01/summary.json`；
其中 `attempt02` 保存实际通过的输入快照、哈希、命令和逐周期记录。
首次测试平台声明顺序导致的编译失败保留在原目录，不覆盖失败证据。

| 检查项 | 修复后的实测结果 |
|---|---|
| AXI48、内核高虚拟地址 | 第 3 周期 MMU 收到 `0xffffffd680846000`，第 4 周期发出物理地址 `0x100846000` |
| AXI48 低地址与 AXI64 高地址对照 | 首次 AXI 和请求确认均为第 4 周期，与修复前相同 |
| 两类非规范地址的 load/store | 分别返回 cause 13/15，完整保留输入 `tval`，不发出 AXI 请求 |
| 跨页、相邻虚拟页映射至不连续物理页 | 两次请求分别使用对应物理页，虚拟地址元数据正确 |
| 负步长与非零 `vstart` | 三个元素地址和对应翻译结果正确 |
| indexed、非零 `vstart` 与背压 | 索引地址正确，spill 在背压期间保持稳定且确实经历停顿 |

周期 1 定义为接收输入向量请求的上升沿。测试使用受控 DTLB 命中和 PTE，
对意外页表遍历直接报错；因此没有覆盖 TLB miss、完整页表遍历或 Linux 启动。
这些周期对照仅证明指定场景未增加握手周期，不证明综合时序或所有程序性能不变。

另用真实 RTL 提取的 `set_end_addr` 函数完成 12 组配置、144,000 次
算术对照，全部通过，结果位于
`verification/out/addrgen-va-end-20261017-01/result.json`。
该对照检查同宽 32/64 位地址计算，不替代上面的 AXI48/VA64 集成测试。
5 项静态类型检查和 4 项测试运行器单元测试也已通过。

### 相邻边界补充回归

在同一修复 RTL 上新增 8 个 VCS 场景，全部通过。结果保存在
`verification/out/addrgen-virtual-neighbors-20261017-01/result.json`，
对应 `current/run.log` 保存逐周期信号，`inputs.json` 保存输入哈希。

| 场景 | 输入或边界 | AXI 请求数 | 完成确认周期 |
|---|---|---:|---:|
| 高虚拟地址 store | `0xffffffd680846000` | 1 | 4 |
| 跨页 store | 从 `0xffffffd680846ff0` 写 64 字节，两页映射不连续 | 2 | 6 |
| 连续加载跨低 32 位进位 | 从 `0xffffffd6fffffff0` 读 64 字节 | 2 | 6 |
| 负步长跨低 32 位借位 | 基址 `0xffffffd700000000`，stride=-16，vstart=1 | 3 | 8 |
| indexed 偏移进位及背压 | 基址 `0xffffffd6fffffff0`，EEW64，vstart=1 | 3 | 14 |
| Sv39 低半区上界附近跨页 | 从 `0x0000003fffffeff0` 读 64 字节，仍处于合法区间 | 2 | 6 |
| 关闭翻译的 load | 物理地址 `0x0000001080846000` | 1 | 3 |
| 关闭翻译的 store | 同一物理地址 | 1 | 3 |

检查同时覆盖翻译地址、物理地址、AR/AW burst 长度、描述符地址、异常、
请求数量和最终完成；关闭翻译时明确要求 MMU 请求与响应均为零。
新增场景只在修复 RTL 上运行，表中周期不是与旧 RTL 的性能比较。
本轮没有再次修改 RTL，受控 DTLB 测试的范围限制仍然适用。

复跑命令（输出目录需为新目录）：

```bash
python3 verification/vlsu/run_addrgen_virtual_address.py --neighbors \
  --out verification/out/addrgen-virtual-neighbors-new
```

## 单独待审查的物理地址风险

若 `CVA6Cfg.PLEN` 大于 AXI 地址宽度，翻译后的 PA 在进入 AXI 前也可能
被收窄。必须由平台明确保证 PA 可表示，或在完整 PA 上拒绝超出范围的
访问。QBS/AKV 在收窄后做物理范围检查也需要纳入这项审查。
这是独立于本次虚拟地址截断的风险，尚不能仅凭静态检查认定已出现板测故障。
本补丁不宣称解决该风险，也不宣称时序或板级验证已经完成。
