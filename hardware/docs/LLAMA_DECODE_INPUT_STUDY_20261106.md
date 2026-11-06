# 下一项结构优化前的真实 Decode 输入与测量约定

## 1. 为什么不沿用 Prefill 的一行

当前宽点积候选已在全 N QKV 和真实 FFN 长 K 上取得执行收益，但 Decode 的
M1 dot 步长没有变化。完整模型工作量账目指出，Decode 量化投影中 FFN 和
词表输出层分别占约 61.44% 和 18.09% 的 MAC；需要真实 Decode 的输入和
已有快速路径作为对照，不能用 Prefill 行、全部 DIRECT 的弱基线，或不同
模型的较早切片替代。

## 2. 当前捕获怎样进行

`run_decode_capture.py` 复用已通过完整模型检查的静态库，不重建 llama.cpp。
先执行真实 Qwen3-1.7B Q4_K_M 的 40-token Prefill，检查返回码、有限 logits
和已核验的首个贪心 token 22406。随后以该 token、位置 40、同一 Q8_0 K/V
cache 进入第一个 Decode，捕获以下 F32 输入：

| 源张量 | 行数 | K | 后续消费者 |
| --- | ---: | ---: | --- |
| `attn_norm-0` | 1 | 2048 | 第一层 Q/K/V |
| `ffn_norm-0` | 1 | 2048 | 第一层 gate/up |
| `ffn_swiglu-0` | 1 | 6144 | 第一层 down |
| `result_norm` | 1 | 2048 | 最终词表输出投影 |

这是完整执行 Prefill 后真实产生的 Decode 激活，不重复或拼接输入。前三个
捕获后继续执行后续层，最终在 Decode 词表投影之前停止；它没有完成本次
Decode 的最终 logits 或生成第二个 token。因此验收状态明确区分完整 Prefill
已执行与完整 Decode 尚未执行，也不使用 QEMU 时间作为性能数据。

回调在后端同步后读取真实张量，检查形状、步长、有限值及捕获次序；第一层
Decode 输入还必须不同于旧 Prefill 首行。回调可能切分调度图，因此其中观察
的 context 统计用于确认路径和准备数据，不冒充无观测模型的覆盖率或周期。

## 3. 长运行之前的准入与结束后的验收

先核对模型盘、host GGUF、源码、编译器、静态库和所有需要的原始权重，缺少
词表 tensor 或出现未知格式时在 Prefill 开始前拒绝。原始权重保留 N128 前缀，
完整 K 和原始 N 进入清单：Q/K/V、gate/up/down，以及词表输出权重。

为减少日志开销，Prefill 关闭 QBS 逐条日志；在完整图调用返回后、Decode
开始前再开启两个原有 trace 门控。配置不在任何阻塞执行 context 内变化。
检查器要求四个捕获边界前分别完成 0/4/6/196 个投影调用和 0/192/576/17920
条 native 命令，并逐调用核对 K、N、profile、M1 和实际命令数量。

同时要求 28 次 grouped Prefill、28 次 Decode Attention 及输出驻留路径实际
成功，并出现合法 activation-context 命令。K6144 超出当前 context 容量，
必须保留 DIRECT，不强行提高能力或放宽 descriptor 检查。

运行目录：验证树 `verification/out/e2e_decode_capture_20261106_01/`。捕获状态
只有在上述检查全部完成后才为 `REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED`。
未取得这个结果前，不把准备文件或运行中的 QEMU 当作已接受数据。

本批现已完成，独立复核状态为 `REAL_QWEN3_DECODE_CAPTURE_REAUDITED`，目录为
`verification/out/e2e_decode_capture_audit_20261106_01/`。收集器重新检查 231 项
直接输入，重读原日志、四个 F32 payload，并从已核验原始 GGUF 再次提取全部
七组权重前缀；native QEMU 构建身份也经过独立复核。捕获的 Decode 输入确实
不同于 Prefill 首行。

捕获范围内实际有 DIRECT=1792、FILL=84、REUSE=15960、RELEASE=84 条命令。
DIRECT 对应超出 context 容量的长 K 路径；已有的 QKV/gate-up 共享及单操作内
复用已在运行。以上只覆盖词表投影之前的工作，不作为完整模型的时间比例或
无观测运行的精确 context 覆盖率。

## 4. 下一轮硬件测量要保留的成本

用真实输入建立 M1 SDK 调用，保留 Q/K/V 与 gate/up 的已有 context 生命周期
和长 K 的安全 DIRECT fallback。比较相同输入、相同工作量和数值；N 采样必须
明确，不将其直接外推成全模型时间。按完整调用记录准备、admission、执行和
命令间开销，再用 AR/R、严格等待、FP/result 反压及排他阶段计数解释瓶颈。

现有 128-bit reader 与量化权重块的服务下界表明，增加 M1 乘法器不能自动
解决数据供给。应先确认实际传输效率和空隙，再选择更好的请求推进、缓冲、
数据驻留或软件批量提交，允许合理面积投入，但不先假定某个队列一定有收益。

## 5. 软件对照还有一个必须固化的差异

本次已核验模型库编译的 `arch/riscv/qbs.cpp` 哈希仍为 `43a86cfd...bf6e`，
尚未采用已重建、做过 host 检查的 `trace-context.patch` 后像 `9aa982ff...8f9`。
后者把 trace 环境查询从每条 native 命令移到阻塞 context 创建时读取一次。
本批 C SDK 计时不执行该 GGML 层查询，所以已测 QKV/FFN 的硬件时间比不受
此差异影响；但它仍是模型级软件基线必须处理的开销，不能遗漏。

后续在独立构建输入中只重建这一对象并核对其余库成员，验证调用之间更新
配置的行为、native 序列、结果及 CSR 后再固化新基线。不能覆盖当前脏 llama
工作区，也不能修改正在被 Decode 捕获消费的库或源码。

该独立库现已完成构建和 archive 审核，工具为
`build_trace_context_library.py`；输入仍是已接受的实际模型静态库及原编译
命令，非另一次全库 CMake 编译。在唯一验证树
`verification/out/e2e_trace_context_library_20261106_01/attempt-02/` 中：

- 新库只替换一个同名 `qbs.cpp.o`，32 个成员的名称和顺序不变，其余 31 个
  成员逐字节相同；不能用 `ar q` 追加一个新名字而留下旧实现。
- 全局定义的 919 个名字、923 条定义保持一致，原库 SHA 不变。
- 原封存源码的 preimage 和注册 patch 的 postimage 均严格核验。
- 333 项 pins、实际编译依赖和全部产物重新通过独立复核；12 项工具测试通过。

状态为 `TRACE_CONTEXT_LIBRARY_BUILT_ARCHIVE_VERIFIED`，不是模型数值验收。
尚未把新库接入现用模型或计作性能提升，下一次模型功能对照还需检查 native
命令、结果、CSR 和两次 context 之间的 trace 配置更新。第一次 Python 3.9
兼容性失败保留在同一输出树，不覆盖其记录。

## 6. 已建立的真实 M1 SDK 基线

`build_decode_native.py` 已在独立目录完成编译和内存准入，状态为
`REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED`。程序为单次 reset 后的 M1/N128
七个投影：Q、V、K、gate、up、down、vocabulary，顺序与第一层实际图调度相符。
所有 K 保持完整，down 为 K6144，其余为 K2048。输出共 896 个 FP32，28 条
native 命令，2359296 个有效 MAC pair；这些前缀不代表完整层或完整词表。

### 6.1 不弱化软件和硬件基线

四个真实输入分别只准备一次。量化直接编译封存 GGML 的
`arch/riscv/quants.c::quantize_row_q8_K` 及 `q8_K-decode-sums.h`，不使用
M4 量化器或计时内的标量替代。原库的其他 8 个通用 SDK/startup 对象复用，
只新增 caller、原生产量化器和真实数据三个对象。

| 消费者 | 使用的输入 | 调用 scope | N128 的四条命令 |
| --- | --- | --- | --- |
| Q | `attn_norm-0` | FILL_KEEP | FILL, REUSE, REUSE, REUSE |
| V | 同一份量化输入 | REUSE_KEEP | REUSE, REUSE, REUSE, REUSE |
| K | 同一份量化输入 | REUSE_RELEASE | REUSE, REUSE, REUSE, RELEASE |
| gate | `ffn_norm-0` | FILL_KEEP | FILL, REUSE, REUSE, REUSE |
| up | 同一份量化输入 | REUSE_RELEASE | REUSE, REUSE, REUSE, RELEASE |
| down | `ffn_swiglu-0` | DIRECT | DIRECT 四次 |
| vocabulary | `result_norm` | OPERATION | FILL, REUSE, REUSE, RELEASE |

三个独立激活生命周期使用不同 generation。正常执行预期有 DIRECT=4、
FILL=3、REUSE=18、RELEASE=3；RELEASE 也消费片上激活，因此硬件的
`context_reuse_count` 合计应为 21，而非 18。K6144 的 7008-byte 激活超过
4672-byte context，仍保留普通 DIRECT，不改变能力声明。

### 6.2 校验和计数语义

独立 host oracle 比较原 row-major 与 R4 权重布局的全部输出及异常标志；
ELF 检查全部量化字节、896 个输出、前后 canary、累计 fflags、frm、vcsr
及 vstart。M1 生产量化器使用显式 RNE narrowing，会将初始 VCSR=5 改为
3；这是原有软件行为，不套用 M4 测试中的 VCSR 不变假设。后续 QBS 调用
必须保持量化后的 VCSR=3 和 vstart=0。

四组有限真实输入共 48 块没有正负等幅最大值冲突，可与独立 scalar oracle
逐字节比较。该批通过也不能证明两个量化器对任意 tie 输入全域等价。

每次调用分别记录 preparation、admission 和 execution，总 region 包含调用
间控制；校验和打印在区间外。除排他的 phase 账目外，其余等待/忙计数不
相加成 stall breakdown。尤其注意：

- `activation_bytes` 是 compute adapter 接收字节，包含 SRAM context 回放。
- `context_read_bytes` 是实际 context 回放数据；FILL 本身不算 REUSE。
- `activation_axi_bytes_saved` 是已匹配 context 避免的逻辑激活读取字节。
- 本测试每条命令 reader payload 为 16-byte descriptor 加权重和实际激活
  读取。以 `payload_bytes - weight_bytes - 16` 核对实际激活 AXI payload，
  再与 `activation_bytes - activation_axi_bytes_saved` 对账。
- R beat 包含总线传输；不等于仅权重数据，也不代表板上 DDR 带宽。

### 6.3 可复现运行与自动收集

构建目录位于唯一验证树：
`verification/out/e2e_decode_native_build_20261106_02/`。第一次构建因新增
生产量化器使用的工具链 `float.h` 尚未纳入依赖清单而拒绝；失败目录保留，
第二次显式准入并固定该工具链头文件，没有改变量化源码或 RTL。

`run_decode_native.py` 已完成不启动模拟器的 preflight。正式运行由
`decode_native_campaign.py` 依次执行 VCS、独立协议检查和
`collect_decode_native.py`，均使用全新目录并校验源码、参考数据和镜像身份。
只有最终 `REAL_QWEN3_DECODE_SDK_BASELINE_REAUDITED` 才算接受性能数据；
编译、preflight 和模拟器启动都不是 PASS。本批没有新 RTL 或全模型性能结论。

正式任务由 `ara-e2e-decode-native-20261106-01.service` 直接持有，现已成功
完成 VCS、独立协议检查及重放审计，服务 exit=0，未遗留模拟器。独立结果为
`REAL_QWEN3_DECODE_SDK_BASELINE_REAUDITED`；实测值见第 8 节。状态与结果查看：

```bash
systemctl --user status ara-e2e-decode-native-20261106-01.service --no-pager
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_decode_native_vcs_20261106_01/status.json
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_decode_native_campaign_20261106_01/result.json
```

运行目录为 `verification/out/e2e_decode_native_vcs_20261106_01/`，最终独立
审计目录为 `verification/out/e2e_decode_native_audit_20261106_01/`。本批先在
现有基线镜像测 M1，不因 M4 的宽点积收益额外跑一遍未改变的 M1 硬件。

## 7. 原库与 trace-context 候选的模型级验收

静态库成员一致只能证明修改范围，不能替代实际数值验证。因此增加独立的
`trace_context_model_campaign.py`：在一个 QEMU guest 中分别 exec 原库和
候选库链接的程序，避免全局环境缓存跨版本遗留；guest 内的比较程序读取
两个结果文件，逐字节比较全部 logits、token 和 CSR，不用最终 token 相同
代替数值一致。

两侧共用同一个 `model.o` 和同一组其他静态库，只替换 `libggml-cpu.a`。
测试由已接受完整模型 fixture 机械生成，保持原 prompt、模型、线程、数值
和运行时选择；仅选择已有 output-tile Attention，减少一个重复 Decode
step，并开启已有 aggregate trace，保持逐命令 lifetime 日志关闭。

| 项目 | 配置或检查 |
| --- | --- |
| 模型 | 实际 Qwen3-1.7B Q4_K_M，28 层，151936 词表 |
| 输入 | 同一 40-token prompt；每种 KV 各执行完整 Prefill 和一个 Decode step |
| KV | Q8_0 K / Q8_0 V；Q4_0 K / Q8_0 V |
| 数据 | 两侧各 4 份完整 logits，共 607744 个 FP32 配对；每侧结果文件 2431060 bytes |
| 调用 | 每侧 788 个量化投影调用、56 个 Prefill Attention 和 56 个 Decode Attention |
| 对照 | 新旧结果逐字节比较，token/CSR 同时匹配先前已接受控制运行的对应步骤 |

`projection-schema.json` 从原始 GGUF 的 197 个权重 tensor 导出格式与尺寸，
核对封存的 Qwen3 图及模型盘身份。检查器逐层按 Q/V/K/Wo/gate/up/down 的
真实调度次序检查每个 CALL；Prefill 的末层 FFN 与词表只请求最后一个输出，
因此是 193 GEMM + 4 GEMV，而不是将全部 197 个投影都强行视为 40 行。
Decode 则为 197 GEMV。两个 KV 配置重复相同的投影形状。

验收不只比较两个总数：按 profile 与 GEMV/GEMM 重建输入行、输出行、MAC、
M1/M4 命令数，与 native EXEC 摘要逐项对账；FILL/REUSE/RELEASE 不能超过
相应格式具备 context 资格的实际命令。Attention 的 LAYOUT、PV、输出驻留、
REGISTER 和主调用记录全部参与比较，并匹配原控制运行相应步骤；QBS tensor
coverage 记录也不静默丢弃。逐命令日志关闭，避免输出数十万条命令拖慢测试。

host C++ 测试实际编译比较程序，验证最后一个 logit 改变、CSR 不同、两边
相同 NaN、文件截断和额外字节都会拒绝；日志负例检查拒绝的具体原因，包括
两边同时错误缩小工作量、把所有调用摘要重分配到一个格式、虚增 context
计数、改变 KV 字节数等。准备阶段曾发现 LAYOUT/PV 没有 status 字段的误拒绝，
已在启动长测试之前通过正例和负例修正，未用目标仿真反复试错。

运行器和独立 collector 均核对源码、库、ELF、模型盘、native QEMU 构建来源
以及链接参数。自动完成状态为 `TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED`；
preflight 与启动都不等于验收。本项使用 QEMU 只验证完整模型功能与工作量，
不产生硬件周期、速度提升、PPA 或板卡验收结论，也不提前替换生产库。

该配对现已完成，独立 collector 给出
`TRACE_CONTEXT_QWEN3_MODEL_PAIR_REAUDITED`。两侧 607744 个完整 logits
逐位相同，token、CSR、788 个投影调用以及 Prefill/Decode 各 56 个
Attention 调用的实际工作记录均一致；复核了 35429 项输入与产物身份。
候选库只有 `qbs.cpp.o` 改变，其他 31 个 archive 成员保持原样。
精简回执位于 `verification/performance/evidence/trace_context_model_20261106_01/`。
这完成了本项完整模型功能配对，不是模型性能测量或生产库自动替换。

## 8. 真实 M1 VCS 基线已通过及下一项结构判断

VCS 和独立审计已完成，917 项输入、镜像、原始日志、独立协议及全部数据
再次核对。完整区域为 227810 cycles，其中准备 68377、admission 11610、
SDK execution 145475，剩余区域控制 2348。所有输出、量化字节、guard、
FCSR=9、VCSR=3 和 vstart=0 均通过。注意这里是七个 N128 前缀，不是连续
的完整模型图，也不是完整层/词表时间。

| 投影 | 格式 | K | SDK execution | QBS busy | R beats | strict weight wait |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Q | Q4_K | 2048 | 14944 | 12038 | 9372 | 378 |
| V | Q6_K | 2048 | 18366 | 16174 | 13572 | 4170 |
| K | Q4_K | 2048 | 13735 | 11888 | 9220 | 380 |
| gate | Q4_K | 2048 | 14204 | 12038 | 9372 | 376 |
| up | Q4_K | 2048 | 14000 | 11886 | 9220 | 378 |
| down | Q6_K | 6144 | 51686 | 49703 | 42532 | 13890 |
| vocabulary | Q6_K | 2048 | 18540 | 16325 | 13724 | 4169 |

四份生产单行量化的周期依次为 11541、11571、33842、11423；QKV 与 gate/up
没有重复准备。28 条命令共有 FILL=3、REUSE/RELEASE 命中=21，实际 context
回放及节省的逻辑 AXI 激活读取均为 49056 bytes。全部 reader payload 为
1700512 bytes，其中权重 1665024、实际激活读取 35040、descriptor 448。
107012 个 128-bit R beats 还包含对齐填充，不能将 payload 当作总线总字节。

各调用 R transfer duty 为 Q4_K 约 77.56%--77.85%、Q6_K 约
83.91%--85.57% 的 QBS busy。这里的通路确为 128 bit：封存 4-lane SoC
的宽接口是 `64*NrLanes/2`，共享 reader 沿该宽度发出 AR；不是外部已有
256-bit 通路却被 QBS 无意只用了一半。不能只改一个 QBS 宏就宣称带宽翻倍。

对这一批数据可作以下判断：

1. FP input 和 profile-result 反压均为零，没有证据支持先增加 M1 的浮点
   服务能力。当前 reader 每周期最多 16 bytes；Q6_K 在 dot 保持当前吞吐时
   已暴露明显传输服务压力。
2. 长 K down 的 13890 个严格等待周期中，12724 个周期有 R transfer，945
   个周期 R 被阻塞，192 个周期无 outstanding，29 个周期等待 R valid。
   它不是主要由漫长的外部响应空洞造成，也不能只靠增加 outstanding 数
   承诺很大收益。R transfer 来自共享 reader，不等价于逐周期权重 DDR 延迟。
3. Q4_K 的严格等待仅约 busy 的 3.2%，其中主要表现为 R 被阻塞而非 R 空闲。
   后续可追 bank 所有权、payload 接纳和 tile 切换，但单独清理这一小段
   不足以解释显著端到端加速，不能只围绕这个状态反复试改。
4. SDK execution 中有 15423 cycles 不在 QBS busy 内，占 10.60%；包含提交、
   接口完成、结果存储和软件控制，不称为纯 CPU 运算或全部可删除的开销。
   真正 GGML 层的 trace/getenv 成本还需使用固化的新软件基线，不能与此 C
   SDK 区域混为同一项。
5. N128 区域的准备占比为 30.01%，完整 N 会改变摊销，尤其词表为 N151936。
   不能据此将激活量化硬件列为最高优先级。长 K context 扩容仍是候选，但
   本点激活流量远小于权重流量，须先计算整体收益再增加 SRAM。

`diagnose_decode_native.py` 独立重放上述结果，并为每个阻塞调用给出
`max(dot_issue, R_beats)` 服务下界。它不是可实现的调度，也不是相加的 stall
分解；例如 down 的 busy 与该下界之比约为 1.1686，说明在保持当前物理传输
工作和宽度时，只优化零散控制的空间有限。扩大 Decode 点积通路之前，应
同时比较内存通路投入、命令批量推进以及与已有 Prefill 吞吐扩展的收益。

精简回执位于 `verification/performance/evidence/decode_native_20261106_01/`；
原始独立审计和归因分别位于唯一验证树
`verification/out/e2e_decode_native_audit_20261106_01/`、
`verification/out/e2e_decode_native_diagnosis_20261106_01/`。

## 9. 单输入提交循环的隔离对照

本轮只针对已测得的 SDK 非 busy 成本建立小型软件候选，不将该成本全部
当成可删除的开销。生产 SDK 未改动；实验补丁位于
`software/qbs/experimental/single_input/`。它在全部原有参数、容量、
对齐和 context 校验之后，对无 split/gather/segmented view 的 M1 采用
预计算 descriptor header 与递增地址，其余计划继续走原通用迭代器。

主机差分分别编译完整原 SDK 与候选 SDK，使用独立符号命名空间核对
调用序列、真实 n、地址、stride、context 转移、错误返回与 output/workspace
字节。GCC 和 Clang+UBSan 各 24535 项通过；每侧七项原始 SDK fixture
通过。定向检查还确认了 fast helper 以及 M4/M8、gather、split、分段和
view 的 generic 路径确实执行。这证明控制流差分，不冒充真实硬件异常测试。

目标 ELF 同时保留原 SDK 与候选，在同一 SoC 上按 ABBA 顺序执行四轮
原有真实 Decode 数据，共 112 条命令、3584 个输出。保留生产量化器、
所有输出逐字节比较、canary、CSR、完整 K、context 作用域及独立协议检查。
冷启动和最后一轮热基线分别保留；性能无改善也可以通过功能检查，但不能
因此升级生产 SDK。两侧均为七个 N128 前缀，不是完整模型时间。

目标汇编已确认独立 helper 的 128-byte 栈帧；其调用者为 368 bytes，
原 generic 入口为 304 bytes，因此本候选不能宣称减少栈占用。
实际减少的是候选热循环中的通用规划与 header 重建工作，净周期收益待
VCS 对照测量。首次目标构建只因调用程序清单未展开原公共对象的编译器
头文件依赖而拒绝；修正为核验两份已封存输入清单的无冲突并集后构建通过，
没有允许任意新头文件，也没有修改 RTL 或数值路径。

### 9.1 VCS 对照已完成

自动 VCS、独立协议检查与原始记录重放均完成，最终状态为
`REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_REAUDITED`，复核了 1035 项输入。
112 条命令、3584 个输出、全部准备字节、canary、CSR 与各项服务工作量
一致。下表各含两轮，不把此前单独运行的基线混入本次配对：

| 区域 | 原 SDK 两轮周期 | 候选两轮周期 | 合计周期之比 |
| --- | --- | --- | ---: |
| SDK execution | 146111 / 145929 | 141131 / 140927 | 1.03539x |
| 含准备的 SDK region | 228260 / 228118 | 223355 / 223015 | 1.02242x |
| QBS busy | 130099 / 130107 | 130111 / 130108 | 约相同 |

每轮 execution 均值从 146020 降至 141029，减少 4991 cycles；
execution 减去 QBS busy 的区间均值从 15917 降至 10919.5，减少
4997.5 cycles，busy 均值反而增加 6.5 cycles。这一账目支持收益主要
来自 busy 区间外的提交/控制成本，不是更快的点积，也不把该差额全部
解释成纯 CPU 运算。七个调用的热基线对照均保持正收益，其中长 K down
仅约 1.011x；含准备总体提速为 2.24%，不是整个模型提速。

精简回执在 `verification/performance/evidence/sdk_single_input_20261106_01/`。
生产 SDK 尚未替换。后续若集成实际 GGML 库，还需核对完整模型数值及
非 M1 路径的功能和性能；不继续围绕这条循环承诺大幅模型收益。
