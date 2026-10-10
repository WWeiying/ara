# PLIC 修正与 Linux 配套验证

## 目的与边界

本阶段处理 [PLIC_LINUX_GAP.md](PLIC_LINUX_GAP.md) 已定位的集成错误：
默认 32/1/nonstd 寄存器生成物被带入实际需要 58/2/标准地址的 Cheshire SoC。
不另写一个 PLIC，不改 Linux 驱动，不把外设仿真称为 Linux 启动。
源 0 是保留槽，58 个槽对应设备 ID 1..57，因此 DTS 的 `riscv,ndev` 为 57。

## 可复现的隔离准备

以下命令从验证 worktree 根目录执行。依赖生成器只读；输出必须是新目录，
拒绝改动过的模板、错误依赖提交和已有输出。生成物不自动覆盖 FPGA 导出。

```sh
python3 -m venv verification/tools/plic-venv
verification/tools/plic-venv/bin/python -m pip install -r verification/fpga/plic-requirements.txt
make -C verification plic-prepare \
  PLIC_ROOTS=/path/to/pinned/fpga/roots.json \
  PLIC_OUT=/absolute/path/to/verification/out/plic-new
```

`prepare_plic.py` 冻结 Cheshire cfg、OpenTitan ipgen/templates、register_interface
reggen，校验源文件与固定 Git blob 相同；从副本生成五个 RTL、寄存器 HJSON、
ipconfig 和 C header。它还生成只修改 ndev 的候选 DTS template。
manifest 记录工具、命令、输入/输出 SHA-256，状态为 `GENERATED_NOT_VALIDATED`。
运行前后的原依赖不变；不能只拿 Git HEAD 代替工作区文件核查。

2026-09-22已生成候选并通过静态配套检查；初次VCS测试完成370笔事务、5282周期，
确认IE保留位、completion门控和窄读副作用三类问题。隔离补丁复验使用相同TB，
370笔事务、3223次检查、7组均PASS；尚未应用到正式FPGA导出或上板。
逐周期证据与修复范围见 [诊断和复验报告](reports/PLIC_CONTRACT_20260922.md)。

```sh
make -C verification plic-check \
  PLIC_OUT=/absolute/path/to/verification/out/plic-new
make -C verification plic-contract \
  PLIC_DIR=/absolute/path/to/verification/out/plic-new/rv_plic \
  PLIC_RUN_OUT=/absolute/path/to/verification/out/plic-new-vcs
```

以上默认流程保留原生成器行为，可用于重现负例。修复候选必须显式选择补丁：

```sh
make -C verification plic-prepare PLIC_FIX_CONTRACT=1 \
  PLIC_ROOTS=/path/to/pinned/fpga/roots.json \
  PLIC_OUT=/absolute/path/to/verification/out/plic-fixed-new
make -C verification mmio-prepare \
  MMIO_OUT=/absolute/path/to/verification/out/mmio-fixed-new
make -C verification plic-contract \
  PLIC_DIR=/absolute/path/to/verification/out/plic-fixed-new/rv_plic \
  MMIO_DIR=/absolute/path/to/verification/out/mmio-fixed-new/rtl \
  PLIC_RUN_OUT=/absolute/path/to/verification/out/plic-fixed-new-vcs
```

PLIC模板补丁只在工作副本应用，原始模板仍冻结保存。MMIO准备脚本核对两个
导出源文件的固定SHA后，在新目录生成覆盖件；其它编译源不替换。两项准备均
不改共享依赖或正式导出；生成/准备状态不自动等于仿真PASS。
新增桥接回归用 `make -C verification mmio-contract MMIO_DIR=... MMIO_RUN_OUT=...`
运行，单独检查连续请求、不同访问范围、读副作用及错误归属，不代替PLIC集成测试。
已完成同TB原桥/修复桥对照：原桥FAIL，修复桥65个AR/74个R beat、6笔写，5组均PASS。
范围与逐周期证据见 [MMIO回归报告](reports/MMIO_CONTRACT_20260922.md)。

`plic-check` 的 `STATIC_PASS` 只证明配置、选定生成结构和 DTS 对应，不是功能证明；
`plic-contract` 另行构建 VCS，保存每笔物理访问和有界周期日志，不覆盖旧结果。

配套 OpenSBI 必须重新构建，因为它内嵌 DTB。既有隔离 builder 支持显式模板：

```sh
python3 -B verification/fpga/prepare_linux_bundle.py \
  --template /absolute/path/to/verification/out/plic-new/ara_vcu118.dts.in \
  --output /absolute/path/to/verification/out/linux-plic-new
```

builder 验证 Image/initramfs 输入、加载区间及内外 DTB 逐字节相同，但不能证明
中断连线或 CPU 行为正确；状态保持 `PREPARED_NOT_BOOTED`。

## 一次有判别力的 RTL 验证

测试使用实际 `axi_to_reg_v2`、地址译码/解复用及生成的 PLIC。访问从完整物理地址
`0x04000000` 发起，不在 testbench 预先减去基址；64-bit AXI、32-bit reg 和
`CutMemReqs=1` 与当前 board_cfg 继承值对应。它不包含 CPU、AXI crossbar/AMO、
UART 实体或 DDR，因此仍需完整 SoC/板卡验收。

预先固定的判别关系：

| 假设 | 捕获与判据 |
|---|---|
| 27 位 reg 地址保留了 PLIC 基址 bit26 | 同一笔请求的 AXI 地址、reg 地址、内部 reg_addr/addrmiss 和 B/R error；旧包 priority1 物理访问应失败 |
| S context/高位源缺失 | 两个 IE word、两组 threshold/claim、ID31/32 与 ID57，区分上下文串扰和尾部截断 |
| IRQ/claim/complete 协议不正确 | 源同步前后、IP/IE、priority、threshold、两个 IRQ/ID、claim/complete；检查取消通知不等于消费 pending |
| 总线适配损坏访问 | AXI valid/ready/ID/size/strobe、reg valid/ready/error、响应背压；检查高/低 32-bit word 及每次实际握手 |
| 保留的 IE[0] 实际可写 | 对每个 context 写全 1 后检查低 word 的 bit0 必须为 0，同时保留其它使能位；不能用 source0 被绑零掩盖寄存器读回错误 |
| 禁用源的 context 仍能 completion | M 使能并 claim 持续为高的源57，S 不使能57却写 complete57；若 complete[57] 生效、IA 被释放、IP 重新置位，才能归因于缺少 context enable 门控 |
| AXI64 窄读误触相邻32-bit寄存器 | 对物理地址0x04200000发 size=2 的 threshold 读；若另有对0x04200004的 reg 读并产生 claim_re，随后 IP/IRQ 清除，则是桥接读副作用，而非源丢失 |

所有探针按上升沿前 `#1step` 采样，窗口最多8192周期，日志包含复位和事务编号。
AXI ID 会循环使用，关联事务必须同时使用单调递增的 transaction ID，不能只看 ID。
统计 `valid && ready` 才是接受事件；`valid` 保持多个周期不是多笔请求。
失败时保留源文件哈希、编译命令、事务日志和完整有界周期日志。
可恢复的语义失败记录后继续其它独立检查；协议损坏、未知控制值或超时立即停止，
不把损坏状态下的后续结果计作覆盖。修复前先用已有日志排除其它假设，
只有缺少具体判别证据才追加诊断仿真；修复后的针对性回归不能因此省略。

预期来自标准地址定义和独立事务检查，不从新生成 header 自动照抄。
[PLIC 1.0.0](https://github.com/riscv/riscv-plic-spec/blob/master/riscv-plic.adoc)
规定：threshold 约束通知而非 claim；同优先级由较小 ID 获胜；对该 context
未启用的源提交 completion 应被忽略。若生成 IP 存在其它错误，记录独立失败，
不为让生成步骤通过而调整 oracle。

## 向完整板卡推进

1. 静态配套检查与外设 RTL 仿真通过后，结合当前 CVA6/dispatcher 修复，建立新的
   完整 SoC 输入快照；保留已审核的 FPGA 适配，不整文件覆盖导出差异。
2. 完成匹配的构建/bitstream，记录 DDR/时钟/复位和 UART/JTAG 信息。
3. 验证 OpenSBI/Linux 初始化、timer 与真实 UART 中断、用户态 RVV 状态切换。
4. 先运行标准 RVV 的真实模型基线；再受控开启 QBS/AKV，补齐 custom context
   所有权与异常恢复验证。不用 QEMU 单进程 PASS 替代板卡多进程正确性。
