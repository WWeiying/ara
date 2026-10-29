# 共享 RVV 解码下的 Prefill 完整调用配对

## 测量目的

旧的独立 Prefill 驱动曾使用 `dequantize_row_q8_0` 标量回调；真实
GGML 后端使用的是 `akv_quant_q8_0_value` RVV 回调。旧结果只能说明旧配置
的性能，不能直接作为当前后端的分组收益。本轮使用已经收敛到
`software/akv/experimental/quantized_kv/prefill/` 的实现和共享 RVV 回调，
重新建立两种 K 格式的完整调用配对。此处没有新增 RTL、指令或算术近似。

## 输入与对照

输入来自真实 Qwen3-1.7B Q4_K_M 模型的 Prefill 捕获，权重格式与本测试
的 KV cache 格式不是同一概念。每种捕获分别采用 Q4_0 或 Q8_0 的 K，
V 均为 Q8_0。

| 项目 | 配置 |
|---|---|
| Q | F32，head dimension 128，取 query 16–19 |
| GQA | 取一个 KV head 对应的两个 query heads，共 8 个输出行 |
| 实际可见 KV 长度 | 四个 query 分别为 17、18、19、20 |
| 原捕获容量 | 256 KV tokens，8 个物理 KV heads |
| 布局 | 将原始 K/V 字节从 head-major 置换为 token-major，不重新量化 |
| RTL | 4 lanes，VLEN=1024，16 MiB 仿真 L2，与前期测量使用同一镜像 |
| A | 连续四次调用当前 `akv_quant_strided_execute`，每次处理一个 query |
| B | 一次调用当前 `quant_prefill_execute`，跨 query 分组并共享 V |
| 顺序 | A、B、B、A；每次独立初始化输出保护区和 FCSR/VCSR |

周期区间包括 admission、Query 量化、K 面板准备、QK、在线 Softmax/PV、
输出 scatter 及结束 drain，不包括打印和结果检查，也不包括真实运行时的
C++ dispatch 和堆工作区分配。因此它是完整内核调用对照，不是完整模型加速比。

| 必须检查的活动 | A：逐 query | B：跨 query 分组 |
|---|---:|---:|
| QBS 命令数 | 4 | 4 |
| V 行解码次数 | 74 | 20 |
| K 面板数 | 4 | 1 |
| K 复制行数 | 74 | 20 |
| Q4_0 K 复制字节 | 5328 | 1440 |
| Q8_0 K 复制字节 | 10064 | 2720 |

两边并未减少 QK 命令数。预期收益来自减少重复的 KV 检查、K 复制和 V
解码；是否体现为周期下降，以本轮实际结果为准，不能只用次数下降推算。

## 构建与验收

新入口：

- `verification/akv/quantized_kv/prefill/build_production_native.py`
- `verification/akv/quantized_kv/prefill/run_production_native.py`
- `verification/akv/quantized_kv/prefill/test_production_native.py`

历史目录只提供经过哈希核对的编译命令配方，不继承旧 C/header 身份，
不复用旧对象。两种格式分别重新编译全部 16 个对象，并重新记录当前依赖、
GNU 工具、链接脚本及静态数学库的哈希。捕获的十个输入文件（五组
二进制及元数据）逐项对照封存的捕获审计，并检查完整 shape、stride 和 extent。
生成的 token-major 数据另行记录哈希。

构建结束检查最终反汇编：必须存在 native QBS 执行路径及共享 V 解码器的
`vle8.v`、`vsext.vf4`、`vfcvt.f.x.v`、`vfmul.vf`、`vse32.v`；不得链接
`dequantize_row_q8_0` 或 `qbs_ref_execute`。生产运行入口额外拒绝未声明共享
RVV 回调或未使用规范 Prefill 路径的构建。

既有数值和协议 checker 没有放宽：每轮检查 1024 个输出、ABBA 各轮位级
一致性、真实捕获 golden 的误差界、FCSR/VCSR、保护区、命令/解码/面板活动，
之后执行独立 UVM/AXI 协议检查及前后源码/镜像身份检查。只有全部完成后，
`result.json` 才能标为 `PASS`。启动成功或 `PREFLIGHT_NOT_RUN` 不是仿真通过。

## 本次封存与运行位置

两种构建和只读 preflight 已完成；8 项构建门控、捕获身份/几何、回调绑定、
日志负向测试及布局置换测试通过。以下是启动时状态，不代表性能结果已出。

| K 格式 | ELF SHA256 | 状态 |
|---|---|---|
| Q4_0 | `669e41a0aa21bdfef10b2ea5fa19bb618278f19b2f1c7af49b28639bc8fe6b77` | VCS 后台执行，待验收 |
| Q8_0 | `9cb226566b8ccfe1fd404ed439dd0dc0a1af94b42b048fe049983af336bd7bb2` | VCS 后台执行，待验收 |

所有目录均位于当前验证工作树的 `verification/out/`：

- 构建：`prefill-production-q4-build-20261028-01`、`prefill-production-q8-build-20261028-01`。
- 运行：`prefill-production-q4-vcs-20261028-01`、`prefill-production-q8-vcs-20261028-01`。
- systemd 单元：`prefill-production-q4-20261028-01.service`、`prefill-production-q8-20261028-01.service`。

两个单元直接管理 Python worker 和 VCS 子进程。每路 VCS 的运行上限为
10800 秒；另设 12000 秒服务上限以容纳身份核验和协议检查。不运行综合，
不覆盖历史结果，不在运行期间修改被封存的实现或 checker。

查看状态，不必持续轮询：

```bash
systemctl --user status prefill-production-q{4,8}-20261028-01.service --no-pager
cat verification/out/prefill-production-q{4,8}-vcs-20261028-01/status.json
```

结束后读取两个运行目录的 `result.json`；仅在 `state=PASS`、
`independent_protocol_checked=true`、`post_pins_match=true` 时引用其
`measured.baseline_cycles`、`measured.shared_cycles` 和 `measured.speedup`。
没有生成终态结果前，不填写加速比，也不与旧标量回调数据拼接。
