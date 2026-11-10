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
- 借用返回固定为三拍，不是任意延迟的弹性接口。普通EW8内部流水必须为零；
  `QbsLaneMulLatencySupported`在顶层、VLSU调度和VMFPU三处同时门控。若普通
  EW8改为非零流水，整体退回原QBS调度，而不是只关闭Lane入口导致引擎等待。
  共享乘法器在VMFPU实例处显式固定`Bypass8=1`，不再依赖模块默认值。

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

正式固件在 `stage2_qwen3_{attn,ffn}_{m4,m8}_build_20261109_04`，已用于下述
完整SoC配对。更早的01/02/03目录是开发阶段构建记录，不用于新验收。host预检查
实际调用SDK planner/cursor，覆盖8种规划、40条命令，核对每个输出坐标恰好一次；
并区分通用`command_n=32`与M8的`wide_command_n=16`。

首次调用清零flags验证新NX产生，重复调用预置DZ（位3）验证sticky保留；独立
oracle的NX不能被预置NX掩盖。checker的反例包括漏NX和丢DZ，不能仅检查程序退出。
`soc_loan_monitor.sv` 直接核对真实VMFPU内部乘法接受/完成，而不以引擎fixture替代。
完整调用数值、协议及借用计数的结果见下方最终表，不以固件已编译代替验收。

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
这些仍是引擎结果；完整SDK调用、特殊scale补充门及SoC验收分别列在下方。

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

## 后续已完成的验收

`stage2_matrix_special_vcs_20261109_02/report.json` 已通过。复用上述深度0/16的
封存镜像，每侧执行六种Q4_K/M8/N5/Kb2场景：qNaN、sNaN、正负无穷、混合
符号零和FP16非规格化scale。原始SV检查器逐位检查结果及flags；详情及NaN参考值
适配范围见 `MATRIX_SPECIAL_GATE.md`。继承的half sNaN转换行为未作独立IEEE验收，
不能将保持原契约写成新完成的浮点规范认证。

完整SoC的协同关闭/开启两份镜像均已构建。两侧的 `qbs_control_smoke` 和
`qbs_akv_handoff_smoke` 都通过，报告分别在
`stage2_soc_campaign_20261109_01_{baseline,candidate}_smokes/report.json`。
包括QBS异常后的恢复、普通RVV/QBS/AKV2交接、精确异常指令匹配，以及独立
CVXIF/VID/AXI协议检查。这些烟测不是性能验收，也不替代完整指令退休状态对比。
八组完整软件调用现已执行并通过；实际周期及保留结论见下一节。

GGML已有 `GGML_RISCV_QBS_WIDE_M` 环境开关。打开后，
`ggml_riscv_qbs_plan_activations()` 调用SDK的 `qbs_recommend_activation_storage()`，
依据设备能力、形状及预计输入流量决定是否使用M8存储，不是所有Prefill自动使用M8。
本轮RTL不改变该选择或QBS指令契约；关闭软件开关仍使用原M4/小行数路径。
协同开启也只将Q4_K/M8映射到并行两组行，其余命令沿用原实现。当前完整调用测试
显式比较M4/M8，不能据此宣称整模型每个投影均已自动命中新路径。

RTL协同开关和软件wide-M开关是两个独立条件。关闭协同或配置不兼容时，已准入
的M8命令仍合法，只是使用原串行两波调度。设备能执行M8并不表示M8一定更快：
当前SDK推荐器只估算输入payload，不计量化、packing和prepared cache的成本。
本阶段不修改生产选择器、不默认开启wide-M，也不增加新的ISA或能力位。
上述fallback是在执行前按类型/形状选择；native执行中出错不能描述为自动RVV重试。

## 完整调用最终结果与保留决定

`stage2_soc_campaign_20261109_01/report.json` 已为 `PAIRED_CALLS_CHECKED`，八组
worker均为PASS，`post_pins_match=true`。两份SoC使用同一份提交`bcc2e0082`的
source archive，仅协同开关不同；同一M4或M8程序在两个硬件上使用完全相同ELF。
各组均包括首次、重复两次调用，所有输出逐位正确，Q8及边界检查无错误；flags
分别为0x01/0x09，独立协议检查通过。四条实际Lane在Attention/FFN的M8程序中
分别各接收并返回32,768/65,536个借用beat；M4借用beat为零。

下表周期包含量化、packing、查询/规划、SDK执行和末尾fence，不含首次权重repack。
两类样本均为M8/K2048，Attention N64、FFN N128；不是完整模型输出宽度。

| 真实数据切片 | 调用 | 原M4（也是协同开启后的M4） | 原M8 | 协同M8 | 相对最快原调度减少 |
|---|---|---:|---:|---:|---:|
| Attention Q | 首次 | 171,793 | 176,124 | 162,520 | 5.40% |
| Attention Q | 重复 | 170,361 | 174,676 | 161,072 | 5.45% |
| FFN gate | 首次 | 210,577 | 219,767 | 192,559 | 8.56% |
| FFN gate | 重复 | 208,733 | 218,445 | 191,237 | 8.38% |

同一M8程序关闭/开启协同，Attention每次少13,604周期、FFN每次少27,208周期。
减少量全部落在执行阶段并等于engine busy的减少；量化、packing、规划、fence
及执行中的软件余量不变。M4各阶段周期也完全不变，支持收益来自硬件协同而非
减少工作或更换软件。这不意味着engine内部各phase分配不变。

相对原M8的重复调用周期分别减少7.79%/12.46%，但原M4更快，因此最终收益应
采用表中的5.45%/8.38%。Attention协同M8的准备工作占重复调用81.24%，FFN为
68.98%；加快整数计算不能消除这些软件开销。**代表性完整调用减少20%的保留
目标未达到**，最终报告的`performance_target_met=false`必须保留。

决定是保留已验证RTL和显式开关作为候选，不默认开启，不据此替换板上验收位流。
不扩大SRAM、外部总线或算术阵列以追逐目标。固件使用真实llama的逐行RVV量化
再单独packing，不等于GGML的原生M4 interleaved量化或prepared reuse成本；因此
该表是完整SDK微基准，不是GGML算子、全宽投影或端到端推理的实测加速比。

## 真实GGML选择及回退功能门

`stage2_ggml_functional_20261110_02/report.json` 已通过，固定llama源码为
`03959acc0`、SDK为`c2b7db195`，不使用当前脏工作区。用真实Attention激活和
原始Q4_K权重构建单个 `ggml_mul_mat` 小图；GGML自行选择trait、repack、量化、
规划和执行。四臂各为独立进程、单worker，不加载完整模型。

| 配置 | M/N/K | 实际QBS命令 | 检查 |
|---|---|---:|---|
| QBS开启、wide开启 | 8/64/2048 | 4条M8/N16 | M8选择、完整量化、输出及flags |
| QBS开启、wide关闭 | 8/64/2048 | 4条M4/N32 | 默认M4、完整量化、输出及flags |
| QBS开启、wide开启、小形状 | 4/64/2048 | 2条M4/N32 | 形状回退、完整量化、输出及flags |
| QBS关闭 | 8/64/2048 | 0 | 原RVV trait、完整量化、预定数值容差 |

每臂全部量化字节与独立host准备按对应布局匹配，不能将M4/M8不同布局的原始
字节串说成相同。三条QBS路径的每个输出及flags均精确核对；普通RVV按预先固定
的绝对/相对容差2e-4/2e-5检查。host算术oracle与QEMU共享冻结`qbs_ref`，所以
这是GGML选择、准备和native ABI的功能闭环，不是独立算术模型或RTL性能证据。

首次`_01`在standalone CMake配置中因冻结源码没有`ggml.pc.in`失败，未启动
QEMU，原记录保留。`_02`使用测试侧父CMake将GGML按正常embedded模式构建，
未改生产源码或原检查器，只编译一次库；21项host检查和四臂实际QEMU执行通过。
既有QEMU与新SDK的header仅差可选QBACC编码/能力定义，兼容审计逐项核对；本门
只执行普通QBEXEC并确认QBACC能力为零，不据此声称可选QBACC已验证。

## 运行方法

### 配置保护补充验收

`stage2_vmfpu_config_20261110_01/report.json`为PASS，四套新VCS镜像均完成源文件
及镜像前后核对。零内部延迟的普通/共享配置复用原full-FP检查器，每侧5条普通FP、
2次PV返回、24次借用返回通过；另将测试副本的普通EW8内部延迟分别设为1和2，
每侧8条跨全部位宽的VMUL/VMULH正常写回/完成，持续lease和借用valid均被忽略，
借用接收/返回为零。顶层及VLSU采用静态连线检查，没有重新执行全SoC。

```bash
python3 -B verification/performance/next_mechanism/stage2/run_vmfpu_config.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_config_NEW

systemd-run --user --unit=stage2-vmfpu-config-NEW \
  python3 -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_config_NEW/inputs/run_vmfpu_config.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_config_NEW --execute
```

SDK宿主机回归另存于`stage2_sdk_host_closeout_20261110_01/host-tests.log`，生产SDK
与`c2b7db195`一致。格式转换56组合、分段执行1530形状、storage view 1809形状、
context准入7187468种规划均通过；这些是软件检查数量，不能计为RTL回归条数。

旧`test_check_matrix_v2.test_full_offline_pin_audit`绑定原运行时的live源码身份，
新的配置保护修改后应拒绝该旧身份。旧报告及冻结输入不变，不能修改旧pins使之通过，
也不能将旧SoC周期直接改标成新源码实测。本轮其余63项host检查通过（2个prepared
检查类需单独指定证据目录）；queue和special的prepared检查各12项另行通过。

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

QEMU仅产生这些功能输入，不提供硬件性能数据。捕获首四行Attention激活已与旧
四行样本逐位核对；上述VCS引擎和SoC配对给出周期证据，不能用捕获程序的运行
时间代替硬件周期。后续新输入仍须另做相同工作量的VCS配对。

完整矩阵比较必须同时包含原M8和等工作量的原M4对照，覆盖全部输入装载、整数
修正、FP累加、排空和结果提交。原有M8权重复用不是新收益；阵列乘积率也不能
冒充整个矩阵或整模型的加速比。
