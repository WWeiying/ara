# Resident 用户态直达测试环境

## 目的与范围

这套环境用于回答一个问题：去掉每次 Attention 调用的驱动往返和输入复制后，Resident 能否在 Linux 下比原生 AKV 更快？

旧路径在每次调用中进入内核，检查并复制输入，再借用内核浮点/向量状态执行。新路径只在开始和结束时办理独占权限，计算期间直接在用户态执行现有 AKV/Resident 指令。没有修改 Attention 算法、KV 容量或总线，也没有把工作移到主机。

当前测试对象是从真实 Qwen3 数据构造的完整 SDK Attention 调用，不是完整 llama.cpp 模型。测试保持 4 Lane、VLEN=1024、F16 KV，先覆盖有效 KV 长度 65、128、137。完整模型的接入需要后续将同样的权限生命周期放到模型执行线程外层；不能将本测试程序的成功等同于模型已完成验收。

**这是需要新内核与新权限门控 RTL 的候选环境。旧位流不具备该权限门控，不能仅复制 ELF 就启用。**旧 broker、注册视图测试及其证据保持不变，不自动替换正式部署。

## 调用流程

```text
程序启动
  -> 检查内核接口、CPU 配置、权限门控版本
  -> 准备并预触碰数据、缓冲区和栈，初始化标准 F/V 状态
  -> 锁定页面，获取一次线程独占权限
  -> 交错运行原生 AKV / Resident
       完整 SDK 准备 -> 自定义指令与 RVV 计算 -> 等待完成
       此区间不调用设备 ioctl、不复制 K/V 到内核
  -> 检查输出、fflags、保护区、输入不变和真实执行路径
  -> 释放权限并清理私有上下文
```

权限不是普通互斥锁。硬件必须拒绝没有权限的线程执行 AKV 指令，Linux 必须在切换线程、异常退出和其他生命周期事件中正确处理权限及私有上下文。普通 RVV 和 QBS 不受该 AKV 门控影响。

## 硬件接口

新增 supervisor CSR `0x5c0`，读回高 32 位签名 `0x414b5601`。低三位如下：

| 位 | 名称 | 含义 |
|---|---|---|
| 0 | STRICT | 开启 AKV 权限检查 |
| 1 | U_ALLOW | 允许用户态执行 AKV |
| 2 | S_ALLOW | 允许 supervisor 执行 AKV，例如受控清理 |

复位后三位为零，保留旧系统行为。开启 STRICT 后，`opcode=0x5b` 且 `funct3>=2` 的 AKV 指令都受控，包括旧 AKV 操作、INFO、FULL/REFILL、RELEASE 和 Resident QK/PV。只限制 Resident 新指令是不够的，因为旧 AKV 指令也能改写同一私有上下文。

门控依据实际执行特权级，而不是 MPRV 指定的访存特权级。M-mode 是可信固件。CSR 写入需刷新后续指令，避免旧权限下译码的指令跨越权限变更。

实际 RTL 修改位于 CVA6 依赖中的 `core/csr_regfile.sv`、`core/decoder.sv`、`core/id_stage.sv`、`core/cva6.sv`。权限信号从 CSR 经 ID stage 进入实际译码器。依赖目录原先已有其他本地修改；移植时应使用本次交付的增量补丁及输入哈希，不要将整个脏依赖目录覆盖到 FPGA 环境。

## 用户接口

`direct_uapi.h` 定义 `/dev/ara-akv-direct` 的三项 setup/teardown 操作：

| 操作 | 用途 |
|---|---|
| `GET_INFO` | 检查 ABI、门控签名、单 CPU 配置及支持的保护能力 |
| `ACQUIRE` | 为当前执行线程取得独占权限，返回代次与所有者身份 |
| `RELEASE` | 撤销权限并完成私有上下文清理 |

`direct_client.c` 不提供逐次计算 ioctl。计算仍使用固定提交的原生 SDK 和 Resident 汇编。客户端只负责开始和结束，不能替代内核权限验证。

首版限定单 hart、单执行线程、受控测试。租约期间的信号、fork/exec、权限撤销以及用户态缺页均按配套内核规定终止或拒绝，包括普通的懒分配缺页。因此测试在获取权限前完成标准 F/V 状态初始化、页面预触碰和 `mlockall`。这不是透明的任意进程迁移、信号重入或缺页重放方案。

内核进入路径先关闭权限并排空已接受的向量工作，再让 Linux 丢弃或保存向量寄存器。该步骤尤其针对提前应答的本地 KV 读取，不能将“CPU 已收到应答”误认为“VRF 写回已经结束”。它发生在系统调用/中断边界，不是逐次 Attention 的驱动计算接口。

## 性能统计

- 原生 AKV 与 Resident 使用同一 ELF、同一内核、同一位流和同一份输入。
- 正式计时保留查询转换、SDK 计划/检查、Softmax、计算和完成等待；不会仅报告 QK/PV 内核时间。
- 权限获取/释放和固定测试数据准备放在测量循环外，并单独记录。固定输入的预检查不能推广成“任意可变 KV 永远无需检查”。
- 测试记录真实 native/Resident 叶函数调用数，成功返回不等于快路径确实执行。
- 首次调用和暖态调用分开；每侧 6 个暖态样本交错执行。
- 输出、异常标志、保护区或路径不符时不接受性能结果，也不静默回退。

这消除的是 **每次调用额外的内核往返与复制**，不是承诺整个系统没有任何开销。首次权限建立、正常 OS 调度、必要的数据准备和计算同步仍然存在；能否恢复先前 VCS 中约 1.21 倍的完整 SDK 收益，必须以新板测结果判断。

## 构建与交接

本轮新增可选的 [概率数据通路候选](COMPACT_HANDOFF.md)：Softmax 后直接存 FP16，
PV 不再读回 FP32 后转换；不增加工作区、不改 RTL。它默认关闭，独立包用于验证，
不能在没有板测结果时替代已经验收的软件。

最新软件候选见 [PREFLIGHT_HANDOFF.md](PREFLIGHT_HANDOFF.md)：在复用 QK/PV 控制字和尾块计划的基础上，取消同一调用内重复的计划/描述符校验。它继承 [PREPARED_HANDOFF.md](PREPARED_HANDOFF.md) 的全部准备优化；优先使用新交接文档中的包，旧包保留作对照。

已准备软件低开销后继，见 [LOW_OVERHEAD.md](LOW_OVERHEAD.md)。下述 `build.py` 保持原始冻结 SDK；后继 `build_low_overhead.py` 使用同一 SDK 基线加四项登记增量，不覆盖原交付包。

用户态构建入口为：

```sh
cd /home/wangwy/openproject/ara_dsa
python3 -B verification/performance/resident_deployment/direct_cost/build.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_direct_build_MANUAL_01
```

输出目录必须不存在。脚本从 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b` 提取 AKV SDK，不会使用工作区未提交的 AKV 汇编；固定真实输入、编译参数、源码哈希与 ELF 哈希均留档。

板测脚本、结果分析器及运行说明位于 `verification/performance/resident_deployment/direct_cost/`。当前内核候选位于本目录的 `kernel/v4/`，早期目录保留用于追溯，不能混用其镜像。具体板测交接见 [BOARD_HANDOFF.md](BOARD_HANDOFF.md)。交接时必须同时提供：

1. 权限门控 RTL 补丁与配套新位流的构建身份。
2. 配套内核补丁、配置及启动镜像身份。
3. 冻结 SDK、测试 ELF、SHA256 清单和板测脚本。
4. 已完成的离线检查结果与仍待完成的板测项目。

先检查权限隔离和清理行为，再测三组耗时。不要在正式系统上直接覆盖内核、驱动或程序；不要将未实施门控的旧位流与新 ELF 混用。构建成功、模块级 RTL 测试通过和板上实际通过是三个不同的验收状态。
