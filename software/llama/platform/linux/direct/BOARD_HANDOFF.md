# Resident 用户态直达板测交接

软件低开销后继已准备，优先使用 [LOW_OVERHEAD.md](LOW_OVERHEAD.md) 中的新包和新分析器。本文件中的原始包保留作对照；两包使用同一权限门控及同一 v4 内核，不要混用性能 ELF 与分析器。

## 本次交付

目的：测量去掉逐次设备调用和内核输入复制之后，Resident 的完整 SDK 调用是否比原生 AKV 更快。Attention 算法、KV 容量和总线不变。主机不参与板上计算。

**先生成包含权限门控的新位流，再启动配套的独立测试内核。旧位流不能直接运行此环境。**本轮没有运行 Vivado、烧写板卡或替换正式启动文件。

固定交付目录：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/
  resident_direct_delivery_20261113_01/
  resident_direct_delivery_20261113_01.tar.gz
```

| 内容 | 包内位置 | 身份 |
|---|---|---|
| 增量权限门控 RTL | `rtl/cva6-akv-direct-gate.patch` | CSR `0x5c0`，签名 `0x414b5601` |
| 配套测试内核 | `kernel/Image` | v4 源码；SHA256 见下 |
| 内核补丁与构建输入 | `kernel/`、`kernel-build-inputs/` | Linux 6.19.6，单 hart、非抢占测试配置 |
| 11 项权限/生命周期测试 | `board/safety/lease_smoke.elf` | 先通过，再允许启动性能测试 |
| 三组配对性能程序 | `board/perf/resident-direct-pair` | 原生 AKV 和 Resident 在同一 ELF 中 |
| 一键测试入口 | `board/run_environment.sh` | 校验身份、先安全后性能、失败即停 |
| 检查器及证据 | `board/perf/analyze.py`、`evidence/` | 离线检查输出、路径与完整计时记录 |

测试内核 SHA256：

```text
d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1
```

SDK 固定在 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b`，通过 `git archive` 提取，没有采用工作区未提交的 AKV 汇编。性能 ELF SHA256：

```text
ae6efa5932facf0adc0da91605486c2ba36ced24efedd8dcb18160d77663432d
```

每份包都有 SHA256 清单。内核的 `uname` 后缀沿用增量构建的 `-akv-direct-test-v1`，**不能靠这个后缀辨别候选版本**，以 Image 哈希为准。

## 给 FPGA 会话的任务

1. 阅读本文件和 `rtl/README.md`。以现有 FPGA 工程为基础吸收四个 CVA6 文件的门控增量，保留原有 FPGA 补丁、DDR、以太网和时序配置。不要把整个脏依赖目录覆盖过去。`cva6-baseline-prerequisite.patch` 仅用于还原测试基线，不应盲目重复应用。
2. 检查 CSR 经顶层、ID stage 到 decoder 的连线实际进入 FPGA 源码，生成独立候选位流并记录 SHA256。包中没有位流，也没有替代已有 OpenSBI、DTB 或根文件系统。
3. 使用包中的 `kernel/Image` 和与板卡匹配的启动环境，保留可恢复的原启动方案。新内核启用 `CONFIG_RISCV_AKV_DIRECT`，仅 CPU0/hart0 在线，不装旧 `ara_resident` 模块。
4. root 下运行下面的统一入口。不要直接跳过安全测试，也不要在任何失败后自动重试或启动整模型。

这套测试内核启动后，对所有没有取得租约的 AKV 调用都拒绝执行，**包括原先的原生 AKV/GGML 程序**。这不是普通正式内核的无感替换；普通 RVV 和 QBS 不属于该门控范围。

## 板上命令

将包内 `board/` 整个目录上传。在其目录中执行，替换实际位流哈希和新的结果目录：

```sh
ulimit -l unlimited
BOARD_ID=vcu118 \
BITSTREAM_SHA256=<本次实际位流的64位SHA256> \
KERNEL_SHA256=d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1 \
sh run_environment.sh /tmp/resident-direct-01
```

程序需要 `/dev/ara-akv-direct`、标准 V/F 状态支持、足够的可锁定内存以及可读取的用户周期计数器。板卡无需安装 Python。脚本不加载驱动、不修改启动文件，也不更换位流。环境变量中的位流/内核身份由操作者核实；脚本还会核对包哈希及运行时 CSR/ABI，但这不等同于从 FPGA 读回并证明整个位流身份。

执行顺序：

```text
SHA256 校验
  -> 11 项权限/退出/信号/缺页/共享 FD 检查
  -> SDK/权限探测
  -> T=65 配对测量
  -> T=128 配对测量
  -> T=137 配对测量
```

任意一步不通过即停止并保留日志。`status=COMPLETE` 只表示采集流程完成；最终正确性和性能结论还要通过分析器。把整个结果目录取回主机后执行：

```sh
python3 /path/to/resident-direct-01/perf/analyze.py \
  /path/to/resident-direct-01/perf
```

交回完整结果目录、内核串口日志、新位流构建身份和实际启动命令。失败时保留首次现场，不覆盖结果。

## 测量内容

- 真实 Qwen3 捕获输入，`Hq=2`、`Hkv=1`、`D=128`、F16 KV，`T=65/128/137`，4 Lane、VLEN=1024。
- 每个点先记录双方首次调用，再交错采集每侧 6 个暖态样本；不跨内核或位流比较两侧结果。
- 测量完整 SDK 路径：查询转换、能力查询、计划/检查、QK、Softmax、PV、归一化和完成等待；不是仅计一条硬件指令。
- 数据准备、F/V 初始化、预触碰、页面锁定和一次租约获取在循环外；租约获取/释放独立记录。计算区间没有设备 ioctl 或 K/V 到内核的复制。
- 对照既有独立参考输出，检查全部输出位、`fflags`、向量状态、输入不变、保护区以及真正执行的 native/Resident 叶函数计数。禁止静默回退冒充成功。
- 数据是固定、不可变、已检查的 fixture。不能据此省略实际模型中会变化的 KV、形状和数值准入检查。

## 已完成与待验收

| 项目 | 当前状态 |
|---|---|
| 实际 CSR、decoder、ID stage 等模块 VCS 门控测试 | 77,878 个检查通过；不是整 SoC 启动 |
| 客户端与分析器主机测试 | 多编译器及边界/拒绝用例通过 |
| 测试脚本停止/身份校验测试 | 9 项主机模拟流程检查通过；不执行 RISC-V 算法 |
| Linux v4 入口/返回状态审查与编译 | 静态检查、受影响对象和 Image 编译通过 |
| 两个静态 RV64 测试 ELF | 编译、哈希及客户端标量指令审计通过 |
| 新位流、测试内核板上启动、11 项安全测试 | 待 FPGA 会话执行 |
| 三组真实耗时、完整 SDK 计算结果 | 待板测；不预设一定加速 |
| 完整 llama.cpp 生成测试 | 本包不包含，先验收 SDK 路径再接入模型线程 |

本轮租约仅用于受控单线程环境。租约期间信号、fork/exec、地址映射变化和任何用户缺页会撤销并终止，不支持透明重启；提前预触碰和锁页用于避免普通懒缺页，不是取消权限保护。标准系统调用仍遵循 Linux 向量调用约定，不能跨系统调用假定向量寄存器内容保持。

进入内核时先关门控并用 `vl` CSR 读排空已接受工作，再允许 Linux 丢弃或保存 VRF；返回时重新检查线程所有权和 F/V 状态。该保护及正常调度仍有成本，因此本环境承诺消除的是逐次计算的内核调用/复制，不是“系统总开销为零”，也尚未证明可以恢复 VCS 的收益倍数。
