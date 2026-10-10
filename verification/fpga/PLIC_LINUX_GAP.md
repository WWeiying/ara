# VCU118 Linux PLIC 配套缺口审查（2026-09-22）

## 结论与边界

**静态集成缺口已确认；修复、重新生成、仿真和板卡验证均未执行。** 当前 FPGA 导出的 PLIC 是依赖仓库的默认 **32/1、nonstd_regs=1** 实现，而固定 Cheshire 配置实际要求 **58/2、nonstd_regs=0**。Linux DTS 又声明 **51 个设备中断、两个 M/S 上下文**。三者不是同一个硬件/软件契约。

问题不只是少一个 S-mode 上下文：默认生成的 `BlockAw=27` 与 SoC 传递绝对地址的方式不匹配，标准 PLIC MMIO 本身就会译码失败。正确方向是采用已存在的 Cheshire 配置，成套重新生成 PLIC，再同步软件描述；**不能只改 package 参数、DTS、IRQ 连线或关闭寄存器错误响应**。

本次初始审查阶段唯一写入是本文。该阶段外部依赖仅只读核查，没有运行生成器、make、Bender、EDA、Vivado、综合、QEMU、板卡、串口或 JTAG；没有修改 DUT、FPGA 导出、handoff、脚本或其它工作树。所有下述修复命令/验证场景在初始审查时均是后续工作，不是该次 PASS。主线程的 trap 修复/复验独立归档，不在这里重跑或代为签核。

范围澄清：用户 goal 已授权隔离生成与验证，不需要对这些既定范围内步骤逐次请求授权。本文“未执行”描述的是上次只读审查的任务范围，不是对后续工作的授权限制；后续生成/验证证据由对应任务独立归档，不能倒填为初始审查实测。本轮静态门禁任务仍不修改 DUT/导出或运行 EDA/板卡。

## 路径与版本

下列别名固定本次实查路径；`C/O/RI` 位于原工作树缓存，**不是本次写入位置**。解析依据是 `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/roots.json`，而不是猜测同名 `hardware/deps` 路径。

```text
R  = /home/wangwy/openproject/ara_dsa_verification
E  = R/hardware/fpga/ara_dsa_vcu118
B  = R/verification/out/fpga-linux-userspace-bundle-20260922
C  = /home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara
O  = C/.bender/git/checkouts/opentitan_peripherals-7b624fb57f78de9a
RI = C/.bender/git/checkouts/register_interface-902ad5bfde7bb98c
P  = E/rtl/opentitan_peripherals/src/rv_plic/rtl
T  = O/src/rv_plic/tpl/rv_plic
L  = /home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6
S  = B/inputs/opensbi-1.7
```

| 源 | 实查 Git HEAD | 历史边界 |
|---|---|---|
| Cheshire `C` | `cd73fd892a09da8aa9ae03171c0338bd3873007c` | shallow repository；不能据此排除更早的远端版本 |
| OpenTitan peripherals `O` | `cd3153de2783abd3d03d0595e6c4b32413c62f14` | 非 shallow；检查了本地可达 PLIC 历史 |
| register_interface `RI` | `ae616e5a1ec2b41e72d200e5ab09c65e94aebd3d` | 非 shallow；使用其配套 reg_iface reggen，不混用上游 TL-UL 版本 |

## 当前硬件与软件证据

### 1. 构建实际选择的是 32/1，不是闲置副本

- [sources.tcl](../../hardware/fpga/ara_dsa_vcu118/scripts/sources.tcl) 第 552、556、560、570、575 行分别选择 `rv_plic_reg_pkg.sv`、`rv_plic_reg_top.sv`、`rv_plic_gateway.sv`、`rv_plic_target.sv`、`rv_plic.sv`；[manifest.json](../../hardware/fpga/ara_dsa_vcu118/manifest.json) 同时记录这些文件及输入指纹。
- `P/rv_plic_reg_pkg.sv:10-16` 明确为 `NumSrc=32`、`NumTarget=1`、`PrioWidth=3`、`BlockAw=27`。
- `P/rv_plic.sv:101-164` 已展开固定的 `prio0..31`、32 位 IE/IP、`threshold0`、`cc0`。只改 package 的数字不会产生 `ie1/threshold1/cc1`，还会留下缺失的高位源连线。
- `P/rv_plic_reg_pkg.sv:262-267` 和 `P/rv_plic_reg_top.sv:2938-2943` 只有一个 IE/threshold/claim-complete 上下文。`devmode_i=1`，`reg_error=(devmode_i & addrmiss) | wr_err`，不是访问不存在的上下文后静默成功。
- `E/rtl/cheshire/hw/cheshire_soc.sv:1220-1231` 直接实例化此模块，只传 reg 请求/响应类型；没有生成计数覆盖。输入切成 `[NumSrc-1:0]`，输出直接接 `xeip`。

### 2. SoC 的源数为 58，上下文是单 hart 的 M 和 S

`E/rtl/cheshire/hw/cheshire_pkg.sv:209-268` 的 packed struct 给出 `NumIntIntrs=$bits(cheshire_int_intr_t)=58`；源编号由最低有效位开始：

| ID | 实际连线 |
|---|---|
| 0 | 保留零源 `zero` |
| 1 | UART |
| 2..16 | 15 个 I2C 源，按 struct 从 `i2c_fmt_threshold` 到 `i2c_host_timeout` |
| 17、18、19 | SPI host error、SPI event、USB |
| 20..51 | GPIO[0..31] |
| 52、53 | VGA 总线写/读错误 |
| 54、55 | DMA 总线写/读错误 |
| 56、57 | core 总线写/读错误 |

外设在某配置下关闭并不自动压缩此编号表。当前 32 槽只能连接 ID 0..31，32..57 被截去；`NumExtPlicIntrs=NumSrc-NumIntIntrs` 还会产生无符号下溢。此算术风险不能等同于已观察到的 CLIC 故障，当前默认配置关闭 CLIC。

同文件 `cheshire_xeip_t={s,m}`，每 hart 两位；`cheshire_soc.sv:124-125,152,655-657` 定义 hart 数并连接 CVA6 的 `irq_i`。单 hart 应为 `irq_o[0] -> M`、`irq_o[1] -> S`。现在的一位输出不可能提供两个独立上下文；不能通过改 DTS 将 M 上下文冒充 S，或把一个输出复制到两位来修复。

### 3. MMIO 地址宽度本身也不匹配

SoC 的 PLIC 窗口是 `[0x04000000, 0x08000000)`，共 64 MiB（`cheshire_pkg.sv:417`）。其地址路径没有减去 PLIC 基址：

```text
cheshire_soc.sv:369-419  AXI -> 32-bit reg -> addr_decode -> reg_demux
axi_to_detailed_mem.sv:206,256,873,896  保留地址，只做 beat/bank 对齐
axi_to_reg_v2.sv:132,187               传递 mem 地址
periph_to_reg.sv:66                   reg_req_o.addr = add_i
reg_demux.sv:34                       原样转发选中的请求
rv_plic_reg_top.sv:56                 reg_addr = req.addr[BlockAw-1:0]
```

上面桥接文件位于 `E/rtl/axi/src/` 与 `E/rtl/register_interface/src/`。因此当前 27 位译码保留了物理基址的 bit 26：

| 物理访问 | 当前 27 位 reg_addr | 当前译码结果（静态推导） |
|---|---|---|
| priority1 `0x04000004` | `0x04000004` | 不等于 PRIO1 offset `0x4`，addrmiss |
| M IE `0x04002000` | `0x04002000` | 不等于 IE0 offset `0x2000`，addrmiss |
| M threshold `0x04200000` | `0x04200000` | 不等于 `0x200000`，addrmiss |
| S IE `0x04002080` | `0x04002080` | 地址错误，且根本没有 IE1 |
| priority0 所在地址 `0x04000000` | `0x04000000` | 意外命中默认 MSIP0 offset，而非 PRIO0 |

这说明只用 **相对 offset** 驱动独立 PLIC 测试会漏掉集成错误。按 `S/lib/utils/irqchip/plic.c:262-263`，OpenSBI cold-init 从 priority1 开始写零，因此这一错误可以先于 S 上下文初始化触发。这里确认的是地址和错误响应逻辑；**没有声称已经实测 CPU access-fault、启动卡死位置或板上波形**。

默认 `nonstd_regs=1` 把 MSIP/ALERT 放在 offset `0x04000000/0x04004000`，使 reggen 需要 27 位。`T/data/rv_plic.hjson.tpl` 的 `nonstd_regs=0` 分支并非彻底删除这两个寄存器：它保留一个 MSIP 占位和 ALERT，放在 `0x03fffff8/0x03fffffc`，而 `T/rtl/rv_plic.sv.tpl:132-138` 把 `msip_o` 置零。最后 offset 加寄存器宽度恰好为 64 MiB，配套 reggen 由 `(offset-1).bit_length()` 得到 **BlockAw=26**（`RI/vendor/lowrisc_opentitan/util/reggen/reg_block.py:429-431`）。这时物理基址 bit 26 才会被正确丢弃。真正 IPI/MSIP 仍由 CLINT 提供。

### 4. 实际软件包仍声明 51 和两个上下文

[实际 DTS](../out/fpga-linux-userspace-bundle-20260922/ara_vcu118.dts) 第 70-78 行与 [导出模板](../../hardware/fpga/ara_dsa_vcu118/linux/ara_vcu118.dts.in) 相同：

```dts
interrupts-extended = <&CPU0_intc 11 &CPU0_intc 9>;
riscv,max-priority = <7>;
riscv,ndev = <51>;
reg = <0x0 0x04000000 0x0 0x04000000>;
```

DTB 已在此前只读板卡审查中解码核对，本次重新核对其 SHA-256，见文末。`L/drivers/irqchip/irq-sifive-plic.c:651-659` 明确在 `ndev` 上加一，为保留源 0 留空间；第 680、724-728 行按 DT context 顺序选地址。因此：

- `src=58` 是 **0..57 共 58 槽**，完整描述应是 **`riscv,ndev=<57>`**。`src=51` 只能到 ID 50，连现有 GPIO31/ID51 都缺失；若需求真是 51 个非零设备源，也至少要 52 槽，但仍不匹配当前完整 SoC。
- `C/sw/boot/cheshire.dtsi:114` 自身也写 51；不能把该旧 DTS 当成当前硬件源数的权威。可证明它未描述 ID52..57，不能凭此断言历史上为什么保留 51。
- M context0 的 IE/threshold/CC offset 为 `0x2000/0x200000/0x200004`；S context1 为 `0x2080/0x201000/0x201004`。对应 S 物理地址是 `0x04002080/0x04201000/0x04201004`。
- 即使临时忽略基址错误，`ndev=51` 会使 OpenSBI 写 priority1..51、初始化两组 enable word 和 M/S contexts；32/1 实现并没有这些地址。Linux 也按第二个 context 访问 S 寄存器，不会自动退回 context0。
- `B/manifest.json` 记录 `FW_FDT_PATH` 和 `embedded_dtb`：OpenSBI 内嵌的也是同一 DTB。后续必须同时更新外部 DTB、内嵌 DTB 的 firmware 和包指纹，不能只换启动目录中的 `.dtb`。

## 生成源、历史和根因

**已有可用的生成路径，不需要手写第二套 PLIC。**

| 阶段 | 精确输入/行为 |
|---|---|
| SoC 配置 | `C/hw/rv_plic.cfg.hjson:8-13`：`instance_name=rv_plic; src=58; target=2; prio=7; nonstd_regs=0` |
| 默认配置 | `O/src/rv_plic/rv_plic.cfg.hjson`、`data/rv_plic.ipconfig.hjson` 当前均为 `param_values: {}` |
| 模板默认值 | `T/data/rv_plic.tpldesc.hjson`：32、1、7、nonstd_regs=1 |
| 正常 SoC 构建入口 | `C/cheshire.mk:90-93,114`：把 SoC cfg 复制进 OTP，`make -j1 otp` 后才标记 `.generated`；当前 OTP `.generated` 不存在 |
| IP 生成 | `O/otp.mk:28-41`：`ipgen.py generate -C ... -o ... -c ...`，展开三个 RTL 模板及寄存器 HJSON |
| 寄存器生成 | `O/util/ipgen/renderer.py:271-298`：解析新 HJSON，调用 `reggen.gen_rtl.gen_rtl` 生成 reg_top/reg_pkg，并保存 ipconfig |
| 软件头文件 | `O/otp.mk:60-76`：配套 `regtool.py --cdefines` 从同一 HJSON 生成 `rv_plic_regs.h` |

模板生成的核心叫 **`rv_plic.sv`**，不是一个未找到的 `rv_plic_core.sv`；仲裁另在 `rv_plic_target.sv`。必须一并生成 `reg_pkg/reg_top/gateway/target/rv_plic`，保留 HJSON、ipconfig 和软件头文件。`ipgen` 已调用 reggen，不需要再用另一版本 regtool 覆盖其寄存器 RTL。

**当前导出路径的静态根因明确：** [prepare.py](../../hardware/fpga/vcu118/prepare.py) 第 35-71 行解析依赖并枚举 Bender sources，没有执行 Cheshire 的硬件生成 prerequisite；[export.py](../../hardware/fpga/vcu118/export.py) 第 218-295 行复制这些解析出的文件，没有 PLIC 生成/适配步骤。当前依赖仍是默认配置，五个 PLIC RTL 与导出逐文件 SHA-256 全相同；manifest 的 source hash 也吻合。证据支持“默认生成物绕过 SoC 配置进入导出”，而不是未知的 Linux 驱动版本问题。没有完整历史执行日志，故不声称还原了当年每一条命令。

本地历史进一步限制了“复用旧版本”的选择：

- 导出 `rv_plic_reg_pkg.sv` 自初始提交 `d2892695`（2026-09-08）就是 32/1；本地可达导出历史未找到已生成 51/2、52/2 或 58/2 的替代包。
- OTP 本地可达 PLIC 历史中未找到上述多上下文生成物或 51/2 配置；当前模板可接受 `src/target` 配置，**存在通用生成器不等于存在已经验证的 51/2 板卡版本**。
- `b4387a0`（2023-04-11）加入 extension-register 配置；`4a1ccfd844a1e7ff6836a36c87aee676521e903c`（2023-05-25）专门把 IE context stride 从 **0x100 修正为 0x80**。当前 pinned OTP 模板已含修复；不能回退到更早的模板，即便其单 context 测试曾能通过。
- Cheshire 缓存是 shallow；只确认 pinned 版本已有正确的 **58/2** cfg，不把未检索的远端历史称为“不存在”。未下载、fetch 或检查外部板卡存储。

还有两个生成陷阱：`otp.mk` 的 `PLICOPT ?= -s 32 -t 1 -p 7` 在当前 recipe 中**没有被使用**；设置它不会改变 ipgen 配置。`OTP_PLIC_OUT` 的 prerequisites 又没有 cfg，单独 `make otp_rv_plic` 可能认为已有文件最新。Cheshire 正常入口最终通过 `make otp -> make -B _otp` 强制生成，但它会改共享 checkout 并生成其它外设，**不应在本次/原缓存里运行**。

## 建议的原子修复单元

1. 在用户 goal 已授权的隔离验证范围内使用独立的新输出目录，固定上述依赖 commit、实际输入 hash、Python 版本和依赖版本。使用 `C` 的 58/2/7/0 配置；不把已生成 `.sv` 当输入模板，不重新下载或改动现有工作树。
2. 使用配套 `O` 的 ipgen/template 和 `RI` 的 reggen，一次生成整个 PLIC 目录及软件头文件。`O/requirements.txt` 列出 hjson、mako、pyyaml、tabulate、yapf，但未固定版本；准备隔离环境并记录版本，不能声称当前已验证可运行。
3. 在新的候选导出中成套接收五个 RTL、元数据和来源指纹；确认 58 槽、两个 context、priority 3 位、claim ID 6 位、BlockAw26、两个 pending word 和每 context 两个 enable word。显式检查 IRQ 顺序、源0常零和 `NumSrc >= NumIntIntrs`。保留固定 primitive/reg_iface 依赖，不混用不同生成器产物。
4. 同步候选 DTS 为 ndev57、M0/S1、原基址/窗口及 UART ID1；重新构建 DTB 和含该 DTB 的 OpenSBI。更新使用 PLIC 的固件头文件/生成元数据，并核对最终实际传给 Linux 的 DTB，而非仅检查源码模板。无需为这套标准地址布局魔改 Linux PLIC 驱动。
5. 与主线程已验证 trap 修复及其它待交接 RTL 合成一个新的完整 SoC 候选，重新审核 source/export 差异、manifest、SHA256SUMS。旧 [CURRENT_RTL_HANDOFF.md](CURRENT_RTL_HANDOFF.md) 不是这次配套修复后的输入快照；不在本文任务中覆盖它。

下面是**隔离生成示例，在初始只读审查阶段未执行**；隔离生成与验证已包含在用户 goal 授权中。`C/O/RI` 取前文绝对路径；`PY` 必须指向已经准备好的隔离解释器，`OUT` 必须是 `R/verification/out` 下不存在的新目录。先验证实际导入的 `reggen.__file__` 位于所列 RI，不运行共享 checkout 的 make。示例只读模板，写新 OUT，且禁止 Python 在输入树写 bytecode。

```sh
set -eu
: "${C:?pinned Cheshire source}"
: "${O:?pinned OTP source}"
: "${RI:?pinned register_interface source}"
: "${PY:?prepared isolated Python executable}"
: "${OUT:?fresh absolute output directory}"
test ! -e "$OUT"
mkdir -p "$OUT/inputs" "$OUT/sw"
cp "$C/hw/rv_plic.cfg.hjson" "$OUT/inputs/rv_plic.cfg.hjson"
PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$RI/vendor/lowrisc_opentitan/util" \
  "$PY" -B "$O/util/ipgen.py" generate \
  -C "$O/src/rv_plic/tpl/rv_plic" \
  -c "$OUT/inputs/rv_plic.cfg.hjson" -o "$OUT/rv_plic"
PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -B "$RI/vendor/lowrisc_opentitan/util/regtool.py" \
  --cdefines "$OUT/rv_plic/data/rv_plic.hjson" \
  > "$OUT/sw/rv_plic_regs.h"
```

输出验收至少包括 `rv_plic/rtl/{rv_plic,rv_plic_gateway,rv_plic_target,rv_plic_reg_top,rv_plic_reg_pkg}.sv`、`rv_plic/data/{rv_plic.hjson,rv_plic.ipconfig.hjson}`、cfg 和软件头。保存整套生成目录、命令/stdout/stderr、工具/模板/config/output hash；首次生成失败后先解释错误，不通过重复改参数、换旧工具或加 `--force` 覆盖来试错。生成器返回零也不等于下面的硬件验证通过。

## 必须验证的场景与判据

以下均 **NOT_RUN**。先做一次有区分力的集成测试，然后向完整 SoC/板卡推进，不以不断增加局部测试替代交付。预期地址取本文及固定 Linux/OpenSBI 实现，不仅使用新生成的 header 自证。

| 层级 | 必须覆盖 | 通过判据/失败定位 |
|---|---|---|
| 生成/静态门禁 | 58/2/7/0、BlockAw26、src0、claim宽度、所有输出同一配置、无陈旧副本；反例用现有32/1包 | 旧包在构建前被拒绝；source/context/地址宽度差异不能只作为可忽略 warning |
| 一次真实地址总线测试 | 使用与 SoC 相同 AXI-to-reg/demux，物理访问 `0x04000004`、`0x04002000/04`、`0x04002080/84`、`0x04200000/04`、`0x04201000/04`，并访问 ID57 priority `0x040000e4` | 每个标准32位访问成功且无别名；读写两 context 相互独立；正确处理64位总线高/低word、byte-enable及返回error；不能只在顶层减掉基址后测试 |
| 地址/边界反例 | priority ID58 offset `0xe8`、不存在 context2、IE最高word保留位、旧MSIP/ALERT与窗口边界 | 空洞地址按所选总线错误契约返回、不改合法寄存器；保留位不引发中断；无错误的26/27位别名 |
| 源与网关 | 代表 ID1、31、32、51、52、57；reset、pending、enable、claim、complete、持续电平与去断言后再次到达；ID0永不成为真实源 | 跨32位边界和非2次幂尾端不丢失；claim/complete没有重复消费或卡住；claim=0表示无可领取事件；非法完成ID不破坏其它源 |
| 优先级/上下文 | priority0禁用、阈值相等/越过、同优先级选序；分别只开M/只开S、两个context竞争同一源 | 检查实际 `ip/ie/threshold/cc_id/claim/complete` 和 `xeip.m/s`；完成跨上下文竞争按已审核契约工作，不靠复制IRQ输出通过 |
| CPU与固件 | 实际单hart RV64/Sv39配置，回放OpenSBI cold/warm初始化，再由S-mode驱动UART源1；核对中断delegation与PMP/MMIO权限 | context0连MEIP、context1连SEIP，S trap真实到达；正常MMIO不产生access-fault；错误MMIO能完整返回异常而非挂死；记录真实cause/PC和AXI响应 |
| 完整SoC/板卡 | 后续新完整SoC构建与对应bitstream；DDR初始化/访问、CLINT timer、PLIC UART交互、Linux调度 | 同一输入指纹的报告/bitstream；Linux实际`/proc/interrupts`中UART随输入增长、可重复收发、timer推进及调度正常。仅earlycon/SBI轮询打印、DDR校准或单个shell提示符均不足以关闭PLIC缺口 |
| llama目标 | Linux基础通过后，使用标准RVV fallback跑小型真实模型有界生成，再独立接入custom backend | 保留模型/ELF/内存预算与输出证据；不能把QEMU native QBS或PLIC通过称为FPGA llama/custom context通过 |

当前 PLIC 默认 `LevelEdgeTrig='0`；异步源先经 `prim_flop_2sync`。若未来确实启用边沿源，须另验脉宽/CDC/重复边沿；源码已注明没有完整 pulse-sync，不能给未使用的边沿模式补写 PASS。

建议首个定向测试设定固定 cycle 上限及不超过 5 分钟的墙钟上限，只捕获初始化访问和一次 UART claim/complete 的有限窗口。至少采集 `reg_in_req.addr`、选路、PLIC `reg_addr/addr_hit/addrmiss`、reg response error、AXI response、`intr_src_synced/ip/ie/threshold/claim_re/complete_we`、`xeip` 及 CPU trap。旧包预期在 priority1 的绝对地址译码处失败；改成相对地址后才失败于高位源/S context，则说明测试绕过了 SoC 地址路径。一次失败先比对这些信号，不增 timeout 盲重试；预计超过十分钟的全SoC/后续构建交给独立目录运行，不长时间轮询。

## 向板卡推进的下一步

初始审查给出的下一项是**隔离生成58/2/7/0候选，并完成上表的一次真实地址/IRQ集成验收**，然后接收主线程 trap 最终证据，形成可构建的完整 SoC 输入快照。它不是再增加一个与板卡无关的计算微测。隔离验证已有用户 goal 授权；生成、EDA和板卡操作未在当时的只读审查任务中执行，不意味着每一步都需再次请求用户授权。

当前没有提供与这些尚未实施修复匹配的 bitstream 证据；[软件包 manifest](../out/fpga-linux-userspace-bundle-20260922/manifest.json) 明确 `board_boot=NOT_RUN`，准备好的 Image/OpenSBI/rootfs 不能替代硬件闭环。`/dev/serial/by-id` 本次只读 `ls` 返回不存在，只说明本机未枚举该入口，不等于证明板卡不存在。

板卡阶段最少需要负责人提供：具体 VCU118/DDR配置与连接所在主机、稳定UART/JTAG标识、允许的操作窗口/操作者；若声称已有可用bitstream，则提供路径、SHA-256及完整SoC输入manifest/构建报告，而不只是文件名。已有板卡配置文件可作为候选，但CLINT时钟/路由、DDR容量/映射、CVA6 MMU/PMP/trap配置必须随实际构建和boot日志核实。本文不把它们标记为已上板验证。

**状态保留：** PLIC缺口静态确认；重新生成/修复后RTL/FPGA/Linux boot/llama均未验证；`OS_CUSTOM_CONTEXT=NOT_VALIDATED`。QEMU单进程计算、trap原ELF复验与此PLIC/板卡验收是不同证据域。

## 本次核对的 SHA-256

五个 RTL 在 `P/` 与 `O/src/rv_plic/rtl/` 中逐项相同；以下是原有文件的实读值，不是新生成物：

```text
16636ef1a144fc614d255c6e91d12b5a9898df895ceaf0e1292ed211a42af24c  rv_plic.sv
6e01bcc602506f3d0c5581b25f6bcc2d9800a84ba82488d4004c7bc071510f60  rv_plic_reg_pkg.sv
c57f256c00f09aa02a6483ec2f7fc5dd3ba1badf65225aeefc4ed822f902ed2f  rv_plic_reg_top.sv
c9d86f32bd218d3641cdac73656e6ac776b01e72041b98b5f509d3c4956078ff  rv_plic_gateway.sv
b108ec9304c49e966e7de30e6fada6035cf6e498860157f2428b77b0a1c69153  rv_plic_target.sv
f0b3ad41f5626f3396d378c8b46b3251bd05103aa289b755008ced26e6341023  C/hw/rv_plic.cfg.hjson
10f2da7ad094bcb6bc712a19f69129c8fae57987e3d4f240a3742c270744799b  O/util/ipgen.py
88e69cb7d2687a76ca2c6906503453fba3fca1e687ff3143f62afeabcbb95a84  O/util/ipgen/renderer.py
7f19ec98494ec7d47546752d8527701544071776de956084f6bf307ab8ec8155  RI/vendor/lowrisc_opentitan/util/regtool.py
ada7a97cab8458abb62ed00a530a2a8c14029ebbd8498d08bd91cd5ab7ee285d  B/ara_vcu118.dtb
```

审查使用了定向 `sed/rg`、`sha256sum`、`git log/show/rev-parse` 和只读目录检查；没有启动长期作业、运行生成命令或通过脚本更改缓存。文内未来命令和验收表不能当作已经执行的日志。
