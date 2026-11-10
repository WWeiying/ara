# 第二阶段：QBS 与 RVV 整数乘法器协同

目标是用现有 Lane 乘法器参与 Prefill 的量化矩阵计算，不增大 SRAM、不修改外部
总线、不再复制一套大型乘法阵列。起点提交为 `b0156f8ab`。设计和验收标准见
`hardware/docs/INFERENCE_STAGE2_RVV_COOPERATIVE_MATRIX_20261109.md`。

## 当前实现范围

- `simd_mul` 和 `simd_mul_shared` 导出与原 valid/ready 对齐的完整128位乘积。
  原有低位、高位、定点舍入和饱和结果接口保留，不通过新乘法器重算。
- `qbs_lane_mul_borrow` 仅增加寄存、所有权控制和四个二乘积求和，不包含乘法器。
  一条 Lane 处理一个权重输出行，与另外四个输入行的两个连续K元素相乘。
- 入口、完整乘积和局部求和分为三拍，与 QBS 原点积阵列对齐。输入在发射前
  等待 ready；一经接收，三拍后结果必须可直接写入私有整数部分和，不允许在
  返回时再施加反压。外层必须保留所有在途结果，故障和释放也要排空这些结果。
- VMFPU 借出前等待本地普通指令及结果队列排空，并拒绝与 AKV 的 FPU 借用重叠。
  执行期间不把借用结果送入普通VRF写回，也不产生普通指令完成或异常标志。
- 首个并行矩阵候选只选择 Q4_K/M8，其余格式及行数沿用原调度。Q4_K 的32元素
  分组能匹配现有两路修正；不能直接将这一吞吐结论外推给16元素分组格式。
- 顶层 `ARA_QBS_LANE_MUL_ENABLE` 默认未定义，显式开启后也仅支持当前四Lane、
  VLEN1024的组合。尚未验收的新路径不能自动替换板上正式交付。

## 已完成的实际 VMFPU 检查

输出目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_borrow_20261109_02/`。
原始 `report.json`、两套 `run.log`、编译命令及输入SHA256均保留。

| 配置 | 普通整数指令 | 借用接收 | 借用返回 | 复位取消 | 获取/正常释放 | 准入冲突检查 |
|---|---:|---:|---:|---:|---:|---:|
| 原分位宽乘法器 | 10 | 270 | 269 | 1 | 3/2 | 9 |
| 共享乘法器 | 10 | 270 | 269 | 1 | 3/2 | 9 |

普通指令包括8/16/32/64位的 VMUL、VMULH，借用覆盖连续发射、气泡、符号边界、
获取冲突、释放排空和在途复位。每组均满足接收=返回+取消。
本测试实例化真实 VMFPU，但关闭浮点支持以单独核查整数借用；它不是浮点共存、
整个SoC或性能验收，也不证明完整矩阵已经提速。

另有独立的完整乘积/原接口对照门和借用传输门。仅以各自最终回执判定结果，不
把“已编译”“正在仿真”或部分配置完成视为整批通过。

## 已完成的乘积及矩阵级检查

独立乘积门 `stage2_mul_product_vcs_20261110_03/report.json` 已通过，比较基线固定为
`b0156f8ab`，不使用变化中的 HEAD。覆盖24种位宽/流水配置及3种共享EW8配置，
接收152,093项，退休152,050项，复位取消43项，共214,604次检查。每配置包含6,000
个随机周期及定向边界；未将它表述为全部字节对的穷举验证。

独立借用门 `stage2_mul_borrow_vcs_20261110_01/report.json` 通过，接收6,935项、
返回6,923项、复位取消12项，包含80次入口阻塞、4次复位和6次租借撤回。

矩阵级结果来自 `stage2_matrix_vcs_20261109_02/report.json`。原01 worker因日志
解析器不认识多词前缀失败，原FAIL回执保留；02通过严格离线审计复用原两份镜像，
没有重新编译RTL或改变结果/异常检查。两侧各完成36项合成功能用例、12项context
功能用例及其故障/复位检查。context套件每侧372条命令和12次在途复位；非加速
格式仍走原路径。

以下为旧Qwen2.5真实样本的首组结果，K=1536，八个不同输入行，32个输出通道。
M4以两次N32、M8以两次N16覆盖相同的256个输出。表中周期包含各命令的数据读取、
计算、排空和提交，不包含CPU量化/描述符构造等完整软件调用开销。

| 调度 | 原路径周期 | 协同开启周期 | 周期变化 |
|---|---:|---:|---:|
| 两个M4/N32 | 13,756 | 13,756 | 不变，未使用新路径 |
| 两个M8/N16 | 15,362 | 12,238 | 减少20.34% |
| 最快原调度与协同M8比较 | 13,756 | 12,238 | 减少11.04% |

不能只用较慢的原M8来宣称完整收益。单条M8的dot发射周期从6,144降到3,072，
但FP请求阻塞从0增到1,296周期；浮点运算数量不变。因此乘积吞吐翻倍不等于
矩阵性能翻倍，当前也没有据此声称达到完整投影减少20%的目标。

上述样本来自Qwen2.5。引擎fixture使用四个真实整数乘法器，但不代替完整SoC
资源所有权及软件调用验收。Qwen3的后续独立配对如下。

Qwen3后续配对已完成：见 `MATRIX_QWEN3_GATE.md` 和
`stage2_matrix_qwen3_vcs_20261109_01/report.json`。Attention Q与FFN gate均为八个
不同激活行、K=2048、N=32；原M4、原M8、协同M8分别为18,216、20,406、16,194
引擎周期。两类输入均相对最快原M4减少11.10%，输出及flags逐位一致。两种投影
采用相同的分块形状，因此周期相同并不表示其数值输入相同。

## 后继所有权及完整调用检查

`stage2_vmfpu_full_fp_20261110_01/report.json` 对应提交 `02d38f71b`，取代初版
简化仲裁作为当前所有权依据。呈现中的普通请求或PV获取优先；QBS必须等待真正
排空后才能获取，不能用“lease阻塞普通ready、普通valid又阻塞lease”的互等逻辑。
公共排空条件涵盖FP结果/flags、SLDU和归约尾部；PV原有除法器空闲判断保留。

标准及共享整数乘法配置均通过：每侧5条普通FP指令、5次flags事件、2次PV返回、
24次借用返回，以及持续请求、延迟VRF grant和真实SLDU归约回送。该门仅有一条
真实Lane，不能替代四Lane归约或SoC验收；初版无FP测试表是历史分层证据，不应
用于宣称新仲裁已经重跑了同一旧测试。

`build_projection.py` 准备完整SDK调用的独立M4/M8程序。当前固定输入为Qwen3
Attention Q：M8/K2048/N64，FFN gate：M8/K2048/N128。只缩减输出通道，K不截断。
每个模式分别从复位开始执行首次/重复两次调用，统计真实llama RVV量化、打包、
设备查询/规划、SDK执行及末尾fence。冷权重repack不在调用ROI；这仍是投影切片，
不是模型整个输出维度或端到端推理。

固件准备在 `stage2_qwen3_{attn,ffn}_{m4,m8}_build_20261109_04`，尚未代表RTL
执行。更早的01/02/03目录是开发阶段构建记录，不用于新验收。当前host预检查
实际调用SDK planner/cursor，覆盖8种规划、40条命令，核对每个输出坐标恰好一次；
并区分通用`command_n=32`与M8的`wide_command_n=16`。

首次调用清零flags验证新NX产生，重复调用预置DZ（位3）验证sticky保留；独立
oracle的NX不能被预置NX掩盖。checker的反例包括漏NX和丢DZ，不能仅检查程序退出。
`soc_loan_monitor.sv` 直接核对真实VMFPU内部乘法接受/完成，而不以引擎fixture替代。
SoC构建和调用验收尚未完成，不应将固件已编译写成已经提速。

为处理已测得的FP入口阻塞，后继候选增加协同路径专用的16项整数结果暂存，条目
140位、共280字节原始数据位，复用现有`fifo_v3`。它不扩大激活/权重SRAM，也
不复制乘法或FP阵列。目的索引、整数结果和缩放原始位随条目保存，释放整数上下文
后不再从已变化的K/输出行游标取元数据；命令完成及故障恢复均等待FIFO与FP排空。

`stage2_matrix_queue_vcs_20261109_01/report.json` 已通过，两种深度均重新编译；
深度0的周期与前一版协同镜像一致。原合成、context、故障/复位用例、最小分辨
用例及两类真实Qwen3输入均通过；不改变数值/flags/工作量期望。

| 相同八行、K2048、N32的引擎工作量 | Attention Q | FFN gate |
|---|---:|---:|
| 原M4 | 18,216 | 18,216 |
| 协同M8，暂存关闭 | 16,194 | 16,194 |
| 协同M8，16项暂存 | 13,604 | 13,604 |

新版本相对最快原M4减少25.32%周期，相对前一协同版本再减少15.99%。原M4未
使用该队列，周期不变。单条M8的下一tile等待从2,112降至816周期，其中仅剩
context1占用的等待从1,680降至384；每命令1,024项结果入队/出队相等，24次
启动发生在旧结果尚在队列时，支持“释放上下文并重叠下一个tile”的归因。
这些仍是引擎结果；不能替代尚待执行的完整SDK调用、特殊scale补充门或SoC验收。

## 后台完整调用任务

固定RTL提交：`bcc2e0082`；服务：`ara-stage2-soc-20261109-01.service`。
总目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_soc_campaign_20261109_01`。
启动时已确认两份实际VCS编译进程，后续由同一长驻服务直接托管。

流程为同提交的协同关闭/开启两份SoC构建、两侧QBS异常恢复和普通RVV/AKV交接
烟测，然后八组完整调用：两种投影、M4/M8两种程序、关闭/开启两种硬件。程序
各自从复位执行首次与重复两次调用，最多四路并行，每条仿真上限三小时。首个失败
停止派发后续阶段并保留原证据；不会自动改RTL、放宽检查或增加资源。

总状态可查看：

```bash
jq . /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_soc_campaign_20261109_01/status.json
```

`PAIRED_SOC_BUILDS`不是测试通过；`SOC_SMOKE_QUALIFICATION`不是性能完成。
`PAIRED_CALLS_CHECKED`表示配对检查完成，另以`performance_target_met`判断代表点
完整调用的20%目标是否达到。每个worker的源文件、输入、镜像和输出身份独立核查。
所有结论仍以相应最终回执为准，不把本段启动记录视为完成验收。

## 运行方法

所有结果写入唯一主验证工作树的 `verification/out`，每次使用新目录名。
禁止覆盖旧失败目录，禁止在worker运行时修改其 `source-pins.json` 所列文件。

实际 VMFPU 小测试分为准备与执行：

```bash
python3 -B verification/performance/next_mechanism/stage2/run_vmfpu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW

python3 -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW/inputs/run_vmfpu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW --execute
```

长任务必须用 `systemd-run --user` 直接托管第二条命令，不能让短启动器退出时
连带终止仿真子进程。VCS在宿主机运行，不调用 Verilator、URG 或综合工具。

## 模型数据与后续性能比较

`capture_qwen3.cpp` 和 `run_capture.py` 使用已封存、核验过的 llama.cpp 库及
Qwen3-1.7B-Q4_K_M 模型。在真实GGML图的第一层 Attention 和 FFN 投影输入处，
各收集八个不同token的归一化激活；只截取输出通道，不截短K维。

QEMU仅产生这些功能输入，不提供硬件性能数据。捕获首四行Attention激活必须
与旧四行样本逐位相同。新数据仍需在VCS中与原路径完成配对后，才能报告周期收益。

完整矩阵比较必须同时包含原M8和等工作量的原M4对照，覆盖全部输入装载、整数
修正、FP累加、排空和结果提交。原有M8权重复用不是新收益；阵列乘积率也不能
冒充整个矩阵或整模型的加速比。
