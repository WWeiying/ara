# 两项原来源 FOF 静态审查

## 结论与范围

结论：两项 selection 的原源码、几何和原 oracle 未发现阻断。仅接受静态来源选择，不是 adapter/reference/DUT 验收，也没有证明 M6 尚存在对应缺陷。Tesla 的 adapter 尚待 READY 后审查；不重复已接受的 e16 H/I。

已只读检查归档 C/S、实际失败 ELF 反汇编、归档失败报告及 M6 frozen 的 predicate/FOF/drain 路径。未执行编译、参考、DUT、Host 或读取 reference raw；未修改生产文件。

审查入口：`verification/fpga/current_board_review/next_fof_failure_scope01.md`，SHA256 `e4fe7b48d9670a6aa723b1d1c4c26f6ae683540384fa84573c49289022ab53d3`。

## 原来源与失败事实

归档根目录：`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`。下面的路径均相对该根目录，散列为 SHA256。

| 证据 | 路径 | 散列 |
| --- | --- | --- |
| e8 C | `rvv_small_exceptions01/rvv_small_exceptions_e8_scenario0/scenario.c` | `9883b8afe63695b104ca0915da15f565885b99310803fefcb1baef24e67cc07b` |
| e8 S | `rvv_small_exceptions01/rvv_small_exceptions_e8_scenario0/scenario.S` | `d99047d4adb47d622c32a675ab485cd1f5c4cccd2e805f5b419056b25ab0d715` |
| e8 failed ELF | `rvv_small_exceptions01/binaries/rvv_small_exceptions_e8_scenario0` | `24f4844318a01f821681aa568aee42c1560b0f1705218dca0efa44eed34c9cbe` |
| e64 C | `rvv_small_exceptions01/rvv_small_exceptions_e64_scenario5/scenario.c` | `3fd4798e476ad168f5795d13ff3c770e00ff555616f603a5ef5c6b51fcbfac4b` |
| e64 S | `rvv_small_exceptions01/rvv_small_exceptions_e64_scenario5/scenario.S` | `79ac02eb05e4dcbb0788c8d65f912168c85416256f84309c82c63f2f5e958c04` |
| e64 failed ELF | `rvv_small_exceptions01/binaries/rvv_small_exceptions_e64_scenario5` | `a688dbfe9f1887fa028764d2e7decbdcfb3fd55460aa1e572b89f88b1c85a316` |
| Manifest | `rvv_small_exceptions01/manifest.json` | `c6d7c465085cf029c57136a7b09e79d3c232e3db2582dcfba3b2f4254b60b26c` |
| Actual sampled report | `rvv_exception_symptoms02/sampled_report.json` | `b0fd608dba2971b3ba65cb294b5e8754bd7add1f71b7cf69fc79d595197f39d0` |
| Symptoms | `rvv_exception_symptoms02/symptoms.json` | `8d6d083b90db358d2de7b21537ff8c5f79c998da258da840357a4ea73059248d` |

两项均是归档中真实独立失败单项，不是推测前序。e8 实际 numeric exit1，0.639674s：目标 PC `0x10498`，编码 `0x01050c07`，a0=`0x3f8825fffc`，badaddr=`0x3f88260000`，cause13，signal11/code2。e64 实际 numeric exit1，0.419404s：目标 PC `0x10472`，编码 `0x01057c07`，a0=badaddr=`0x3fb27ca000`，cause13，signal11/code2。两项均 unexpected_signals1/errors1；这些证据是错误的架构可见保护页异常，不是已证明的返回数值错误。完整 parent 与单项的绝对 PC 不可混用。

## 几何与完整原 Oracle

原程序 mmap 两页；令 P 为第二页起点，第二页 PROT_NONE。`start=(word*)P-4`，前四个 word 写入 11、48、85、122。物理数组保留 `word out[130]` 和 `uint8_t mask[16]`；所有 out 项按 word 类型初始化为 `0x5b`，mask 全16字节清零后仅 mask[0] 设值。不是把 uint64 数组逐字节 memset 为 0x5b。

| 项目 | e8 / scenario0 | e64 / scenario5 |
| --- | --- | --- |
| 原 shape | e8,m1,tu,mu；VL8 | e64,m1,tu,mu；VL8 |
| 实际 VLMAX（M6 VLEN1024） | 128，需实际 capacity 证据 | 16，需实际 capacity 证据 |
| Base / stride | P-4 / 1 byte | P / 8 bytes |
| 逻辑 mask | 0xff；8项 active | 0；8项全部 inactive |
| 期望 target 行为 | 元素0..3读入；元素4的非首元素 FOF fault 缩短 VL4；不交付架构 trap | 不访问无映射 target 页；不缩短 VL；不改变8项 oldvd |
| 原返回值 | packed VL4 / vstart0 | packed VL8 / vstart0 |
| 原值检查 | out[1..4] = 11,48,85,122 | out[1..8] = uint64 0x5b |
| 原 guards | out[0]、out[9] = uint8 0x5b | out[0]、out[9] = uint64 0x5b |

**e8 out[5..8] 明确允许不定。** helper 确实恢复 VL8 并存回8项，但原 C 数值检查跳过这4项；任何 observer、snapshot、独立 byte oracle 或聚合内存比较均须保留排除，不能把一次观测值固化为严格 golden。e8 原值检查共4项+2guards，e64 共8项+2guards。不能将 guard 换成 VLMAX+1，不能声称原 oracle 检查完整页/全部130输出。

原 helper 只 preload8项 oldvd，不是完整 VLMAX；因此 v24 未初始化的 VLMAX tail 不可额外要求等于0x5b。e64 的 P-32..P-8 四个原输入 word 仍须按原值设置，即使 target all-off 不读取。两项 `vlm.v` 执行时 VL8，实际消费1个逻辑 mask byte；物理16字节初始化不能缩成1字节。

## 原 Helper 与 CSR 边界

原 `load_1` 是11条指令，不是 Gather 的13条：vsetvli、oldvd load、vlm、masked FOF load、读取 vl、读取 vstart、左移32、or、恢复 VL8 的 vsetvli、store8项、ret。应保留未选择的 ordinary `load_0` 来源，不可替代目标 FOF 指令。capacity 是独立3条指令。

e8 load_1 起点 `0x1048c`，目标第4条 `0x10498`；e64 起点 `0x10466`，目标第4条 `0x10472`。原 ELF 的 helper 编码与归档 S 对应。此证据不等于 adapter ELF 与 Linux ELF 字节相同；未来 relocation/ABI/privilege 适配需单独声明。

packed return 在恢复 VL8 **之前**读取，因此 e8 返回 VL4，但 helper 返回后或 completion ecall 时 CSR VL 是8。若只核 completion CSR 而声称观察了缩短值，会丢失判别力；若硬要求 completion VL4，则误拒原程序。目标架构 trap 必须为0；允许的 completion ecall 必须在 ledger 中独立分类。目标不能通过 trap handler repair/remap/retry/跳过 PC 来完成。

## M6 静态路径与可判别信号

复用既有 M6 identity，不新建 RTL identity 验证。frozen 路径位于 `/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources`。

- `ara_dispatcher.sv:4350..4415`：FOF response 将 exception_vstart 写入 VL 并清除架构可见 exception.valid；masked exception 进入 WAIT_IDLE_FLUSH。非 FOF exception 写 vstart，不能混用解释。
- `addrgen.sv:920..958`：inactive predicate 先产生 skip descriptor，按 EEW 减少 remaining bytes、推进地址；不进入 active alignment/MMU fault 分支。e64 长度64字节，8次 inactive skip 每次减8，仍须终止请求而不是改成 VL0。
- `addrgen.sv:1260..1288`：MMU fault 通过有序结束 marker 与前面数据协调；非首元素判定使用 `VL != remaining_bytes >> EEW`，fault ordinal 为 `VL-(remaining_bytes >> EEW)`。e8 fault 时8-4=4，才应触发 FOF 缩短。
- `vldu.sv:625..666` 及 sequencer done/drain 路径负责 partial prefix、FIFO/最后 grant 和同一 Load VID 完成。内部 fault/flush 不等同架构可见 trap。

未来测量若需要定位：绑定 target VID 的 predicate ordinal/valid/ownership、remaining byte count、skip/MMU request、FOF response flag/exception_vstart、VL 更新、Load done/final grant 和架构 trap ledger。e64 的8项跨两个每4项的数据窗口，不能只验证第一个 mask 窗口；BE0 内部 VRF request 可以合法存在，不应以“没有任何内部请求”施加非架构约束。

e64 的“无 target MMU/AR”须有 target-VID 范围的实际证据才能宣称。Spike PASS、未改变 output 或未出现 trap，均不足以证明 DUT 没有发起 MMU/AR；oldvd preload、mask load、stores 和 completion 的访问必须排除出目标统计。

## READY 后最小审查边界

审查原初始化/11条 helper、实际 vlenb/capacity、VL8/mask、返回 CSR 采样位置、上述原值/guard/不定排除、原正常退出、异常 ledger 和真实 source/ELF/reference pins。当前没有发现未封存 adapter 的实际错误，不预先为其背书。

Sv39 S/M 适配可以保留此两项架构几何和数值语义，但不关闭原 Linux clone/wait/signal/PROT_NONE 编码或 schedule，也不关闭完整96调用 parent、其余20 singles、e16 H/I 的 M6 replay或全部 FOF 类型。此文不构成 DUT 启动授权。
