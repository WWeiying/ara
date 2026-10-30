# Q8_0 解码与 PV 的寄存器融合候选

## 目标与当前状态

当前共享 RVV V 解码器先将一个 token 的 Q8_0 V 转成 F32 临时数组，随后
在线 Attention 的各个 query head 从该数组读回，执行输出 rescale 和加权
累加。V 解码已经不是旧标量版本，但仍有一次中间 F32 写回和后续读取。

本候选尝试消除这次中间传递：Q8_0 数据只解码到向量寄存器，供多个 head
的 PV 累加使用。它只改变软件指令组织，不增加 RTL 或自定义指令。目前
仅为独立叶函数，**没有安装到 GGML 后端，没有修改现有 admission、在线
Softmax、QBS QK 调度或 fallback**，也没有宣称已获得性能收益。

## 为什么不是简单逐块融合

每个 Q8_0 block 包含一个 F16 scale 和 32 个 INT8 值。直接在每个 block 后
遍历 heads，会把原本较长的 PV 向量循环分成多个 32 元素循环，增加向量
请求和控制开销，可能抵消少一次写回的收益。

本候选针对当前 VLEN=1024 配置：一个 F32 m1 寄存器恰能装 32 个元素。
将最多四个 block 解码为 m1 fragment，再组合成一个 m4 值向量。之后才
遍历 heads，对最多 128 个元素执行一次 PV 更新。D=160–256 时再处理
第二组，D=32/64/96 等尾部只读取真实 block，不读取未初始化的向量元素。

```text
原路径：Q8_0 → RVV 解码 → F32 临时数组 → 各 head 加载 → rescale/FMA
候选：  Q8_0 → m1 fragment → m4 寄存器拼接 → 各 head rescale/FMA
```

实际反汇编中，候选的 PV 主体只向输出地址执行 `vse32.v`，没有向量临时
数组写回或 whole-register 栈 spill。寄存器拼接仍可能产生寄存器移动，不能
认为拼接无成本。最初的普通 `static inline` 解码 helper 被编译器拆成函数
调用，带来重复的 ABI 保存和恢复；已将这个内部 helper 明确设为
`always_inline`，最终反汇编不再有这种解码函数调用。

## 数值与调用约束

候选保留每个输出元素的操作顺序：

1. INT8 转成 F32，并乘以该 block 的 F16 scale。
2. 只有原 rescale 分支成立时，执行 `Y = round_f32(Y * ms)`。
3. 执行一次 fused `Y = fma(decoded_V, vs, Y)`。

有限 F16 scale 与 INT8 的乘积能被 F32 精确表示，因此解码本身不引入
新的数值近似。rescale 与 FMA 没有合并成一次表达式，也不跳过零权重操作。
不同 head/元素之间的操作交错改变，但每个元素的上述顺序保持不变。

与现有 grouped PV 相同，要求 RNE、屏蔽浮点 trap、不能观察更新过程中的
中间 FFLAGS；比较的是最终结果和最终 sticky flags。调用者必须保证 Q8_0
scale 有限、输入稳定、实际分配容量足够。叶函数检查 shape、步长溢出、地址
范围和输出别名；只读输入之间允许重叠。

快速叶函数当前支持 1–8 个 heads，D=32–256 且为 32 的倍数，允许输出行
padding。寄存器 fragment 的组合依赖 VLEN=1024；其他 VLEN 在输出修改前
返回拒绝，应继续走原 RVV 路径。这里尚未完成其他 VLEN 下拒绝分支的动态
回归，不应将该候选称为已经验证的任意 VLEN 实现。

## 已完成的功能验证

源文件：`verification/akv/quantized_kv/register_pv/` 下的 `candidate.h`、
`test_candidate.c` 和 `run_reference.py`。测试使用 GNU 编译器及现有
QEMU RISC-V 模型，不需要 QBS 模型改动。

通过记录：`verification/out/register-pv-reference-20261028-02/result.json`。

| 检查 | 结果 |
|---|---|
| 生成边界组合 | 12288 项通过 |
| 真实 Qwen3 V 数据组合 | 640 项通过 |
| 无效 shape、步长、指针范围与别名 | 16 项拒绝，输出与 CSR 不变 |
| 两个对照 | 当前共享 RVV 解码器＋标量 rescale/FMA；独立位表示 F16 解码＋相同算术 |
| 输出 | 所有元素位级一致，包括整个输出分配区的 padding 和保护区 |
| FCSR / VCSR | 最终 FCSR 一致，包含预置 DZ；VCSR 保持 5 |
| 运行 | Linux guest 正常退出，源/工具/输入前后哈希一致 |

生成组合覆盖全部 1–8 heads、8 种 D、紧密/填充布局、4 种 rescale mask、
12 种数值 pattern，以及有/无预置异常标志。输入包含正负零、最小/最大
F16 subnormal、normal 边界、负 scale、INT8 全位型变化；输出和系数组合
还覆盖 F32 subnormal、rescale 下溢/溢出，以及未激活分支中的 signaling NaN。

640 项真实数据组合使用两份原始 Qwen3 捕获的 V，覆盖 8 个 KV heads 和
各 20 个可见 token，分别以 2/8 query heads 更新 D=128 输出。系数和初始
输出是定向构造的，用于独立叶函数检查；它们不是完整 Attention 的实际
Softmax 状态，不能将这组测试描述为完整真实模型计算。

```text
REGISTER_PV_PASS cases=12928 invalid=16 real_cases=640 exact=1 flags=1 guards=1
ELF SHA256: 2d1f034a487f6b48296f460e3ce28a64f44ce4bd9d720ea730af19e034996c69
QEMU log SHA256: a2236547dde4e3b099c197df72c8fb3df2b672105c3eb1bb96e474c5612bfd09
input-pins SHA256: 99428e30d3f7e71657ff70c8ec18a344e1e5faeafa235232151848e655a842ff
```

目录 `register-pv-reference-20261028-01` 保留最初的编译检查失败：helper
未内联，wrapper 中没有解码指令，检查器因此拒绝，尚未执行 QEMU。没有放宽
该代码生成检查，也没有将第一次构建失败算作数值 PASS。

## 后续性能门槛

这一步仅证明叶函数可行，QEMU 的 15.5 秒是宿主功能验证耗时，不是目标
周期或性能数据。进入后端前仍需：

- 在独立候选中接入实际在线 Softmax/PV，保留每个 head 的 token 顺序和最终
  normalization，不能仅用预生成系数的微测量决定安装。
- 对照当前共享 RVV 解码版本，用同一真实输入和 RTL 镜像完成完整调用 ABBA，
  包含 admission、QK 和输出处理。
- 检查命令数、真实 V 行处理数、输出、flags 和协议；比较至少两种 heads/
  KV 长度配置，避免只对单一 shape 调优。
- 只有完整调用测得收益且语义稳定，才增加受能力/shape 限制的 GGML opt-in，
  保留现有默认路径与所有 fallback。若收益不足，保留证据而不安装。

正在运行的 Q4_0/Q8_0 Prefill 对照仍使用原有共享实现，不受此候选影响。
