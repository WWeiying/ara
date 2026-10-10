# Linux 向量上下文路径：源码抽取与 S 态验证

## 本次验证什么

测试 `apps/riscv-tests/isa/rv64uv/linux_vector_context.c` 在真实 CVA6/Ara
SoC RTL 的 S 态执行 Linux 标准 RVV 上下文保存/恢复序列，不使用 QEMU
代替 RTL，也不强制修改 CPU PC 或寄存器。它不是一次完整 Linux 启动。

内核切换任务时，不能只保存当前 VL 个元素：即使任务当前 VL 很小，
其余向量寄存器字节仍属于该任务。因此 Linux 临时设定 e8/m8/VLMAX，
分四组搬运 v0-v7、v8-v15、v16-v23、v24-v31，然后恢复原来的向量配置。
测试覆盖的正是这个依赖 CSR、访存、VRF 和标量/向量完成顺序的组合路径。

## 来源与边界

来源：本机 `cva6/cva6-sdk/buildroot/output/build/linux-6.19.6/` 下
`arch/riscv/include/asm/vector.h`，标准 RVV 分支：

- `riscv_v_enable` / `riscv_v_disable`；
- `__vstate_csr_save` / `__vstate_csr_restore`；
- `__riscv_v_vstate_save` / `__riscv_v_vstate_restore`。

源码 SHA256：`5b732436c12dffc97bb5638111f8c445e2557768cee595c8332dd430a3bd476f`。
该构建目录 `.config` SHA256：
`6b35a469fd9879f59a3690d52e02d51bedc3bbb603c5f8193840c293983b289f`。
保留 GPL-2.0-or-later 来源许可和原作者归属。

这是**源码指令序列抽取**，不是从现有 Image 直接裁剪出来的二进制：

| 对象 | SHA256 |
|---|---|
| FPGA 包 `linux/artifacts/Image`，也等于 SDK `install64_qemu/Image` | `716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285` |
| 当前 Linux 6.19.6 构建目录 `arch/riscv/boot/Image` | `0daba745ad9d7ee7527caf3681847c218a597a40db3ede065db53232d1ba3615` |

两个镜像不同，尚未建立旧镜像与当前源码的逐指令对应关系。不能把本项结果
声称为“原 FPGA 镜像启动通过”。现有 FPGA 工程、镜像、导出文件均不覆盖。

为隔离内核其余依赖，抽取做了以下明确适配：

1. 排除 T-Head 旧向量扩展分支；目标是标准 RVV 1.0。
2. 用固定 a0/a1 指针和五个 64 位字段代替内核结构体与编译器操作数绑定。
3. 用裸汇编函数保护寄存器分配；原始四条向量读/写及指针递增顺序不变。
4. CSR 符号转换为标准汇编名，VS 掩码为 0x600；保留先恢复 VL/VTYPE、
   再恢复 VSTART、VCSR 的顺序，保留入口开启 VS、出口关闭 VS 的行为。
5. 自建 M→S→M 包装、检查器、数据模式、独立寄存器转储，不抽取调度器。
   S 态使用 Bare 地址翻译、屏蔽中断；分页异常由独立 Sv39 测试覆盖。

## 检查矩阵

固定 4 lanes、VLEN=1024，32 个寄存器合计 4096 字节。

| 上下文 | VL | VTYPE | VSTART | VCSR | 用途 |
|---|---:|---|---:|---:|---|
| A | 17 | e32/m1/tu/mu | 3 | 7 | 非零恢复位置、饱和标志与舍入模式 |
| B | 19 | e16/mf2/ta/ma | 1 | 2 | 分数 LMUL、不同 SEW/policy |
| C | 0 | e64/m2/tu/mu | 0 | 5 | 零长度任务仍须保留全部物理寄存器 |
| D | 0 | VILL=1 | 0 | 0 | 无效配置的合法状态保存/恢复 |

按 A→B→A→C→D→B 恢复六轮，每个上下文、每个寄存器字都使用不同的
确定性数据。预期来自独立整数公式，不来自 DUT 输出。

每轮检查：

- Linux restore/save 的出口 SSTATUS.VS 均为 Off。
- restore 后实际 VSTART/VTYPE/VL/VCSR/VLENB，与保存函数捕获的五个字段。
- Linux 四次 m8 保存的全部 4096 字节。
- 独立的 32 条 `vs1r.v` 转储的全部 4096 字节，避免仅用配对
  `vle8.v`/`vse8.v` 往返导致寄存器映射错误互相抵消。
- 两个输出缓冲区前后各 64 字节 guard，检查越界写。

独立转储在完成 CSR 核对和 Linux save 后清 VSTART，不改变被测序列。
转储之后读 VL 排空向量路径，并以 fence 排序标量检查。被抽取的 save/restore
内部不额外插入 fence，不用测试包装掩盖其内部次序。

计划总计 **6415 次精确比较**。异常必须是最后一条已知 PC 的 S ECALL，
mcause=9、mtval=0、进入 M trap 前 MPP=S；其他异常记录首错并退出检查，
不采用无条件 mepc+=4。异常返回恢复全部被调者保存 GPR，避免错误地继续 S 栈。

## 仿真前的归因计划

| 假设 | 区分证据 | 判定方式 |
|---|---|---|
| VS 特权/状态控制不正确 | SSTATUS 写、特权态、提交 PC、异常原因 | restore/save 范围内任何 illegal trap 均失败 |
| VL/VTYPE/VSTART 恢复次序错误 | CSR 提交次序、dispatcher 配置状态、五字段比较 | 精确字段比较，不用最终 checksum 替代 |
| m8 长度或组映射错误 | VLSU/AddrGen 请求长度地址、v0/v8/v16/v24 请求和提交 | 保存内容与逐物理寄存器转储分别核对 |
| scalar/vector 可见性错误 | accepted/fire、队列、响应、CSR 完成及 scalar 检查 PC | 先确认实际请求/完成，不将 valid 电平算作接受 |
| 包装或程序构建错误 | 非 ZCC 反汇编、异常 PC、planned checks、rounds | 先校验 ELF/测试包装，不能直接归咎 RTL |

现有探针为 pre-edge/#1step 采样，有独立行数上限；trace 截断不能宣称
全程内部信号覆盖。提交轨迹用于 PC 定位，最终数据正确性由上述程序比较检查，
不是仅根据提交轨迹判断。必要时仅针对首错补充窗口，不盲目反复改 RTL。

## 复现

本次复用包含 CSR/FPU/trap/MMU/VLSU/dispatcher 探针的已编译 SoC：
`verification/out/trap-prereq-fixed-build-20260922/_build/vcs/simv`。
本次没有修改 RTL；该镜像没有额外启用 CVXIF contract monitor，不能声称
本次取得了该 monitor 的断言覆盖。环境使用非 ZCC LLVM，标量 C 自动向量化关闭。

```sh
python3 verification/verify.py run linux-vector-context \
  --simv verification/out/trap-prereq-fixed-build-20260922/_build/vcs/simv \
  --commit-trace --probe-kind csr --probe-kind fpu \
  --probe-kind trap_decode --probe-kind trap_ctrl \
  --probe-kind mmu --probe-kind mmu_route --probe-kind ptw \
  --probe-kind addrgen --probe-kind vlsu --probe-kind seq --probe-kind dispatcher \
  --timeout 900 --output verification/out/linux-vector-context-new-run
```

指定 `--simv` 后仍编译软件，随后冻结 ELF；不重新编译 RTL。
独立输出包含程序哈希、仿真镜像哈希、命令、提交轨迹、探针日志和判定结果。
长任务放后台，确认开始执行后不持续轮询。

## 当前状态与下一道门槛

2026-09-22 首次 VCS 执行 **PASS**，无需修改 RTL 或调整测试输入。
结果目录：`verification/out/linux-vector-context-vcs-20260922/`。

| 项目 | 实测结果 |
|---|---:|
| 上下文轮次 / 精确比较 | 6 / 6415，全部通过 |
| VCS 墙钟时间 | 156.905 秒 |
| 全程序提交数（包含初始化、比较、打印） | 74681 |
| Linux restore 的四个 load PC | 各提交 6 次，共 24 次 |
| Linux save 的四个 store PC | 各提交 6 次，共 24 次 |
| 独立转储的 32 个 whole-store PC | 各提交 6 次，共 192 次 |
| 后端 uop 分配 / 完成 | 240 / 240 |
| ACC 接口请求 / 响应 | 350 / 350，包含配置和 CSR 访问，不等于 350 条算术指令 |
| ACC 协议错误 / 最终未完成请求 | 0 / 0 |
| 提交轨迹格式 / 11 路探针完整性 | VALID / PASS，无截断或丢行 |
| 新测试静态检查与既有 plan host 测试 | 11 项通过 |

程序精确输出 `rounds=6 checks=6415 phase=6 cause=9 epc=800008b0 tval=0`。
提交轨迹独立核对每个 load/store PC 的执行次数，CSR 探针确认上下文函数
执行于 `priv=01`（S 态）；不是在 M 态访问 SSTATUS 来冒充 S 态运行。
这次没有发生新的硬件首错，不需要修改 RTL。

冻结 ELF SHA256：
`507792e734f9645c24b35a96a7cd22d102476dfcee5ad7fe0cce02930a6995c5`。
`inputs.json` 记录 simv 及其共享库哈希；结果目录另存测试源码、反汇编、
Linux 原始 `vector.h` 和运行前计划。host 首次调用缺少 PYTHONPATH，以及
新 host 检查错误假设每条 requirement 都有 suites 字段，均已修正验证调用/检查器；
不涉及 ELF/RTL，不计作硬件错误或额外 VCS 试跑。

本项通过只证明被抽取的标准 RVV context 序列在本配置下正确。
尚须验证真实 MMU 启动切换、外部/定时器中断、多任务异步抢占，以及 QBS/AKV
在任务切换时的排空与上下文策略，再复用已有 FPGA 工程验证完整 Linux 和模型。
