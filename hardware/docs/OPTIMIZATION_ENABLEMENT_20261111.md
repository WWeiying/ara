# 已有优化的统一启用与组合验收

## 目标与边界

本轮目标是补齐已有优化缺少的组合测试，把通过验收的实现纳入可复现配置，
并明确记录暂不能开启的原因。不是新增性能机制，也不扩大 SRAM、修改总线或
改变模型权重。不启动新的综合和板测，不将主线修改自动同步成已验收的 FPGA 位流。

开发目录为 `ara_dsa`；新增验证输出统一保存于
`ara_dsa_signoff_integration/verification/out/enablement_*`。
原有板测交付标签、源码冻结目录、首错证据及不相关的未提交修改均保留。

## 逐项验收清单

| 项目 | 当前实现 | 本轮处置与必要检查 |
|---|---|---|
| ALU/移位器共享 | 主线直接使用 | 保留；随代表性 SoC 回归检查 |
| VRF 返回网络与 FIFO 精简 | 主线直接使用 | 保留；不能删掉控制复位或缩减队列容量 |
| QBS 权重宏、AKV 统一存储、共享读引擎 | 主线直接使用 | 保留；不把历史文档中的旧组织当作当前实现 |
| 共享整数乘法器 | 依赖编译宏 | 接入明确构建选项；检查普通 RVV 与 QBS 借用接口 |
| 共享 FMA、紧凑流水与标签 | 原默认关闭 | 接入明确选项；补完整 Resident 与 M8 组合，不以单独部件测试替代 |
| Resident QK/PV | 依赖 RTL、SDK 和平台提供者 | 硬件组合测试后保留可选能力；软件必须独立获得平台准入 |
| QBS M8 协作 | 原默认关闭 | 检查全组合与固定格式；不能直接全局打开旧 WIDE_M |
| QBS/AKV、激活上下文、已有 M4 四项 | 专用软件配置默认请求 | 检查显式关闭、形状选择和原实现回退 |
| 量化 KV、Grouped Prefill、Register-PV | 专用配置支持 | 保留类型、内存、单 worker 和布局条件 |
| 旧 GROUPED_PV | 原可选 | 与 Register-PV 互斥，不能同时默认打开 |
| 阶段4 retained-maxima | 已接入受限软件路径 | K1536 缓存冷生产；目标测试、完整编译及真实图独立审计通过 |
| 阶段4 features-v2 | 显式 SDK 入口 | 不用一个编译宏绕过 GGML/plain-score/provider 契约 |

“纳入构建”表示目标可以生成该实现；“请求启用”表示软件尝试选择；
“实际命中”还需要类型、形状、状态、所有权和内存准入全部成立。
这三个状态不混用。

## 已完成的本轮检查

### 默认策略与平台准入

结果目录：`enablement_host_20261111_02`。
`result.json` 状态为 `HOST_POLICY_AND_ADMISSION_PASS`。

- AUTO 未定义、显式 0、显式 1 三种构建，各通过 32361 项默认策略检查，
  包含新增 retained-maxima 请求及量化内存授权、旧 GROUPED_PV 不得隐式开启的检查。
- 当前 llama.cpp 的平台准入实现，通过普通宿主构建和 UBSan 构建，
  每种执行 88 项检查，覆盖拒绝条件、完整调用 lease、状态变化和范围检查。
- 实际 llama.cpp 默认策略头与 Ara 保存的策略头字节一致。
- 测试使用固定 SDK 归档，不使用当前未提交的 AKV 汇编。
- 保存编译命令、输入 SHA256、日志及结果；结束时输入身份核验一致。

这些是宿主策略和协议检查，不证明自定义指令执行、RTL 性能或板上内存授权。
它们也不替代随后真实 VMFPU/SoC 组合测试。

### 构建开关

`config/optimizations.mk` 接入共享整数乘法器、共享 FMA、Resident QK/PV 和
QBS lane 借用四项开关。`hardware/Makefile` 的 VCS/DC 命令均传播对应宏。
默认 `generic` 行为不变；`candidate_all` 同时选择四项，支持单项显式关闭。
Resident 和借用路径继续限制为四 lane、VLEN1024；独立共享算术不额外限制几何。

`enablement_config_20261111_01/result.json` 为 `OFFLINE_CONFIG_CHECKED`：
11 项测试通过、无跳过，包含实际 SV 预处理及 Make 命令展开。
该证据不包含综合、RTL 执行或平台能力授权，Resident 能力查询仍不作生产承诺。

### 全组合真实 VMFPU

`enablement_lane_combo_20261111_02/report.json` 为 PASS。
当前 RTL 的共享 FMA、共享整数乘法器、QBS 借用接口与 Resident QK/PV 同时使能。

- QK/PV 的 26 个 SoftFloat 对照场景完成：6222 次 FP32、80 次 FP16 私有请求，
  6298 次返回，另有 4 次按测试计划由复位取消；不能将这些请求计作架构指令。
- 同组 25 次整数借用请求与返回一一对应。
- 独立 native/Resident/borrower 争用测试完成 5 条原生指令、2 次 PV 返回、
  24 次整数借用；检查写回、异常标志、背压、归约完成和所有权释放。
- 200 项输入 pins 与 78 个镜像文件核对一致。全流程约 164 秒。
- 首次尝试仅因测试清单遗漏已锁定的 `stream_register` 依赖而编译失败；
  原失败保留，新 runner 只补测试清单，不修改 RTL 或放宽检查。

这是单个实际 VMFPU/控制器的组合证据，尚不是四 lane SoC、完整 GGML 或 FPGA 验收。

### Retained-maxima 的实际接入

当前 llama.cpp 新增 `q8_K-m4-preflight.h` 薄适配层，调用固定 SDK 中已测的
`m4_preflight.h`，不重写量化算术。专用 initial cache 编译开启，AUTO 请求开启；
普通构建默认关闭，显式 `GGML_RISCV_QBS_M4_PREFLIGHT=0` 始终优先。

新 producer 仅在以下条件同时成立时选择：K1536、单 worker、真实图策略允许
共享输入查找、Prepare/Cache/Packed/Parallel Sums 全开。它只改变 cold miss，
在查询前选择独立 producer tag4；命中继续恢复原 payload 和 raised FFLAGS。
域检查拒绝后的 generic 生产只执行一次，不能因返回 false 再量化一次。

- `enablement_software_m4preflight_target_20261111_02/result.json` 为
  `M4_PREFLIGHT_GNU_SPIKE_CHECKED`，16 个独立 GNU/Spike 启动通过。
- 输入来自已固定的真实 K1536 模型激活；数值 producer 与 cache 实现为实际源码，
  graph/capability 元数据由测试提供，不将其称为完整 GGML 图。
- 检查完整 packed bytes、guards、CSR、256 种 sticky-FFLAGS/VCSR 命中组合，
  输入末字节变化、epoch/source 失效及 tag3/tag4 隔离。
- 关闭开关、非适用形状、非 RNE、晚出现的 subnormal/Inf/qNaN/sNaN 均有负例。
  非零 VSTART 在 `prepare()` 入口拒绝，未发生 cache 查询或 producer；
  这不扩展为整个 GGML 入口在任意非零 VSTART 下均可安全运行的保证。
- `enablement_software_m4preflight_build_20261111_01/build.json` 为
  `FRESH_FULL_LLAMA_BUILD_CHECKED_NOT_MODEL_EXECUTED`。
  `llama-simple`、`llama-completion`、`llama-bench` 重新完成静态编译。
  实际编译命令与依赖文件包含新适配层、SDK helper 和对应宏。
- 独立复核目标测试 1393 项 pins 与完整编译 1208 项 pins，均匹配。

当前完整 `llama-simple` SHA256：
`d08fb68839c1bd7612e374542eb4c297f0e688684e98e4479bffc6304ff018cd`。
真实 Qwen2.5 图的 OFF/ON 结果见下一节。先前约 2% 是 SDK 完整调用收益，
不是本轮模型加速比。

### 真实模型图与保留的首个失败

`enablement_model_m4_20261111_01` 使用同一完整程序的两侧运行，只有
`GGML_RISCV_QBS_M4_PREFLIGHT=0/1` 不同。模型为真实 Qwen2.5-1.5B Q4_K_M，
Prefill 26 token 后一次 Decode，两侧均正常退出。它验证 K1536 新入口，
不是代替论文中其他模型或更大上下文的性能实验。

原 worker 状态保留 FAIL：原生 QBS 调用计数比 summary 少 1。静态分析结合
原日志确认，每侧生成文本不换行，使首条 QEMU Trace 粘在文本末尾；
解析器只认行首 Trace，分别遗漏一条。未改 RTL、程序、QEMU、计数要求或原日志。

独立 `model_m4_audit_v2.py` 只对已绑定日志 SHA 的两处完整记录分帧，
然后重新执行冻结的原 checker。21 项新旧负例保证错误数值、额外命令、
错误前缀、缺失 producer 和截断仍被拒绝。原 FAIL 未被改写。

`enablement_model_m4_audit_20261111_01/result.json` 为
`MODEL_M4_FRAMING_AUDIT_PASS`，完成原输入/镜像的前后身份核验：

| 检查 | 结果 |
|---|---|
| 完整 logits | 303872 个 FP32 值逐位一致 |
| 两个 greedy token | 2014、6923，两侧相同 |
| 每侧 native QBS 入口 | 167128，与各格式 summary 严格相等 |
| 开启侧真实 retained producer 入口 | 330，与 tag4 cold 数严格相等 |
| tag4 warm hits | 498 |
| CSR | 两次 API 返回均 FCSR=23、VCSR=2、VSTART=0，两侧相同 |
| 模拟 QBS 命令 | 0 |

观测 ELF 为原已验收对象/静态库加标量观测 wrapper 重链接，原始重链接 ELF
先核对与交付二进制相同；观测 wrapper 不替换数值 producer。
QEMU TB 入口不是指令退休证据，取消的 TB 单独核对并剔除。
没有重跑模型，也不将 QEMU 时间视为硬件性能。

### SoC 队列

`enablement_soc_build_20261111_02` 已生成全组合镜像。
`enablement_soc_campaign_20261111_01` 使用真实 scalar dispatcher、锁定依赖与
已修正的 CPU retirement overlay，执行有限七项队列：三项普通 RVV，QBS M4、
QBS M8、Resident 完整 SDK 调用，以及只关闭共享 FMA 的 Resident 对照。
七项均已完成原始自检、数值和独立协议检查，原 worker 状态为
`SOC_COMBINATION_CHECKED`。另外单独安排 FMA=0 的 QBS M4/M8，
以避免只用 Attention 对照推断投影性能。
队列首次失败即停止；编译完成与功能 PASS 是两个状态。

原 worker 在最终输出 hash 复核和构建终态等待上有静态审阅意见。
不修改运行中的 sealed 脚本；新增独立终检将重放强 checker/protocol 并核对产物。
原 worker 的状态保留，不用独立审计改写原始结果。

共享 FMA 的两个镜像使用相同 RTL/依赖字节、相同固件，只有选择宏不同。
功能固件的完整调用诊断如下；这里没有把三个功能调用视为稳态 ABBA 性能实验：

| 相同调用 | FMA=0 周期 | FMA=1 周期 | 周期增加 |
|---|---:|---:|---:|
| D128、2/1 heads、T137，Resident 请求关闭 | 41908 | 42629 | 1.72% |
| D128、2/1 heads、T137，Resident 请求开启 | 37984 | 38164 | 0.47% |
| 派生 D96、6/2 heads、T65，Resident 请求开启 | 58285 | 58813 | 0.91% |

各行只比较同一调用在两种 FMA 实现下的周期，不能跨行比较作为 Resident 的收益。
它们说明共享 FMA 存在小幅延迟代价，不支持“完全零性能损失”的表述。
之前约 31.08% 是单 lane ADDMUL 部件面积下降，不是本轮重新测得的 SoC 降幅。
保留显式 `shared_fma=0` 选择，使面积与延迟取舍可控。

`enablement_soc_qbs_pair_20261111_01/result.json` 的 M4/M8 补充对照也已完成。
四次同调用配对均通过数值、命令和协议检查，共享 FMA 使每次完整调用增加
63或64周期：M4从171793到171856、170361到170425；
M8从162520到162584、161072到161136，均小于0.04%。
结果明确记为功能通过、存在微小周期回退，不改写为严格性能不退化。

### 既有证据的准确范围

- SharedFma 与 Resident PV 已有真实 VMFPU 899 场景组合证据；
  不能表述为二者完全没有一起测过。
- 阶段3完整 Resident QK/PV SoC 已使用共享整数乘法器，但 SharedFma 和
  QBS M8 借用关闭；因此不能据此宣布所有优化全开通过。
- 历史 Wide-M 完整模型存在数值和 Top-1 差异，且旧串行 M8 有退化；
  新协作路径的局部加速不自动消除所有格式的生产者契约问题。
- 共享 FMA 将 FP16/FP32 ADDMUL 延迟统一到 5 周期。保留 SIMD 并行能力
  不等于所有依赖链的周期不变，需查看完整调用而非仅部件吞吐。

## 不得自动越过的条件

1. `NORMAL_MEMORY` 是平台对可访问内存及执行环境的承诺，不是性能开关。
2. Resident provider 必须对应实际硬件指令、OS、内存和独占所有权契约。
   测试 fixture 或固定 QEMU 提供者不能当作 VCU118 的部署授权。
3. F16 与量化 KV 是不同路径；不能重解释数据以提高快路径计数。
4. 短 Prefill 与 Decode head 分组不是同一种维度；不改变计算语义来扩大准入。
5. 算子开始计算后的错误不得通过重新执行另一条路径伪装成成功回退。
6. 不启用模拟执行来证明硬件收益，不默认开启高开销逐命令诊断。

## 暂不全局开启的具体原因

| 项目 | 不能直接全开的原因 | 保留方式 |
|---|---|---|
| 全局 WIDE_M | 共享 M8 ABI 不能区分有收益的协作与较慢的串行实现；不同权重格式并非都使用协作路径。row-wise Q8_K 与已接受 M4 fused-bias 在边界值可分别得到 10 与 11，旧模型也出现过 Top-1 差异 | 保留显式、受限的 M8 能力；不把此差异称为乘法器功能错误 |
| Resident 的任意平台默认 | 普通 ELF 没有对应 OS/镜像/内存/独占执行契约；测试 provider 不能授权板卡 | 编译支持与运行请求分离；匹配可信 provider 后按形状选择 |
| 阶段4 features-v2 的 GGML 默认 | 当前适配层使用 plain-score v1；单独翻编译宏不等于绑定新特征字段和 provider 契约，且已测小形状退化 | 保留已验证的显式 SDK 入口与旧 GGML 特征路径 |
| 旧 GROUPED_PV 与 Register-PV 同时启用 | 实际入口明确将二者同时为 1 判为回退 | 默认请求 Register-PV；旧路径作为替代，不叠加 |
| 任意 K 的 retained-maxima 默认 | 当前完整调用正收益来自 K1536；其他 K 的功能范围不等于各图上的性能收益 | 先限制已测 K1536 缓存图，不改变不适用调用 |
| NORMAL_MEMORY、仿真执行、详细诊断 | 分别是平台承诺、非硬件实现和额外测量开销，不属于可叠加的性能优化 | 不隐式授权，不用仿真执行冒充硬件，不默认高开销诊断 |

### 额外开关的复核

- `AKV_PAIR_HEADS` 已由 native-auto 在合适的 F16 Decode 条件下选择，
  不能按旧文档称其全部关闭。
- `QBS_SEGMENT_K_BLOCKS` 是权重布局/切分选择，不是 QBACC。给短 K 强制分段会
  改变 partial-sum 边界并排除某些复用；不为所有模型设置同一个小段长。
- `qbs_vrf_continuation`/QBACC 的已有真实长 K 完整调用为 164625 对 179253 周期，
  慢约 8.89%。保持关闭的原因是 VRF seed/commit、额外命令与 replay 的净成本。
- `AKV_REFILL_OVERLAP` 的已有完整调用对照仍慢约 1.55%，且当前 Resident 准入
  不接受 refill overlap，保留关闭；不能把局部重叠活动直接算作完整调用收益。
- `AKV_PORTABLE` 的 plain 场景有约 2.5% 控制开销，而 Refact 的真实 ALiBi/MQA32
  场景有正收益。本轮只对原路径不支持的特性/大 GQA 设计条件默认，普通 plain
  路径不强制切换；当前版本仍不开放 D256。
- `AKV_QK_PANEL4` 已完成当前全组合镜像上的两个版本测试。
  历史显式开关固件周期减少 4.78%；新 SDK 自动选择固件周期减少 6.47%。
  二者分别比较各自同一 ELF 内的 OFF/ON，不能把两个不同 ELF 直接比较。
  数值、CSR、guards、缺能力回退及独立协议检查均通过。
  `enablement_panel4_audit_20261111_02/result.json` 独立复核通过；
  新固件 ABBA 为 107994、100711、100798、107444 周期，
  第五次缺能力回退为 107595 周期，不计入 ABBA。
  SDK native-auto 仅在 F16、D128、6 行 query、KV 长度至少 128 且原有能力检查
  全部成立时默认选择。显式 0/非法值关闭；非 auto 入口保持显式选择。
  该长度门限是保守策略，不承诺每个长度都有相同收益。

## 实际使用方法

面积优化不是 llama.cpp 的运行环境变量。直接实现的共享逻辑保留在 RTL 中；
可选共享算术和 Resident/借用接口需要重新生成匹配镜像。例如仅检查全开配置：

```sh
make -C hardware config-check optimization_profile=candidate_all
```

该配置选择 `shared_simd_mul=1 shared_fma=1 akv_resident=1 qbs_lane_mul=1`，
并选择 QBS/AKV-v2；目前集成几何为四 lane、VLEN1024。
同样的 `optimization_profile=candidate_all` 参数可用于后续 VCS/DC 目标。
本轮不启动综合；配置名称中的 candidate 也不代表板卡已验收。
若更看重依赖链延迟，可显式追加 `shared_fma=0`，其他选择不受影响。

软件使用 llama.cpp 的 `cmake/ara-optimized.cmake`，并指向本轮审核后的冻结 SDK。
QBS、AKV、上下文和 M4 复用等请求自动开启；类型、布局、形状和平台准入仍有效。
`GGML_RISCV_ACCEL_AUTO=0` 关闭隐式默认，单项显式 0 优先于默认请求。
PANEL4 的 SDK 自动选择由 `AKV_QK_PANEL4=0` 独立关闭。
普通 ELF 不获得 Resident 平台授权，也不自动声明量化 KV 的 NORMAL_MEMORY。

“尽量全开”的结果是：有可靠条件选择的优化尽量自动使用，而不是绕开边界检查。
没有收益或契约不成立的路径继续保留显式实验入口，不强制替换正常实现。

## 最终构建与模型验收

当前完整程序已统一包含 M4 preflight、Portable 条件选择和 PANEL4 SDK 更新。
`enablement_unified_build_20261111_01/delivery.json` 的独立审计通过，
三个静态 RISC-V ELF 位于该目录的 `build/bin/`。
首次 worker 在编译成功后误用 `bin/` 路径执行 readelf；保留原 FAIL，
独立审计检查实际产物、8937 项编译输入和339项交付产物，不重复编译。
`llama-simple` SHA256 为
`c44e8090df973dd5ec2e21527b19e435dbdef17cdde2ff6fc5dca7a25006c49e`。
模型观测 ELF 从这些相同对象和静态库重链接；原样重链接先核对与完整程序哈希相同，
再加入标量观测 wrapper。观测 ELF 与未观测程序分别记录身份，不把两个文件混为一谈。

九项 SoC 独立终检已通过，状态为 `INDEPENDENT_SOC_TERMINAL_AUDIT_PASS`，
核对4735项输入及全部镜像身份，重放数值/协议检查；原 worker 报告不变。
Refact 模型的 ALiBi H32/max_bias8 系数已在目标 GNU/glibc
环境逐位核对，32 个系数及 FCSR 均与 GGML 计算匹配，不因静态怀疑改动算术。
不再扩大本轮测试范围，不启动综合或新板测。

Refact 检查 `enablement_portable_model_refact_20261111_01` 已结束。
两侧同一观测 ELF、相同输入，仅 Portable 显式关闭/默认选择不同，均正常退出。
原 worker 保留 FAIL，原因是错误要求整个 `llama_decode` 调用前后 vcsr 相同。
实际两侧的完整 CSR 记录一致：Prefill时 vcsr 从0到2，Decode时从2到2；
FCSR始终23、VSTART始终0。

冻结的 `quants.c` 第184/185行采用指定RNE的 `vnclip` intrinsic；
观测 ELF 的 `quantize_row_q8_K` 在地址 `0x29a6a2` 含 `csrwi vxrm,1`。
这是已有GGML量化代码的行为，不是本轮新增Portable路径导致的两侧差异。
[RISC-V psABI](https://riscv-non-isa.github.io/riscv-elf-psabi-doc/#_vector_register_convention)
不要求vxrm/vxsat跨函数保存；SDK局部更强的保存约定不能错误扩大为完整模型调用的约定。

`portable_model_audit_v2.py` 绑定原始日志和checker的SHA，仅为这两条精确的
Prefill记录修正上述整调用比较；其余原checker的数值、原生计数、双侧CSR一致、
FRM、sticky FFLAGS和VSTART检查不变。16项新旧负例通过，独立审阅通过。
未修改原日志、原FAIL、RTL、QEMU或模型程序，未重跑模型。
独立结果 `enablement_portable_model_audit_20261111_01/result.json` 为
`PORTABLE_REFACT_WHOLE_CALL_ABI_AUDIT_PASS`：

| 检查 | 结果 |
|---|---|
| 比较完整logits | 98432个FP32值，均有限 |
| Prefill | 49216个值逐位相同 |
| Decode | KL=0.00552781，余弦=0.999999647，最大绝对差=1.233658，top5重合率=1 |
| 两步greedy token | 322、1932，两侧相同；生成文本为`The answer is the first` |
| 每侧原生QBS入口 | 38148，Q4_K/Q6_K工作量相同，模拟命令为0 |
| Portable实际执行 | 32个Decode算子、128个group，与128次原生features SDK入口严格匹配 |
| 未加速的Prefill | 两侧均保留32次feature fallback，不冒充加速命中 |

Decode并非逐位一致；以上只满足事先定义的短功能对照门槛
（KL不高于0.02、余弦不低于0.98、top5重合率不低于0.8，并要求token一致），
不能表述为广泛模型精度无损或模型级性能收益。

版本清单为 `software/llama/integration_manifest_20261111.json`。
本轮有限测试与逐项处置已完成，无待运行任务。
有条件默认和不能开启的原因分别列在前文；不是任意模型、形状、平台无条件全开。
这也不是完整ISA重新signoff或新FPGA验收；未提交、推送或替换已交付位流。
