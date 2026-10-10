# Linux MMU 启动切换：被测路径和独立对比

## 范围和来源

本项抽取 Linux 6.19.6 `arch/riscv/kernel/head.S` 的 `relocate_enable_mmu`，
采用 RV64、非 XIP、非 shadow-call-stack、Sv39 分支。来源在本机
`/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6/`。
源文件 SHA256：`0dbda1a1b97dc30e1b763268aa495e3e650e50cc022cb1fff50db3b407a1810d`。
遵循原文件 GPL-2.0-only 许可及加州大学原始版权声明。

和 vector-context 项一样，这是源码序列抽取，不是宣称现有 FPGA Image
与当前构建目录完全对应；已有镜像哈希不同的问题见 `linux_vector_context.md`。

Linux 在物理地址执行这段代码时，先把返回地址和异常入口加上虚实地址差值。
第一次写 SATP 后，原物理 PC 不在新页表中，取指触发页故障，硬件跳到事先
设定的高虚拟地址 STVEC。跳板页表保证该高地址能取指；随后切换正式页表、
刷新 TLB，再返回高地址的调用点。此过程并不是简单测试能否读写 SATP。

## 测试包装

程序：`apps/riscv-tests/isa/rv64uv/linux_mmu_relocate.c`。

- PA 起点 `0x80000000`，VA 起点 `0xffffffff80000000`。
- 跳板页表只有高地址的首个 2 MiB superpage，没有物理 PC 的恒等映射。
- 正式页表保持相同代码映射，另增加 VA `0x40000000` 到物理数据页 A 的映射。
- M 态屏蔽中断，只把 instruction page fault 委托 S 态，再以 MRET 进入 S。
- 被抽取函数保留原始指令次序、两次 SATP 和两次 SFENCE，不插入额外 fence。
- `kernel_map` 简化成一个 VA 字段，页表来自独立测试布局；`REG_L` 展开为 LD，
  `load_global_pointer` 展开为不可松弛的 LA。禁用压缩编码使 fault 标签明确。
- Linux 的 debug park 改为受控 ECALL，避免异常时无期限自旋。走到该路径
  会因为 PC/观察值不匹配判失败，不能冒充正常完成。
- 高地址返回后额外做一次定向测试：读取 A、把 PTE 改成 B、执行按 VA 的
  SFENCE、读取 B 并写 B。该部分是测试扩展，不声称来自 Linux head.S。

## 对比不能只看 PASS

采用三类彼此独立的证据：

1. **程序内 26 项比较**：已知常量、源码标签地址、SATP、S 异常原因/EPC/TVAL、
   GP、高 VA 返回点、A/B 数据和最终写入的物理页。
2. **宿主机结果 oracle**：`check_linux_relocate.py` 根据冻结反汇编的链接地址
   和独立常量重新计算预期，不读取程序的 expected 数组。GP 从启动段实际
   AUIPC/ADDI 编码独立解码。反汇编 .text 编码逐项与冻结 ELF 校验。
3. **真实执行路径**：提交轨迹必须只执行一次各关键 PC，顺序正确；首次 SATP
   后不能在原 PA 继续提交；高 VA 指令必须与 ELF 中对应 PA 编码一致。
   CSR 探针检查两次 SATP 的实际写值和 S 特权态；trap 探针检查真实 S→S
   instruction page fault，以及正确的高 VA 跳转目标。缺失/截断不通过。

不同物理页使用不同数据，写入后分别核对 A 未改变、B 确实改变。因此，恒等
映射、只改 SATP 不改变地址、TLB 未失效、错误翻译等不能仅靠打印 PASS 混过去。
本项不使用 Spike/QEMU 全指令差分；提交轨迹核对的是这条启动机制路径，
不代表所有 GPR/内存状态逐指令已比较。

## 仿真前假设与探针

| 可能错误 | 区分信号 | 独立失败判据 |
|---|---|---|
| SATP 写未生效/错根页表 | csr_we、ack、priv、csr_wdata、satp_q/d | 两次写必须各出现一次并匹配独立 PPN |
| 页故障没有正确委托 | ex_cause/tval、priv_q、trap_to_priv、stvec | cause12，S→S，low-PC fault、高-PC入口 |
| 取指仍用物理地址 | commit PC/insn、MMU/PTW | 低地址不能在首次 SATP 后继续提交 |
| 第二张页表未使用 | 正式 SATP、数据访问、物理页内容 | 新增数据 VA 必须成功访问 A |
| SFENCE 没有更新翻译 | 同 VA 读取值、PTE、A/B 写后内容 | 重映射后读写必须落到 B，不能仍落 A |
| 包装/构建/检查器错误 | 冻结 ELF、反汇编、26项完整结果、负例检查器测试 | 标签/编码/路径均复核，先排除环境再修改 RTL |

首轮复用现有包含十一类探针的 VCS SoC；确认下述 CSR 错误后重新编译修复镜像，
不能用旧镜像证明新 RTL 正确。不改变 FPGA 包和普通 RVV 数据通路。
不启动综合、整机长启动或长模型。预期单点为分钟量级，上限 900 秒，独立目录。

## 运行与判定

```sh
python3 verification/verify.py run linux-mmu-relocate \
  --simv verification/out/linux-mmu-relocate-fixed-vcs-20260922/_build/vcs/simv \
  --commit-trace --probe-kind csr --probe-kind trap_ctrl \
  --probe-kind mmu --probe-kind ptw --timeout 900 \
  --output verification/out/linux-mmu-relocate-new-run

# 使用安装有 pyelftools 的验证 Python；下面的 dump 对应本项冻结 ELF。
# 修改软件或链接布局后须重新产生 dump；检查器将核对其与本轮 input.elf 的编码。
verification/tools/soc-venv/bin/python verification/cva6/check_linux_relocate.py \
  verification/out/linux-mmu-relocate-new-run \
  --dump verification/out/linux-mmu-relocate-inputs-20260922/input.dump
```

必须同时具有 VCS runner PASS 和独立 host audit PASS；未运行不能标为通过。
本项通过只证明所选 Linux 启动子路径及定向 TLB remap，不证明完整 Linux、
外部中断、调度、SMP、DDR 或 QBS/AKV 上下文切换已经通过。

## 首次运行发现的实际错误

`out/linux-mmu-relocate-vcs-20260922/` 首轮运行 88.67 秒，26 项中只有第 19
项失败：STVEC 期望 `ffffffff8000017c`，实际读回 `ffffffff80000140`。
保留该 FAIL，不修改预期、不覆盖首轮数据。

| 周期（pre-edge） | 捕获事实 |
|---:|---|
| 26376 | S 态把 `ffffffff8000015c` 写入 STVEC |
| 26465 | 原物理 PC `8000015c` instruction page fault，cause12，S→S，trap vector 为高 VA `ffffffff8000015c` |
| 26525 | 高 VA 继续执行，并把 `ffffffff8000017c` 写入 STVEC |
| 26859 | S 态读取 STVEC，CSR 输出错误地成为 `ffffffff80000140` |
| 26895 | 最终 S ECALL；内部 `stvec_q` 仍是正确的 `ffffffff8000017c` |

因此问题不在翻译或软件地址计算，而是 `csr_regfile.sv` 非 CLIC 读出端将
BASE[5:2] 清零，写入和直接跳转端却保留这四位。只检查最终计算结果或是否
到达主函数，很容易漏掉这个 CSR 错误。原始记录还独立证明两次 SATP、
页故障委托、高 VA 指令编码和物理页 A/B 重映射均符合本项预期。

修复非 CLIC 路径：读回存储的 `stvec_q`；Direct 写入保持四字节对齐；
Vectored 写入按现有 `priv_output` 的 cause[5:0] 拼接方式对齐到 256 字节，
避免读回 BASE 和中断实际使用的 BASE 不同。后者沿用 MTVEC 的对齐策略，
不增加地址加法器。CLIC 和虚拟化 VSTVEC 路径未修改、未宣称验证。
[RISC-V 特权规范 STVEC](https://docs.riscv.org/reference/isa/priv/supervisor.html)
规定 Direct 的四字节对齐，其他模式允许额外对齐要求。

同一修复镜像回归：原 MMU relocation ELF、514 项 `stvec_readback`（高/低
地址，Direct/Vectored 各 64 个偏移，CSRRW 的旧值及读回、保留 mode 位）、
6415 项 vector-context、116 项 Sv39、448 项异常矩阵。`stvec_readback`
检查的是该实现的 WARL/读回契约，不代表全部 Vectored IRQ 已验证。
## 修复后的实测结果

`out/linux-mmu-relocate-fixed-vcs-20260922/` 中五点全部通过，同一新编译
镜像、三个并发仿真。以下为各单点墙钟时间，不是处理器执行周期：

| 测试 | 比较项数 | VCS | 秒 |
|---|---:|---|---:|
| Linux MMU relocation | 26 | PASS | 80.52 |
| STVEC WARL / readback | 514 | PASS | 21.77 |
| Linux vector context | 6415 | PASS | 154.50 |
| Sv39 prerequisite | 116 | PASS | 83.15 |
| Trap prerequisite | 448 | PASS | 226.36 |

MMU 测试另有 `host_audit.json: PASS`，包含独立观察值、实际 SATP 写入、
S→S 页故障、高地址指令编码和探针完整性检查。新旧 MMU ELF 完全相同：
`b03778cd2a2e7d2f35ec96409260b34a331dd25e38424928aad0b6bb7ca9a98d`。
不是调整软件预期后得到 PASS。修复后的 CVA6 补丁 SHA256：
`73cacd04bec7c3afa5f397913b7bc9e1b7c14bae57d5152b7ad5b563a1d75309`。

主机核查输出中的 `retire_count=36892`、`high_va_retire_count=56` 是跟踪器
`event=retire` 的记录数量，其中包括带 trap 标记的 ECALL，不能作为严格退休
指令数或性能指标。它们用于检查执行路径，不构成逐条全架构状态差分。
检查器及相关框架的 70 项宿主自测通过，包含错误观察值、错误指令/顺序、
SATP 值、权限/委托、缺失证据等负例；这些也不是 70 次 RTL 仿真。

## 上游修复后复验的检查器选择（2026-10-09）

`upstream-integrated-smoke-20261009-01` 最初将本项也交给
`run_real_dut_case.sh`。该脚本服务于向量接口集成验收，必须观察到 CVXIF
请求/响应、后端 VID 分配以及 Ara AXI 读写。本项没有向量指令，程序虽然
完成 26 项自检，仍被 UVM 的 `CVXIF/NO_TRAFFIC`、`VID/NO_TRAFFIC` 拒绝。
这是测试与检查器不匹配，不能通过删除这两个报错来宣称旧运行通过。

修正后的整机冒烟脚本对本项调用
`run_upstream_relocate_20261009.py`，单独构建同一功能 RTL、相同参数的
标量检查镜像；其余九项仍使用原严格 UVM 检查器。本项重新采集提交轨迹和
CSR、trap、MMU、PTW 探针，运行上述独立 oracle。冻结 ELF、构建时保存的
带符号反汇编、源码清单和输入指纹一起留存，不调用 ZCC，也不重编写测试程序。
`apps/bin` 的 ELF 已 strip，不能直接从它重新生成包含源码标签的反汇编；
oracle 对保留的 dump 逐项核对 `.text` 编码与本次冻结 ELF 是否一致。

额外加入 `ifetch_payload_probe.sv`，逐周期检查取指返回：

- `cva6_icache` 在正常命中和翻译异常两种情况下都会输出 `dreq_o.valid`。
  异常响应的指令数据不是有效指令；frontend 传递异常类型并进入 trap 路径。
- 原 `a_invalid_instruction_fetch` 只检查 `valid`，未排除 `ex.valid`，因此
  页故障响应的数据为 X 时也会打印 warning。新探针不屏蔽该 warning，而是
  记录同周期的 VA、异常有效位、cause、tval 和数据未知标志，逐条解释。
- 正常取指存在任意未知位、异常有效位未知均报错。异常响应必须对应这段
  程序预期的 instruction page fault；warning 数必须与探针记录完全一致。
- 最终 oracle 仍要求原 PA 不继续提交、高 VA 指令与 ELF 编码一致、两次
  SATP 正确写入、S→S 页故障委托正确，以及 A/B 物理页读写重映射正确。

单独复验命令（宿主机 VCS 环境）：

```sh
verification/tools/soc-venv/bin/python -B \
  verification/cva6/run_upstream_relocate_20261009.py \
  --output verification/out/NEW_UPSTREAM_RELOCATE
```

以新目录的 `status.json` 和 `host_audit.json` 为验收依据。没有完整探针和
独立 oracle PASS，不能只凭程序的 PASS 字符串完成验收。旧失败记录保留，
本修正不改功能 RTL，也不扩大为完整 Linux 启动通过。

### 本次实际验收结果

仿真目录：`verification/out/upstream-relocate-closure-20261009-02/run`。
最终独立验收：`verification/out/upstream-relocate-audit-20261009-03/host_audit.json`。
前一目录的顶层 FAIL 是首次后处理缺失符号的记录，不改写；其 `run/summary.json`
为 VCS PASS。最终验收复用了该次完整仿真结果，没有调整程序、RTL 或预期值。

| 检查 | 结果 |
|---|---|
| VCS 程序自检 | 26 项，0 失败，81.87 秒 |
| 独立观察值、SATP、异常委托、TLB remap oracle | PASS |
| 提交事件轨迹 | 36,892 条，其中高 VA 56 条，路径/指令编码符合预期 |
| 正常取指 | 36,329 次，无未知 payload |
| 异常取指 | 1 次，cause=12，VA/TVAL=`0x8000015c` |
| 未知 payload / 原断言 warning | 各 1 次，均为上述异常返回 |
| 新探针检测错误 | 0 |
| 与原九项通过镜像的功能源码/配置比较 | 433 个 RTL 源文件哈希一致，配置一致 |
| 宿主检查器正例/破坏性负例 | 41 项通过 |

原 warning 的 action block 打印 `vaddr=0x80000160`，而探针用 `#1step`
记录断言同一上升沿前的响应地址为 `0x8000015c`。不能拿 action block 中
更新后的组合地址替代实际采样的 fault 地址。trap、CSR 与提交轨迹均独立
确认实际 fault PC/TVAL 为 `0x8000015c`。

对已经完成的标量仿真，仅重做独立验收的命令：

```sh
verification/tools/soc-venv/bin/python -B \
  verification/cva6/run_upstream_relocate_20261009.py \
  --audit-run verification/out/upstream-relocate-closure-20261009-02/run \
  --output verification/out/NEW_RELOCATE_AUDIT
```

该模式检查镜像及动态库哈希、冻结 ELF/反汇编编码、程序观察值、完整探针、
提交轨迹及取指未知值来源，并另存证据指纹；不是跳过失败条件重新打 PASS。
