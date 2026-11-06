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

正式任务已由 `ara-e2e-decode-native-20261106-01.service` 直接持有，已确认
实际 `simv` 子进程和递增的指令握手记录。不是短启动器退出后留下的孤儿任务。
模拟器及独立审计完成前，本节不填入周期结论。进度与最终结果分别查看：

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
