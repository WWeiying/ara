# 矩阵候选的 SoC 交接与真实调用验证

## 当前版本和测量边界

当前候选的完整控制器和非零 seed/分段 K 测试已通过。隔离 SoC 使用 4 lane、
VLEN1024、16 MiB、256 位实际物理存储接口，新增候选开关开启；不改变生产
RTL 或已验证的原版镜像。本阶段只使用 VCS，不启动综合、功耗或 FPGA。

SoC 输入回执：唯一验证工作树的
`verification/out/e2e_balanced_soc_inputs_20261106_01/result.json`，SHA256 为
`fe7d388a120d95e2b159e7f823f91f90689c0ed0bcbea9d757a4294d7473e5b2`。
其前置证据、源文件、实际编译清单和默认关闭/开启开关均已绑定。

## 1. 先运行真正使用候选的 M4 交接

旧交接程序只执行 M1，不能证明新的 M4 路径与其他客户协同正确。后继程序保持
原 AKV 数据、三次普通 RVV 检查及直接 ownership 交接，只把四条 QBS 命令改为
M4/VL128，使用四个不同的 Q8_K 行，并在两次检查调用中检查全部四行及零尾。

| 项目 | 值 |
| --- | --- |
| QBS | M4、N3、K256；四条命令，两次检查 |
| 输出 | 256 个 FP32 字检查，其中 24 个非零、232 个零尾 |
| AKV | 三次 FULL、四次行读取、三次 RELEASE |
| 普通 RVV | 三次 load/add/store 数值检查 |
| 指令编码 | `06b5045b`；e32/m4、VL128 |

实际 ELF SHA256：
`18d74cdfd7bad7db75825d7f8e3aa0bc108832f7e74503252ea8633467b6e861`。
供运行器消费的构建回执为
`verification/out/e2e_balanced_soc_handoff_build_20261106_01/host-finalize-02/result.json`，
SHA256 为 `190eadea36bb1aaa2d8573ab6dcef804701986667e1cd103fdfcbacb11083690`。

原构建已完成编译与链接，但最后的 unittest 模块发现失败，因此原 worker 保持
FAIL。后继主机审计仅修正测试环境并重跑 7 项测试，检查同一 ELF、指令、数据和
装载范围，没有重新编译或重链接，也没有将原 worker 改写为 PASS。

`run_balanced_handoff.py` 保留原 SoC worker 的输入身份、装载、物理平台及独立
UVM/AXI/backend 检查。增加实际 M4 工作量、十条 AKV 命令和联合完成顺序检查：

```text
QBS -> QBS -> AKV x10 -> QBS -> QBS
```

AKV 使用现有严格数字字段解析器，允许并要求真实日志中的 `v2_full` 等字段。
普通数字字段解析器不适合该日志。仅 UART PASS 不足以验收，还要求目标 Core
SUCCESS、原始 trace/日志/镜像绑定及独立协议通过。此处不宣称运行已通过。

## 2. 再测真实模型 SDK 调用

| 调用 | 维度 | 原版对照 | 候选对照 |
| --- | --- | --- | --- |
| QKV | M4，N=2048/1024/1024，K2048 | 可复用已通过的物理 256 位结果 | 相同 ELF，新 balanced 256 位 SoC |
| FFN | M4，N128，K=2048/2048/6144 | 必须新跑原物理 256 位 SoC | 相同 ELF，新 balanced 256 位 SoC |

先前 FFN wide 结果来自物理 128 位平台。直接与新候选比较会混入供给宽度收益，
不能称为计算结构的增量收益。新 FFN 原版与候选均固定 256 位。

QKV 的构建 SHA256 为
`1d55ba64a5b53f7f13a001596c80f0d3b6e09be34cf5b9af00e32a7f5dc2610a`。
FFN 的构建 SHA256 为
`3bd54bcf04cd670d2ad836cb0ee7a35591c4a25c15c1d537b67feeff2b43a2d4`，
ELF SHA256 为 `1fcac1e6643c00e6c74d2a8592a49b3f006af032c46bfacd48838d70bcf57f47`。
两个工作负载均保留准备和准入，不含冷权重重排；FFN down 输入是独立真实捕获，
不是由该 N128 gate/up 切片重新构造的完整 SiLU/FFN 链。

`check_balanced_sdk.py` 只特化原 checker 的点积发射次数期望：每条 QKV 命令
4096→2048；FFN 每 K 块 512→256。原 checker 整文件身份、数值期望、CSR、
命令形状、工作量、物理读流量及阶段账目仍检查，不改写原始日志。
实际关闭路径保持原期望，不能让新计数同时通过旧检查。

`run_balanced_sdk.py` 固定相同的 build、ELF、oracle 和 256 位平台，候选必须
先在同一完整镜像通过 M4 交接。原版 FFN 可在候选编译期间并行执行。
每项运行必须再通过独立协议检查；配对时允许性能退化，不预设优化成功。

报告准备、准入、执行和总区域周期。QKV 是四个真实 prompt token 的完整输出
投影组，FFN 为 N128 的完整 K 三项调用，均不是完整 GGML 图或模型 token/s。
模型级收益仍需结合真实调用次数、其余算子与外部带宽，不能直接相乘或按 N 放大。
