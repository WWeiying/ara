# Linux 系统级验证入口

Linux 验证和 bare-metal RVV 差分是两条独立签核线。`check_boot.py` 是诊断工具，不会把
“有 OpenSBI 输出”误判为完整 Linux 通过，它要求固定的启动 marker，并记录
kernel、DTB、initramfs 等输入的 SHA-256。

## QEMU/FPGA 日志签核

准备完整 console log 和 payload 后运行：

```bash
python3 verification/linux/check_boot.py \
  --log run/console.log \
  --artifact kernel=linux/Image \
  --artifact dtb=linux/ara_vcu118.dtb \
  --artifact initramfs=linux/initramfs.cpio \
  --output run/linux_boot_check.json
```

默认 marker 要求：

1. OpenSBI banner；
2. Linux kernel banner；
3. `Ara DSA VCU118 Linux init reached`；
4. `Linux console, DDR and RVV handoff are alive`。

通过启动 marker 后，还要执行独立的用户态 smoke：

- 普通 RVV arithmetic/load-store；
- QBS/AKV enabled contract；
- QBS/AKV disabled fallback；
- page fault、非法指令、线程/进程切换后的 vector CSR；
- 长时间循环和文件/内存压力。

`build_linux_bringup.sh` 负责生成 VCU118 的 OpenSBI、DTB、Linux Image 和
BusyBox initramfs。它是 payload 构建步骤，不是 Linux 验证结果；只有
`linux_boot_check.json` 和用户态 smoke 都 PASS，Linux 层才可以签核。
最终 signoff 还必须使用 `run_stage.py` 生成并带 checksum 的
`stage_result.json`；直接传入 `--linux-log` 的旧式路径只用于诊断，不是签核证据。

## 可复现运行器

先用同一个运行器执行 QEMU、RTL 仿真或板卡串口捕获命令。它保存完整命令、退出码、
超时状态、console log、marker 和 payload SHA-256；缺少任意 marker 都会失败：

```bash
PYTHONPATH=verification python3 verification/linux/run_stage.py \
  --stage qemu --output verification/out/<run-id>/linux-qemu \
  --marker 'OpenSBI' \
  --marker 'Linux version' \
  --marker 'Ara DSA VCU118 Linux init reached' \
  --marker 'Linux console, DDR and RVV handoff are alive' \
  --marker 'QBS/AKV userspace smoke PASS' \
  --artifact Image=linux/Image \
  --artifact dtb=linux/ara_vcu118.dtb \
  --timeout 3600 -- \
  qemu-system-riscv64 -machine virt -nographic -kernel linux/Image
```

`--stage rtl` 和 `--stage board` 使用相同接口，只替换最后的命令。运行器产生
`stage_result.json` 及同目录的 `stage_result.sha256`。结果中保存 stage、完整命令、
退出码、console 路径、marker、payload 路径和 SHA-256；签核时会重新验证这些信息。
它不会把 QEMU 结果冒充 RTL 或 FPGA 结果。最终检查还会验证 stage、完整命令、
创建/完成时间、payload 路径和 SHA-256，并要求至少一个只在用户态 smoke 完成后
输出的 marker：

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage linux --output verification/out/signoff-qemu \
  --linux-stage-result verification/out/<run-id>/linux-qemu/stage_result.json \
  --linux-stage qemu \
  --linux-userspace-marker 'QBS/AKV userspace smoke PASS'
```

对于 RTL 和板卡，只需将 `--linux-stage` 改为 `rtl` 或 `board`，不得复用 QEMU 的
结果目录。`TIMEOUT`、非零退出、缺 marker、payload 缺失或结果/ payload hash 改变均
保持失败状态，不允许由人工改写成 PASS。`stage_result.sha256` 用于检测结果文件
被修改；它不是证明生成者身份的远程认证，最终结论仍依赖受控工作区、命令记录和
独立复现。

## 独立 Linux 用户态验证载荷

`userspace/rvv_linux_smoke.c`、`rvv_linux_state.S` 和 `custom_caps.c` 是可同时用于
Linux/QEMU 和后续板卡 Linux 的短测试，不使用 bare-metal 的启动代码。

| 测试 | 激励与判定 | 不能据此声称的结论 |
| --- | --- | --- |
| 普通 RVV | 根据 `vlenb` 构造跨多个 VL 的整数加法，逐元素比较，检查输出前后 guard | 不是全部 RVV 指令覆盖 |
| 已修 FP 边界 | `VFREDMAX`，`VL=4/1`，输入包含正负 15，seed 为负无穷 | QEMU 通过不证明 VMFPU RTL 修复通过 |
| 定时抢占 | 同一 CPU 两个进程保持不同的 32 个向量寄存器图样，通过共享内存完成 32 次握手；比较所有 `32*vlenb` 字节及 `vl/vtype/vstart/vcsr` | 不包含 QBS/AKV 隐藏上下文 |
| 信号返回 | 异步定时信号处理函数主动改写所有向量寄存器，检查 `sigreturn` 后原状态 | 不等于所有嵌套信号已覆盖 |
| 标量页权限故障 | 对 `PROT_NONE` 页执行标量 load；处理函数修复权限并改写向量状态，检查重试后状态 | 尚未覆盖跨页 vector load 的逐元素 restart |
| 非法指令返回 | 固定非法压缩指令，核对故障 PC 后跳至已知恢复标签，检查完整向量状态 | 不等于任意非法指令解码已覆盖 |
| QBS/AKV 能力查询 | 每个扩展在独立子进程执行 query，记录原始字；SIGILL 标为 `UNAVAILABLE`，超时/其他异常判失败 | 明确输出 `CUSTOM_COMPUTE=NOT_VALIDATED`，不执行快速路径计算 |

### 判据先于运行

当前 SDK Linux 6.19.6 的 `Documentation/arch/riscv/vector.rst` 第 3 节说明普通
系统调用允许破坏向量状态；`arch/riscv/kernel/traps.c:do_trap_ecall_u()` 确实调用
`riscv_v_vstate_discard()`。因此不能拿向量寄存器跨 `read/write/sched_yield` 是否
保持来判断硬件 bug。本测试在向量状态存活期间不调用 C 函数、不执行 `ecall`：
共享内存握手使两个固定到同一 CPU 的进程必须交替被调度，并记录非自愿切换数，
拒绝未实际发生抢占的测试。汇编保存 CSR 后先清 `vstart`，再 whole-register store，
避免非零 `vstart` 让快照自身漏掉前几个字节。

信号处理函数中的系统调用只影响处理函数自己的上下文；被中断的上下文由 Linux
信号帧保存，并由 `sigreturn` 恢复。这与要求普通系统调用保留向量状态不同。

### 构建和短运行

在仓库根目录执行，输出目录必须为空，防止旧结果混入：

```bash
make -C verification linux-userspace-build
make -C verification linux-userspace-qemu
```

默认输出为 `verification/out/linux-userspace/payload/` 和同级 `qemu/`。可通过
`LINUX_PAYLOAD_OUT`、`LINUX_QEMU_OUT` 指定另一个独立目录。直接脚本支持工具、
基础 initramfs、kernel、firmware、VLEN 路径覆盖：

```bash
python3 verification/linux/build_userspace.py --output verification/out/<run>/payload
python3 verification/linux/run_userspace_qemu.py \
  --payload verification/out/<run>/payload --output verification/out/<run>/qemu
```

构建使用 SDK 的 RISC-V GCC，不使用 ZCC；C 关闭自动向量化，显式汇编发出测试所需
指令。`manifest.json` 记录源码、输入、编译命令和输出哈希，保留 ELF 和反汇编。
rootfs 单独构建，不改写历史 `linux/artifacts/`。运行使用 QEMU `virt` 的动态
OpenSBI 固件与生成的设备树，**不**把 VCU118 的嵌入式 DTB/`fw_jump.elf` 用于 QEMU。

QEMU 自动关机后检查退出码、每项用户态标记、失败日志和工件哈希；180 秒为短测试
超时，内核 panic 后请求重启时 QEMU 直接退出，不反复重启。结果通过后，可验证
这一特定 Linux/QEMU 阶段的证据：

```bash
PYTHONPATH=verification python3 verification/run_signoff.py \
  --stage linux --output verification/out/<run>/linux-check \
  --linux-stage-result verification/out/<run>/qemu/stage_result.json \
  --linux-stage qemu --linux-boot-profile userspace \
  --linux-userspace-marker 'RVV fallback userspace PASS' \
  --linux-userspace-marker 'RVV context switch and fault return PASS'
```

这只能给出所选阶段通过，不能给出 VCS、板卡或完整模型通过。

若 VCS Linux 启动长期耗在软件初始化，先在独立目录构建验证专用内核，
不修改 SDK 的原地构建树或部署镜像。`--lean-init` 在原有
`CONFIG_JUMP_LABEL=n` 基础上关闭 FTRACE/Event Tracing/BPF Events；这是
针对旧运行后段反复停留在 trace-event 初始化附近的可检验假设，不是 RTL 修复：

```bash
verification/linux/build_fast_kernel.sh \
  --output verification/out/linux-fast-kernel-<run> \
  --memory-model flat --lean-init --jobs 16
python3 verification/linux/run_userspace_qemu.py \
  --payload verification/out/linux-userspace-20260922/payload-checked \
  --kernel verification/out/linux-fast-kernel-<run>/build/arch/riscv/boot/Image \
  --output verification/out/linux-fast-kernel-qemu-<run>
```

该脚本从 SDK 的 Linux 6.19.6 源码包单独解包并保留原 RVV/MMU 配置；
`--configure-only` 可先审查配置，随后用 `--build-only` 在同一输出目录编译。
QEMU 通过只证明该测试软件在新 Image 上可运行，不能证明 VCS 时间缩短或
部署内核通过。RTL 未变时可复用已核验的 VCS 编译镜像，只更新匹配的
OpenSBI/DTB/initramfs 封存包。首次改动内核配置时仅在有足够靠前的判别点时
做短程 VCS 对照，核对周期、指令提交和 UART 里程碑；否则直接安排一次带早停
条件的完整启动。旧运行约在 1690 万周期才进入内核，低于该周期的里程碑只能
检查启动包接入，不能检验 tracing 改动。之后同一冻结配置不重复跑短程预演。

2026-09-23 的独立实验中，256 MiB FLATMEM `--lean-init` Image 已通过 QEMU
用户态自检，证据在 `verification/out/linux-flatmem-lean-qemu-256m-20260923-01/`。
此结果尚未证明 VCS Linux 能启动到用户态。

如果需要减少 OpenSBI 启动信息经 115200 波特率 UART 逐字节输出的时间，可在
**验证专用** bundle 构建时加 `--quiet-opensbi`。它使 OpenSBI 以
`FW_OPTIONS=0x1` 关闭启动横幅，保留 Linux 和用户态 UART 输出；不会修改
芯片 RTL 或默认固件。SoC 运行器从封存包读取该选项，在静默模式下要求
Linux 报告 `SBI specification` 与 `SBI implementation ID`，再要求原有的
内核、init 与 RVV 用户态 marker。原有非静默模式继续要求 `OpenSBI v`
横幅。两种模式都必须通过独立 `check_soc_linux.py` 审计，里程碑或 QEMU
通过不能代替 RTL 用户态签收。

一次静默 OpenSBI 加 FLATMEM 精简内核的诊断运行在约 640 万周期打印
`Booting Linux on hartid 0`，并在 700 万周期按里程碑停止，耗时
1780.542 秒；状态为 `LINUX_MILESTONE_REACHED`，不是启动通过。旧运行约
1690 万周期才进入内核附近，但两次内核配置不同，不能把周期差全归因于
OpenSBI 横幅。后续诊断可复用已编译 VCS 镜像，并用
`--linux-uart-milestone 'Linux version'` 在所需 UART 证据出现时即停；
完整签收运行不要设置诊断里程碑，保留失败和停滞早停即可。

### 2026-09-22 实测记录

结果位于 `verification/out/linux-userspace-20260922/`，没有覆盖基础 Linux 工件。
最终使用 `payload-checked/` 的 ELF/initramfs，在 `qemu-checked-vlen1024/` 完成
Linux 6.19.6 + OpenSBI 1.7 + QEMU 10.2.0 用户态测试；单核、VLEN=1024，主机
运行耗时 8.185 秒，模拟器退出码 0。`linux-check/signoff.json` 复核该 QEMU 阶段
通过，不代表整个验证计划签核。

| 检查 | 实际观察 |
| --- | --- |
| RVV 运算和访存 | 101 个元素和边界 guard 通过 |
| VFREDMAX | VL=4/1 边界通过 |
| 抢占恢复 | 父/子各比较 4096 字节，非自愿调度次数分别为 34/33 |
| CSR 恢复 | 父进程 `vl/vtype/vstart/vcsr=9/9/3/3`；子进程 `11/1/1/5`，均通过 |
| 异步信号、标量页故障、非法指令返回 | 完整向量快照和 CSR 通过；页故障检查精确 PC、地址及修复后的 load 返回值 |
| QBS/AKV query | 两者均捕获 SIGILL，记录 `UNAVAILABLE`；这是通用 QEMU 的预期 fallback，不是快速路径计算通过 |

首轮 `qemu-vlen1024/` 未通过：BusyBox 动态加载器查找 `/lib64`，基础 cpio 中
库在 `/lib`，但遗漏了 SDK 根文件系统中的 `lib64 -> lib`。依据启动日志、加载器
搜索路径和 cpio 内容修复打包脚本后才重跑；没有修改处理器 RTL。新 builder 补齐
缺失的别名，保留已有合法目录/链接，原始 cpio 仍保留。基础板卡构建脚本也已
修正，旧工件不会自动获得该修复，后续须重新构建匹配的部署文件。

环境 Python 测试为 `223 passed, 1 warning`，warning 为既有的 `TestResult`
pytest 收集提示。只有 VLEN=1024 的上述运行有本轮动态证据；其他 VLEN、板卡、
RTL Linux、向量跨页 restart 和 Linux 下 QBS/AKV 计算不在此 PASS 范围内。

### QBS/AKV 用户态仍需补齐的合同

- 当前 query 编码为 `0x5b`，QBS `funct3=1`，AKV `funct3=4`，`rs2=x0`。
  query 前执行普通 `vsetvli` 建立 Linux 向量状态；成功 query 可能清 `vstart`，
  不能声称完全不改变架构状态。
- QBS/AKV 的共享读引擎有 MMU 翻译及 4 KiB 边界处理；`OSSupport=1` 是必要配置。
  有翻译时 descriptor 和内嵌数据地址是虚拟地址，不能用裸机物理地址经验代替 Linux
  验证。当前只验证源码连线，尚未证明板卡权限、缺页和异常返回路径。
- QBS activation cache、AKV Q/K/V 上下文位于 VRF 之外，没有 Linux task/ASID
  所有权绑定。普通 RVV 上下文切换不保存它们，绑定 CPU 或进程内 mutex 不能隔离
  其他任务。必须明确驱动/调度器与硬件的独占、失效重建或保存恢复合同，再启用多
  进程快速路径。
- AKV 有 release；QBS 的 RELEASE 是带计算的提交后失效，不是可随时调用的独立
  flush。不能直接把它当成操作系统上下文清理指令。

单调用者 QBS DIRECT 小计算现已在独立 QEMU 测试中通过：真实 Q4_K tile 为
`M=1,N=32,K=1536`，23 次能力查询、1 次执行、32/32 输出比较；另有强制 RVV 和
扩展关闭的两组对照。它未使用隐藏上下文，不能替代上面的多任务合同。
详见 [CUSTOM_RUNTIME_READINESS.md 第 9 节](CUSTOM_RUNTIME_READINESS.md#9-后续-linux-用户态-qbs-小计算实测)。

下一阶段继续解决这些系统合同，再验证其他 Linux 用户态小计算、非法/fallback、
任务切换与异常恢复，最后才扩大到完整 llama.cpp。QEMU 的 custom-op 实现也须和
实际 RTL 的合同逐项核对，不能用其运行成功替代 RTL 证据。

### 部署到板卡前

必须由当前修复版 RTL 重新产生匹配 bitstream，并检查导出源码版本。新的 initramfs
大小不同，VCU118 DTB 的 `linux,initrd-end` 以及内嵌该 DTB 的 OpenSBI 必须一同
重建，不能只替换旧加载命令中的 cpio。先运行普通 RVV 用户态测试和能力查询，
再接入受控的 QBS/AKV 计算；当前测试 init 在完成后会关机，不是交互式模型 rootfs。
