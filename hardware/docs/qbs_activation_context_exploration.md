# QBS 显式 Activation Context 复用

## 1. 解决的问题

QBS 已经能在一条 `qbexec` 内把一个量化 activation block 复用于最多 32 个输出行，
但大矩阵会被软件拆成多条 output-tile 命令。旧路径的每条命令都把同一个 Q8_K 地址
重新提交给 VLSU，因此相同 activation 会随每个 tile 重读一次。

Qwen2.5-1.5B-Instruct Q4_K_M Layer 0 Decode capture 中，`attn_q` 的逻辑矩阵为
`M=1, N=1536, K=1536`。QBS 按 `N=32` 拆成 48 条命令，而一份 Q8_K activation
只有 6 个 block、共 1752 B。旧实测为：

| 指标 | 旧路径 |
| --- | ---: |
| QBS 命令数 | 48 |
| activation 逻辑读取量 | 84096 B |
| 唯一 activation 数据 | 1752 B |
| 重复读取量 | 82344 B |

`84096 = 48 x 1752`。根因不是 AXI burst 拆分或 cache miss，而是命令边界丢失了
“后续 output tile 仍消费同一 activation”的软件语义。

Q/K/V projection 还共享同一个 Attention RMSNorm 输出，gate/up projection 共享同一个
FFN RMSNorm 输出。当前实现先解决**单个矩阵内部多个 output tile 的重复 Q8_K 读取**；
跨 GGML operator 的 F32-to-Q8 动态量化复用仍属于后续工作。

## 2. 为什么不能按地址隐式命中

仅比较 `activation_base/profile/shape` 会破坏内存语义。软件可能在两条命令间原地更新
同一地址，硬件也无法观察所有标量 store、DMA 或未来一致性代理。地址相同不能证明数据
对象和生命周期相同。

因此复用采用显式软件承诺：调用者分配 token，首条命令建立快照，后续命令只在 token
和完整元数据严格匹配时读取快照。普通 `qbs_execute()` 始终生成 `DIRECT`，原有程序不会
因为存在 context 硬件而隐式改变行为。

## 3. ABI v2 契约

描述符携带 `activation_access`、`context_id` 和 `context_generation`。四种访问模式为：

- `DIRECT`：从 activation 地址读取并执行，不读取或修改 context。
- `FILL`：从内存读取并执行，同时暂存 activation；整条命令成功提交后 context 才有效。
- `REUSE`：不创建 activation AXI range，从 context 重放 activation 并执行。
- `RELEASE`：与 `REUSE` 相同地完成本条计算，成功提交后再使 context 失效。

`REUSE/RELEASE` 的严格匹配条件为：

```text
context.valid
&& context_id == saved.context_id
&& generation == saved.generation
&& activation_profile == saved.activation_profile
&& activation_layout == saved.activation_layout
&& M == saved.M
&& K_blocks == saved.K_blocks
```

任何一项不满足都在发出权重、activation 或结果访存前产生 validation fault。硬件不会
静默改走 `DIRECT`，因为静默回退会掩盖软件生命周期错误。

当前 capability 明确报告：

- context 数量：1，合法 `context_id` 为 0；
- generation：8 bit，由调用者管理；
- activation：仅 Q8_K row-major；
- shape：`M=1`，`K_blocks<=16`，即 `K<=4096`；
- 计划必须包含至少两个 output tile，且不能 split-K 或 gather activation。

这些是当前实现边界，不是永久 ISA 限制。unsupported plan 在第一条命令发出前返回
`QBS_STATUS_CONTEXT_UNSUPPORTED`，adapter 应继续使用 `qbs_execute()` 或普通 RVV 路径。

## 4. 软件运行时

公共 API 增加：

```c
typedef struct {
  uint8_t context_id;
  uint8_t generation;
} qbs_activation_context_token_t;

typedef struct {
  uint8_t use_activation_context;
  qbs_activation_context_token_t activation_context;
} qbs_execution_options_t;
```

`qbs_execute_with_options()` 在一个已验证 plan 内自动生成：

```text
第一个 output tile       FILL(id, generation)
中间 output tile         REUSE(id, generation)
最后一个 output tile     RELEASE(id, generation)
```

`qbs_execute()` 保持 ABI 兼容并等价于 options 为 `NULL`，所有命令均为 `DIRECT`。
runtime 不隐藏 token 分配器：调用者必须保证 generation 对应同一逻辑 activation，并保证
同一个单 context 的 `FILL...RELEASE` 序列不被其他线程插入。GGML adapter 因此对整个序列
加 mutex，并在每次新执行时推进 generation；环境变量
`GGML_RISCV_QBS_ACTIVATION_CONTEXT=0` 可退回 DIRECT。

## 5. RTL 数据与控制路径

### 5.1 建立 context

`qbs_engine` 在 descriptor validation 阶段处理 `FILL`：

1. 先清除旧 context valid，并锁存 token、profile、layout、M 和 K-block 数。
2. 正常 read engine 继续产生 activation AXI range；返回 beat 同时送往 compute 路径和
   `qbs_activation_context`。
3. context 按 `(k_block, byte_offset)` 保存数据，并独立记录每个 block 是否完整返回。
4. 只有计算和结果 commit 全部成功，且所有声明的 block 均完整，metadata 与 valid 才原子提交。
5. descriptor validation 失败发生在 `fill_begin` 之前，因此保留原有 context；合法
   `FILL` 已开始后若再发生 MMU、PMA、AXI 或 compute fault，`fill_abort` 丢弃暂存状态，
   且旧 context 已失效。

因此任何失败路径都不会留下半个可观察 context，同时 descriptor 本身无效的命令不会破坏
仍然有效的旧 context。

### 5.2 复用 context

`REUSE/RELEASE` 先进行严格 lookup。匹配后，range builder 不创建 activation AXI ranges，
只保留 descriptor、weight 和结果相关访问。context SRAM 以每 block 19 个 beat 的形式重放
292 B Q8_K 数据：前 18 个 beat 为 16 B，最后一个为 4 B。重放数据进入原有 activation
block adapter，后续 profile decoder、整数 dot、FP accumulation 和 atomic commit 均不改变。

这一设计刻意复用原 compute path，而不是增加第二套数值逻辑。`RELEASE` 只有在本条命令
成功 commit 后失效；若本条命令 fault，context 不会因失败操作提前释放。

### 5.3 SRAM 组织

最大逻辑 payload 为：

```text
16 blocks x 292 B = 4672 B = 37376 bit
```

紧凑数据按 128-bit row 存储，相邻偶数/奇数 row 分到两个 bank。Q8_K block 为 292 B，
其边界不会总与 16 B row 对齐；双 bank 使一个 4-byte 对齐、最多 16 B 的 fill/replay beat
即使跨 row，也能在同一周期访问两个 row。

写入 steering 以四个 32-bit word 为单位，而不是展开成 16 条逐 byte 地址路径；这是由
read engine 的 strobe 契约保证的。generic 仿真使用两个 `146x128` `tc_sram`。TSMC SRAM
实现使用四个现有 `64x256` macro：每个 parity bank 使用两个 macro，每个 256-bit word
承载两个逻辑 128-bit row。物理容量为 65536 bit（8 KiB），逻辑 payload 仍为 37376 bit；
容量差来自可用 macro 粒度，不是额外可寻址 context。

## 6. 正确性与故障规则

以下不变量由定向测试和 RTL assertion 覆盖：

- `DIRECT` 不依赖 context 状态。
- 未完成的 block 不能 commit。
- `FILL` 与 replay 不同时访问单端口 bank。
- context ID、generation、profile、layout、M 或 K 不匹配均产生对应 validation fault。
- stale generation 不会读取 SRAM，也不会产生 activation/weight/output AXI 请求。
- descriptor-invalid `FILL` 保留旧 context；已接受的 `FILL` 若随后 fault，则 context 无效；
  成功 `RELEASE` 后旧 token 无效。
- reset 清空 valid 和 in-progress 状态。
- 结果仍通过原有 shadow/atomic commit 路径，故障时目的向量组保持不变。

## 7. 严格计数器

| 计数器 | 严格含义 |
| --- | --- |
| `context_fill_count` | 成功 commit 的 FILL 命令数 |
| `context_reuse_count` | 通过严格 lookup 并开始执行的 REUSE/RELEASE 命令数 |
| `context_reuse_block_count` | 完整从 context 重放给 compute 的 Q8_K block 数 |
| `context_read_bytes` | context SRAM 到 block adapter 的有效 payload 字节数 |
| `activation_axi_bytes_saved` | 严格 lookup 通过后，按 shape 本应读取但未创建 AXI range 的字节数；后续 weight/compute fault 不撤销该活动计数 |
| `context_replay_cycles` | context 正在输出有效 replay beat 的周期数 |
| `context_replay_compute_overlap_cycles` | `context_replay_busy && compute_phase_compute` 同时成立的周期数 |
| `context_validation_fault_count` | token 或 metadata mismatch 引起的 validation fault 数 |

`activation_axi_bytes_saved` 表示外部流量收益，`context_replay_cycles` 表示内部搬运活动，
二者不能合并为含义模糊的“hit rate”。对于两 tile FILL->REUSE 测试，命令复用率为
`1/2=50%`；第二条命令的 activation 覆盖率为 100%，整个两命令序列避免了 50% 的
activation AXI payload。

## 8. 真实 Qwen2.5 两 tile 证据

定向 workload 使用真实 Qwen2.5-1.5B Q4_K_M Layer 0 `decode_attn_q` 数据，shape 为
`M=1, K=1536`，取连续两个 `N=32` output tile。DIRECT/DIRECT 与 FILL/REUSE 使用同一
权重、activation 和 golden output。

| 指标 | DIRECT/DIRECT | FILL/REUSE | 变化 |
| --- | ---: | ---: | ---: |
| 输出 mismatch | 0 | 0 | 逐位一致 |
| checksum | `0x71b5ea8a1468eb92` | `0x71b5ea8a1468eb92` | 相同 |
| activation AXI payload | 3504 B | 1752 B | -50.0% |
| 总 AXI payload | 29416 B | 27664 B | -1752 B |
| activation read ranges | 12 | 6 | -6 |
| 第二条命令周期 | 2308 | 2188 | -5.20% |
| 两条 matmul 周期 | 4853 | 4735 | -2.43% |
| task timed cycles | 16462 | 16358 | -0.63% |

task 级收益被启动、数据初始化和校验代码稀释；机制判断应以第二条命令、matmul 周期和
AXI payload 为主。该测试还要求第二条命令的 range 列表中不存在 activation role，不能只
依据计数器恰好为零推断“未读取”。

## 9. 综合风险

独立 DC 使用 TSMC 28 nm TT 0.9 V 25 C、1.0 ns clock、0.15 ns uncertainty，并显式链接
四个 `TS1N28HPCPUHDSVTB64X256M1SWBSO` macro。检查重点为 macro 是否保留、外围逻辑面积
和 setup 可实现性；它不是 SoC P&R 或 hold closure。

初始逐 byte steering 与最终逐 32-bit word steering 的结果为：

| 项目 | 逐 byte | 最终逐 word | 变化 |
| --- | ---: | ---: | ---: |
| SRAM macro | 4 | 4 | 不变 |
| macro area | 28332.29 um^2 | 28332.29 um^2 | 不变 |
| combinational area | 6388.03 um^2 | 2697.74 um^2 | -57.8% |
| sequential area | 425.71 um^2 | 423.19 um^2 | -0.6% |
| total cell area | 35146.03 um^2 | 31453.23 um^2 | -10.5% |
| leaf cell count | 8902 | 4071 | -54.3% |
| logic levels | 22 | 20 | -2 |
| setup WNS/TNS | 0.00/0.00 ns | 0.00/0.00 ns | 均无违例 |
| critical path | offset 到 SRAM byte enable | replay block 到 SRAM data | 路径转移 |

逐 word steering 保持每周期一个 128-bit beat 的 fill/replay 带宽，但把四个 word 作为最小地址
单元，消除了 16 份重复 byte 地址算术。最终关键路径 data arrival 为 0.79 ns、required 为
0.80 ns；报告按两位小数得到 0.00 ns slack，且仍有两条按 1000 fanout 估算的网络。因此该模块
在 standalone 模型下达到 1 GHz，但不能据此宣称拥有充分的 SoC 布线余量。standalone hold
违例来自理想时钟和未做 CTS/hold fixing，不能作为最终 hold 结论。

## 10. 复现

软件、reference、RTL 与 QEMU contract：

```bash
make -C software/qbs clean check
make -C verification/qbs clean check
make -C verification/qbs rtl-context-check
make -C verification/qbs rtl-context-macro-check
make -C verification/qbs rtl-descriptor-check
make -C verification/qbs rtl-engine-check
QBS_QEMU=/path/to/qemu-system-riscv64 \
  make -C verification/qbs qemu-contract-check
```

真实两 tile 顶层仿真完成后，严格检查日志：

```bash
make -C verification/qbs activation-context-evidence-check \
  ACTIVATION_CONTEXT_EVIDENCE=hardware/qbs_activation_context_evidence
```

该 checker 同时验证 checksum、命令模式、fault flag、range role、实际 AXI payload、
context counters 和周期，不通过时不会只生成一份看似合理的汇总。

独立 SRAM-mapped DC 检查必须在 EDA 容器内运行：

```bash
bash verification/qbs/synthesis/run_activation_context_dc.sh
```

## 11. 当前边界与下一阶段

当前机制只消除**同一次 M1 Q8_K matmul 的 N tiles 之间**的 activation 重读。它没有：

- 跨 Q/K/V 或 gate/up operator 复用动态量化结果；
- 覆盖 M2-M4、Q8_0 或 split-K；
- 消除 context SRAM replay 本身；
- 证明完整 Qwen token/s、P&R、功耗或多 context 调度。

下一阶段若扩展跨 operator 复用，token 必须绑定 GGML tensor identity、shape、量化 profile
和 graph execution epoch，不能只绑定 data pointer。只有真实模型 trace 证明量化或 replay
成为新的关键路径后，才应扩展 context 数量或把量化流水化。
